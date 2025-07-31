const { ActivityTypes } = require("@microsoft/agents-activity");
const {
  AgentApplication,
  AttachmentDownloader,
  MemoryStorage,
} = require("@microsoft/agents-hosting");
const { version } = require("@microsoft/agents-hosting/package.json");
const axios = require("axios");

const downloader = new AttachmentDownloader();
const storage = new MemoryStorage();
require("dotenv").config();

// Simple in-memory cache to avoid eTag conflicts for non-critical data
const conversationCache = new Map();

const teamsBot = new AgentApplication({
  storage,
  fileDownloaders: [downloader],
});

// Global error handler for eTag conflicts
teamsBot.onTurnError = async (context, error) => {
  console.error(`[onTurnError] unhandled error: ${error}`);
  
  if (error.message && error.message.includes("eTag conflict")) {
    console.warn("Global eTag conflict detected - attempting graceful recovery");
    try {
      await context.sendActivity("I encountered a temporary issue while saving data. Please try your request again.");
    } catch (sendError) {
      console.error("Failed to send error message:", sendError);
    }
  } else {
    try {
      await context.sendActivity("Sorry, I encountered an unexpected error. Please try again.");
    } catch (sendError) {
      console.error("Failed to send error message:", sendError);
    }
  }
};

// Utility functions for cache management (avoiding eTag conflicts)
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

// Simplified state saving for critical data only (like count)
async function saveCriticalState(context, state, storage, updates = {}) {
  const maxRetries = 3;
  for (let i = 0; i < maxRetries; i++) {
    try {
      // Apply updates to state
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
        await new Promise(resolve => setTimeout(resolve, 200 + Math.random() * 300));
        await state.load(context, storage);
      } else if (i === maxRetries - 1) {
        console.error("Failed to save critical state after retries:", err);
        return false;
      }
    }
  }
  return false;
}

// /reset command
teamsBot.message("/reset", async (context, state) => {
  try {
    const conversationId = getConversationId(context);
    await state.load(context, storage);
    state.deleteConversationState();
    
    // Clear cache for this conversation
    conversationCache.delete(conversationId);
    
    await context.sendActivity("Ok I've deleted the current conversation state.");
    await saveCriticalState(context, state, storage);
  } catch (error) {
    console.error("Error in /reset command:", error);
    await context.sendActivity("Failed to reset conversation state. Please try again.");
  }
});

// /count command
teamsBot.message("/count", async (context, state) => {
  try {
    await state.load(context, storage);
    const count = state.conversation.count ?? 0;
    const newCount = count + 1;
    await context.sendActivity(`The count is ${newCount}`);
    
    // Save count to state (critical data)
    const saved = await saveCriticalState(context, state, storage, { 'conversation.count': newCount });
    if (!saved) {
      console.warn("Failed to save count, but continuing...");
    }
  } catch (error) {
    console.error("Error in /count command:", error);
    await context.sendActivity("Failed to update count. Please try again.");
  }
});

// /diag command
teamsBot.message("/diag", async (context, state) => {
  await state.load(context, storage);
  await context.sendActivity(JSON.stringify(context.activity));
});

// /state command
teamsBot.message("/state", async (context, state) => {
  await state.load(context, storage);
  await context.sendActivity(JSON.stringify(state));
});

// /runtime command
teamsBot.message("/runtime", async (context, state) => {
  const runtime = {
    nodeversion: process.version,
    sdkversion: version,
  };
  await context.sendActivity(JSON.stringify(runtime));
});

// /newppt command
teamsBot.message("/newppt", async (context, state) => {
  try {
    const conversationId = getConversationId(context);
    console.log("new ppt generation start")
    // Get previous response from cache instead of state
    const previousResponse = getCachedData(conversationId, 'previousResponse') || "No previous context available.";
    const apiUrl = "http://172.200.58.63:8099/";
    const payload = { query: previousResponse };

    const response = await axios.post(apiUrl, payload, {
      headers: { "Content-Type": "application/json" },
    });

    const { message } = response.data;
    await context.sendActivity(message);
    
    // Store in cache instead of state to avoid eTag conflicts
    setCachedData(conversationId, 'previousResponse', message);
  } catch (error) {
    console.error("Error in /newppt:", error.response?.data || error.message);
    await context.sendActivity("Sorry, I couldn't fetch data from the API.");
  }
});

// /genppt command — no state writing here
teamsBot.message("/genppt", async (context, state) => {
  try {
    console.log("Generating new generalised ppt");
    const apiUrl = "http://172.200.58.63:8098/";
    const payload = { query: "generate new generalised ppt" };

    const response = await axios.post(apiUrl, payload, {
      headers: { "Content-Type": "application/json" },
    });

    const { message } = response.data;
    await context.sendActivity(message);
  } catch (error) {
    console.error("Error in /genppt:", error.response?.data || error.message);
    await context.sendActivity("Sorry, I couldn't fetch data from the API.");
  }
});

