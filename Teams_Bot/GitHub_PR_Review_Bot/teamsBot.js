const { ActivityTypes } = require("@microsoft/agents-activity");
const {
  AgentApplication,
  AttachmentDownloader,
  MemoryStorage,
} = require("@microsoft/agents-hosting");
const { version } = require("@microsoft/agents-hosting/package.json");
const fs = require('fs').promises;
const path = require('path');
const fetch = require('node-fetch');

// In-memory cache to avoid eTag conflicts
const conversationCache = new Map();

function generateGithubApiUrls(prUrl) {
  prUrl = prUrl.trim();
  if (!prUrl.startsWith("https://github.com/") && !prUrl.startsWith("http://github.com/")) {
    throw new Error("Invalid GitHub PR URL");
  }
  prUrl = prUrl.replace(/\/+$/, "");
  const parts = prUrl.replace(/^https?:\/\/github\.com\//, "").split("/");
  if (parts.length !== 4 || parts[2] !== "pull") {
    throw new Error("URL must be in the format: https://github.com/owner/repo/pull/number");
  }
  const [owner, repo, , prNumber] = parts;
  const PR_Diff_API = `https://api.github.com/repos/${owner}/${repo}/pulls/${prNumber}`;
  const PR_Comment_API = `https://api.github.com/repos/${owner}/${repo}/issues/${prNumber}/comments`;
  return { PR_Diff_API, PR_Comment_API };
}

async function checkPRExists(prUrl, token) {
  try {
    const { PR_Diff_API } = generateGithubApiUrls(prUrl);
    const headers = {
      'User-Agent': 'pr-reviewbot'
    };
    if (token) {
      headers['Authorization'] = token;
    }
    const response = await fetch(PR_Diff_API, {
      headers
    });
    if (response.status === 404) {
      return { exists: false };
    }
    if (!response.ok) {
      return { exists: false };
    }
    // Only check if PR exists, don't care about open/closed/merged
    return { exists: true };
  } catch (err) {
    return { exists: false };
  }
}

// Utility functions for cache management
function getConversationId(context) {
  return context.activity.conversation.id;
}

function getCachedData(conversationId, key) {
  const convData = conversationCache.get(conversationId) || {};
  return convData[key];
}

function setCachedData(conversationId, key, value) {
  const convData = conversationCache.get(conversationId) || {};
  convData[key] = value;
  conversationCache.set(conversationId, convData);
}

async function saveCriticalState(context, state, storage, updates = {}) {
  const maxRetries = 5;
  const baseDelay = 200;
  for (let i = 0; i < maxRetries; i++) {
    try {
      Object.keys(updates).forEach(key => {
        if (key.includes('.')) {
          const keys = key.split('.');
          let obj = state;
          for (let j = 0; j < keys.length - 1; j++) {
            if (!obj[keys[j]]) obj[keys[j]] = {};
            obj = obj[keys[j]];
          }
          obj[keys[keys.length - 1]] = updates[key];
        } else {
          state[key] = updates[key];
        }
      });
      await state.save(context, storage, { forceWrite: true });
      return true;
    } catch (err) {
      if (err.message.includes("eTag conflict") && i < maxRetries - 1) {
        const delay = baseDelay * Math.pow(2, i) + Math.random() * 100;
        await new Promise(resolve => setTimeout(resolve, delay));
        await state.load(context, storage, { force: true });
      } else if (i === maxRetries - 1) {
        console.error("Failed to save critical state after retries:", err);
        return false;
      }
    }
  }
  return false;
}

const downloader = new AttachmentDownloader();
const storage = new MemoryStorage();
const teamsBot = new AgentApplication({
  storage,
  fileDownloaders: [downloader],
});

// Global error handler
teamsBot.onTurnError = async (context, error) => {
  console.error(`[onTurnError] unhandled error: ${error}`);
  if (error.message && error.message.includes("eTag conflict")) {
    console.warn("Global eTag conflict detected - attempting recovery");
    try {
      const conversationId = getConversationId(context);
      conversationCache.delete(conversationId); // Clear cache to prevent stale data
      await context.sendActivity("I encountered a temporary issue with data consistency. Please restart the process with /review.");
    } catch (sendError) {
      console.error("Failed to send error message:", sendError);
    }
  } else {
    try {
      await context.sendActivity("Sorry, I encountered an unexpected error. Please try again or use /reset to clear the state.");
    } catch (sendError) {
      console.error("Failed to send error message:", sendError);
    }
  }
};

const FLOW_STATES = {
  WAITING_FOR_PR: 'waiting_for_pr',
  WAITING_FOR_PROJECT: 'waiting_for_project',
  WAITING_FOR_PAT: 'waiting_for_pat',
  COMPLETED: 'completed'
};

async function loadMappedProjects() {
  try {
    const mappedPath = path.join(__dirname, 'mapped.json');
    const data = await fs.readFile(mappedPath, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading mapped.json:', error);
    return { AI_Studio: "default_token_1", Pedigree: "default_token_2", NiFiMCP: "default_token_3", JumpV: "default_token_4" };
  }
}

async function loadMappedPATs() {
  try {
    const mappedPath = path.join(__dirname, 'mapped1.json');
    const data = await fs.readFile(mappedPath, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading mapped1.json:', error);
    return { "test_user": "ghp_default_pat_test_user" };
  }
}

async function saveUserData(userId, data, conversationId) {
  try {
    const filePath = path.join(__dirname, 'input', 'user_submissions.json');
    const { PR_Diff_API, PR_Comment_API } = generateGithubApiUrls(data.prLink);
    const submissionData = {
      ProjectToken: data.projectToken,
      User_Github_token: `token ${data.userPAT}`,
      PR_Link: data.prLink,
      PR_Diff_API,
      PR_Comment_API,
      timestamp: new Date().toISOString()
    };
    await fs.writeFile(filePath, JSON.stringify(submissionData, null, 2));
    setCachedData(conversationId, 'userData', submissionData);
    return true;
  } catch (error) {
    console.error('Error saving user data:', error);
    return false;
  }
}

function createProjectPoll(projects) {
  const projectOptions = Object.keys(projects).map((project) => ({
    title: project,
    value: project
  }));
  return {
    type: "message",
    attachments: [{
      contentType: "application/vnd.microsoft.card.adaptive",
      content: {
        type: "AdaptiveCard",
        version: "1.2",
        body: [
          {
            type: "TextBlock",
            text: "Please select your project:",
            weight: "Bolder",
            size: "Medium"
          },
          {
            type: "Input.ChoiceSet",
            id: "projectChoice",
            style: "compact",
            choices: projectOptions.map(option => ({
              title: option.title,
              value: option.value
            }))
          }
        ],
        actions: [
          {
            type: "Action.Submit",
            title: "Select Project",
            data: { action: "selectProject" }
          }
        ]
      }
    }]
  };
}

function createPATPoll(pats) {
  const patOptions = Object.keys(pats).map((pat) => ({
    title: pat,
    value: pat
  }));
  return {
    type: "message",
    attachments: [{
      contentType: "application/vnd.microsoft.card.adaptive",
      content: {
        type: "AdaptiveCard",
        version: "1.2",
        body: [
          {
            type: "TextBlock",
            text: "Please select your Personal Access Token:",
            weight: "Bolder",
            size: "Medium"
          },
          {
            type: "Input.ChoiceSet",
            id: "patChoice",
            style: "compact",
            choices: patOptions.map(option => ({
              title: option.title,
              value: option.value
            }))
          }
        ],
        actions: [
          {
            type: "Action.Submit",
            title: "Select PAT",
            data: { action: "selectPAT" }
          }
        ]
      }
    }]
  };
}

teamsBot.message("/reset", async (context, state) => {
  try {
    const conversationId = getConversationId(context);
    await state.load(context, storage);
    state.deleteConversationState();
    conversationCache.delete(conversationId);
    await context.sendActivity("Ok I've deleted the current conversation state.");
    await saveCriticalState(context, state, storage);
  } catch (error) {
    console.error("Error in /reset command:", error);
    await context.sendActivity("Failed to reset conversation state. Please try again.");
  }
});

teamsBot.message("/review", async (context) => {
  try {
    const conversationId = getConversationId(context);
    setCachedData(conversationId, 'flowState', FLOW_STATES.WAITING_FOR_PR);
    setCachedData(conversationId, 'userData', {});
    await context.sendActivity("Let's start the PR submission process!\n\n**Enter PR Link:**");
  } catch (error) {
    console.error("Error in /review command:", error);
    await context.sendActivity("Failed to start PR submission process. Please try again.");
  }
});

teamsBot.message("/count", async (context, state) => {
  try {
    await state.load(context, storage);
    const count = state.conversation.count ?? 0;
    const newCount = count + 1;
    await context.sendActivity(`The count is ${newCount}`);
    await saveCriticalState(context, state, storage, { 'conversation.count': newCount });
  } catch (error) {
    console.error("Error in /count command:", error);
    await context.sendActivity("Failed to update count. Please try again.");
  }
});

teamsBot.message("/diag", async (context, state) => {
  try {
    await state.load(context, storage);
    await context.sendActivity(JSON.stringify(context.activity));
  } catch (error) {
    console.error("Error in /diag command:", error);
    await context.sendActivity("Failed to retrieve diagnostic info. Please try again.");
  }
});

teamsBot.message("/state", async (context, state) => {
  try {
    await state.load(context, storage);
    const conversationId = getConversationId(context);
    const cachedData = conversationCache.get(conversationId) || {};
    await context.sendActivity(JSON.stringify({ storageState: state, cacheState: cachedData }));
  } catch (error) {
    console.error("Error in /state command:", error);
    await context.sendActivity("Failed to retrieve state info. Please try again.");
  }
});

teamsBot.message("/runtime", async (context) => {
  try {
    const runtime = {
      nodeversion: process.version,
      sdkversion: version,
    };
    await context.sendActivity(JSON.stringify(runtime));
  } catch (error) {
    console.error("Error in /runtime command:", error);
    await context.sendActivity("Failed to retrieve runtime info. Please try again.");
  }
});

teamsBot.conversationUpdate("membersAdded", async (context) => {
  try {
    await context.sendActivity(
      `Hi there! I'm a PR submission bot. \n\nType **/review** to begin the PR submission process.`
    );
  } catch (error) {
    console.error("Error in conversationUpdate:", error);
  }
});

teamsBot.activity(ActivityTypes.Message, async (context, state) => {
  try {
    const conversationId = getConversationId(context);
    const userInput = context.activity.text;

    // Handle adaptive card submissions
    if (context.activity.value) {
      if (context.activity.value.action === "selectProject") {
        const selectedProject = context.activity.value.projectChoice;
        if (selectedProject && getCachedData(conversationId, 'flowState') === FLOW_STATES.WAITING_FOR_PROJECT) {
          const mappedProjects = await loadMappedProjects();
          setCachedData(conversationId, 'userData', {
            ...getCachedData(conversationId, 'userData'),
            selectedProject,
            projectToken: mappedProjects[selectedProject]
          });
          setCachedData(conversationId, 'flowState', FLOW_STATES.WAITING_FOR_PAT);
          const mappedPATs = await loadMappedPATs();
          const patPollCard = createPATPoll(mappedPATs);
          await context.sendActivity(patPollCard);
        }
      } else if (context.activity.value.action === "selectPAT") {
        const selectedPAT = context.activity.value.patChoice;
        if (selectedPAT && getCachedData(conversationId, 'flowState') === FLOW_STATES.WAITING_FOR_PAT) {
          const mappedPATs = await loadMappedPATs();
          const userData = {
            ...getCachedData(conversationId, 'userData'),
            userPAT: mappedPATs[selectedPAT]
          };
          setCachedData(conversationId, 'userData', userData);
          setCachedData(conversationId, 'flowState', FLOW_STATES.COMPLETED);
          const success = await saveUserData(context.activity.from.id, userData, conversationId);
          if (success) {
            await context.sendActivity(`✅ **Your data has been saved successfully. We are reviewing your PR.**`);
            await new Promise(resolve => setTimeout(resolve, 80000));
            const OutputDir = path.join(__dirname, 'output');
            const files = await fs.readdir(OutputDir);
            if (files.length > 0) {
              await context.sendActivity(`**GitHub PR has been reviewed and commented. You can check by going to the PR link.**`);
              await Promise.all(
                files.map(file => fs.unlink(path.join(OutputDir, file)))
              );
            }
            setCachedData(conversationId, 'flowState', null);
            setCachedData(conversationId, 'userData', {});
            await saveCriticalState(context, state, storage, {
              'conversation.flowState': null,
              'conversation.userData': {}
            });
          } else {
            await context.sendActivity("❌ Error saving your data. Please try again.");
            setCachedData(conversationId, 'flowState', null);
            setCachedData(conversationId, 'userData', {});
          }
        }
      }
      return;
    }

    // Skip commands and empty messages
    if (!userInput || userInput.startsWith('/')) {
      return;
    }

    // Handle PR submission flow
    const currentFlowState = getCachedData(conversationId, 'flowState');
    if (currentFlowState === FLOW_STATES.WAITING_FOR_PR) {
      function inferProjectFromPR(prUrl) {
        if (prUrl.includes("AIStudioShorthills")) return "AI_Studio";
        if (prUrl.includes("PedigreeAll")) return "Pedigree";
        if (prUrl.includes("shorthills-ai")) return "NiFiMCP";
        if (prUrl.includes("JumpV")) return "JumpV";
        return null;
      }

      if (userInput.includes('github.com') && userInput.includes('/pull/')) {
        setCachedData(conversationId, 'userData', {
          ...getCachedData(conversationId, 'userData'),
          prLink: userInput
        });

        const inferredProject = inferProjectFromPR(userInput);
        if (!inferredProject) {
          await context.sendActivity("❌ Could not determine the project from the PR link. Please check the URL.");
          return;
        }

        const mappedProjects = await loadMappedProjects();
        const projectToken = mappedProjects[inferredProject];
        if (!projectToken) {
          await context.sendActivity("❌ Could not find a token for the inferred project. Please check your configuration.");
          return;
        }

        // Pass the correct token to checkPRExists
        const prStatus = await checkPRExists(userInput, projectToken);
        if (!prStatus.exists) {
          await context.sendActivity("❌ The given PR doesn't exist. Please check the PR link.");
          return;
        }
        // Removed merged/closed PR checks here

        const mappedPATs = await loadMappedPATs();
        const userData = {
          ...getCachedData(conversationId, 'userData'),
          selectedProject: inferredProject,
          projectToken: mappedProjects[inferredProject],
          userPAT: mappedPATs["pr-reviewbot"]
        };
        setCachedData(conversationId, 'userData', userData);
        setCachedData(conversationId, 'flowState', FLOW_STATES.COMPLETED);
        const success = await saveUserData(context.activity.from.id, userData, conversationId);
        if (success) {
          await context.sendActivity(`✅ **Your data has been saved successfully. We are reviewing your PR.**`);
          await new Promise(resolve => setTimeout(resolve, 80000));
          const OutputDir = path.join(__dirname, 'output');
          const files = await fs.readdir(OutputDir);
          if (files.length > 0) {
            await context.sendActivity(`**GitHub PR has been reviewed and commented. You can check by going to the PR link.**`);
            await Promise.all(
              files.map(file => fs.unlink(path.join(OutputDir, file)))
            );
          }
          setCachedData(conversationId, 'flowState', null);
          setCachedData(conversationId, 'userData', {});
          await saveCriticalState(context, state, storage, {
            'conversation.flowState': null,
            'conversation.userData': {}
          });
        } else {
          await context.sendActivity("❌ Error saving your data. Please try again.");
          setCachedData(conversationId, 'flowState', null);
          setCachedData(conversationId, 'userData', {});
        }
      } else {
        await context.sendActivity("Please enter a valid GitHub PR link to continue.");
      }
    }
  } catch (error) {
    console.error("Error in message handler:", error);
    await context.sendActivity("Sorry, I encountered an error. Please try again or use /reset to clear the state.");
  }
});

module.exports.teamsBot = teamsBot;