// Generic fallback handler
teamsBot.activity(ActivityTypes.Message, async (context, state) => {
  try {
    await state.load(context, storage); // Load state

    const userMessage = context.activity.text.trim().toLowerCase();
    if (userMessage === "hi") {
      await context.sendActivity("Hello! Hope you are fine. Please ask your query.");
      return;
    }

    const apiUrl = "http://104.208.162.61:8000/query";
    const payload = { query: userMessage};
    const token_URI ="http://104.208.162.61:8000/token"
    const username = process.env.USERNAME;
    const password = process.env.PASSWORD;
    const token_payload = 
      {
        "username": username,
        "password": password
      }
    const token = await axios.post(token_URI, token_payload, {
      headers: { "Content-Type": "application/json" },
    });
    const token1 = token.data.access_token;
    console.log("Token received:", token1);    

// Send token to FastAPI
const response = await axios.post(apiUrl, payload, {
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token1}`,
  },
});
console.log("Response received:", response.data);


    const { answer, sources } = response.data;

    // Build the response 
    let formattedResponse = `**Answer:**\n${answer}`;
    if (answer !== "I don't have enough information to answer this question based on the context.") {
      formattedResponse += `\n\n**Sources:**\n`;
      
      // Convert sources object to array since API returns sources as object, not array
      const sourcesArray = sources && typeof sources === 'object' ? Object.values(sources) : [];
      
      // Deduplicate sources from the same slide and document
      const groupedSources = new Map();
      
      sourcesArray.forEach(source => {
        const slideMatch = source.text?.match(/\[Slide (\d+)\]/);
        const slideNumber = slideMatch ? slideMatch[1] : 'unknown';
        const sourceInfo = source.source_info || 'Unknown Document';
        const key = `${slideNumber}-${sourceInfo}`;
        
        if (groupedSources.has(key)) {
          // If we already have content from this slide/document, combine the text
          const existing = groupedSources.get(key);
          // Only add if the text is significantly different (to avoid exact duplicates)
          if (!existing.text.includes(source.text?.substring(0, 50) || '')) {
            existing.text += `\n${source.text}`;
            existing.combinedCount = (existing.combinedCount || 1) + 1;
          }
        } else {
          groupedSources.set(key, { ...source, combinedCount: 1 });
        }
      });
      
      // Convert back to array for processing
      const deduplicatedSources = Array.from(groupedSources.values());
      
      deduplicatedSources.forEach((source, index) => {
        const sourceText = source.text || "No excerpt available";
        const sourceFile = source.source_file || "Unnamed Source";
        const pptLink = source.metadata?.filepath;
        const slideUrl = source.metadata?.slide_url;
      
        // Handle multiple source files separated by commas
        const sourceFiles = sourceFile.split(',').map(file => file.trim());
        
        // If we have multiple files but only one link, don't make all files clickable 
        // as it's misleading - one link can't represent multiple different files
        const formattedSourceFiles = sourceFiles.length > 1 && pptLink
          ? sourceFiles.join(', ') // Just show file names without links for multiple files
          : sourceFiles.map(file => {
              return pptLink ? `[${file}](${pptLink})` : file;
            }).join(', ');
      
        // Extract slide number from text if available (e.g., [Slide 14])
        const slideMatch = sourceText.match(/\[Slide (\d+)\]/);
        const slideNumber = slideMatch ? slideMatch[1] : null;
        
        // Format Slide URL only if present and valid
        const slideLinkText = slideUrl && slideUrl !== "Slide URL"
          ? `\n   **Slide URL:** [View Slide${slideNumber ? ` ${slideNumber}` : ''}](${slideUrl})`
          : "";
      
        formattedResponse += `\n${index + 1}. ${sourceText}`;
        
        // Add note if multiple sources were combined
        if (source.combinedCount > 1) {
          formattedResponse += `\n   *(Combined ${source.combinedCount} similar sources from the same slide)*`;
        }
        
        formattedResponse += `\n   **Source Files:** ${formattedSourceFiles}`;
        
        // If we have multiple files and a link, show the link separately
        if (sourceFiles.length > 1 && pptLink) {
          formattedResponse += `\n   **Available Link:** [View Document](${pptLink})`;
        }
        
        if (slideLinkText) {
          formattedResponse += slideLinkText;
        }
      });
      
      
    }

    await context.sendActivity(formattedResponse);
    
    // Store response in cache instead of state to avoid eTag conflicts
    const conversationId = getConversationId(context);
    setCachedData(conversationId, 'previousResponse', formattedResponse);
    
  } catch (error) {
    console.error("Error in fallback handler:", error.message);
    await context.sendActivity("Sorry, I couldn't fetch data from the API.");
  }
});


// Conversation update handler
teamsBot.conversationUpdate("membersAdded", async (context, state) => {
  await context.sendActivity(`Hi there! I'm an echo bot running on Agents SDK version ${version}.`);
});

module.exports.teamsBot = teamsBot;