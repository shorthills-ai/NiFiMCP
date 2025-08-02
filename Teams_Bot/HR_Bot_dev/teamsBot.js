const axios = require("axios");
const FormData = require("form-data");


const { ActivityTypes } = require("@microsoft/agents-activity");
const {
  AgentApplication,
  AttachmentDownloader,
  MemoryStorage,
} = require("@microsoft/agents-hosting");
const { version } = require("@microsoft/agents-hosting/package.json");

const downloader = new AttachmentDownloader();
// Define storage and application
const storage = new MemoryStorage();
const teamsBot = new AgentApplication({
  storage,
  fileDownloaders: [downloader],
});

// ✅ Step 1: Load .env at the VERY top
require('dotenv').config();

// ✅ Step 2: Define variables AFTER dotenv is loaded
const PRIMARY_NIFI_URL = process.env.PRIMARY_NIFI_URL;
const FALLBACK_NIFI_URL = process.env.FALLBACK_NIFI_URL;

// ✅ Step 3: Use them
if (!PRIMARY_NIFI_URL || !FALLBACK_NIFI_URL) {
  throw new Error("Missing NIFI URLs in environment variables");
}

/**
 * Axios wrapper with fallback
 * @param {'get'|'post'} method 
 * @param {string} path 
 * @param {object} options { data, config }
 */
async function axiosWithFallback(method, path, { data = {}, config = {} } = {}) {
  const primaryUrl = `${PRIMARY_NIFI_URL}${path}`;
  const fallbackUrl = `${FALLBACK_NIFI_URL}${path}`;
  try {
    return await axios({ method, url: primaryUrl, data, ...config });
  } catch (primaryErr) {
    console.warn(`[Primary Failed] ${method.toUpperCase()} ${primaryUrl}:`, primaryErr.message);
    try {
      return await axios({ method, url: fallbackUrl, data, ...config });
    } catch (fallbackErr) {
      console.error(`[Fallback Failed] ${method.toUpperCase()} ${fallbackUrl}:`, fallbackErr.message);
      throw fallbackErr;
    }
  }
}
async function sendWelcomeCard(context) {
  const card = {
    type: "AdaptiveCard",
    version: "1.4",
    body: [
      {
        type: "TextBlock",
        text: "👋 Welcome to the HR Bot!",
        size: "ExtraLarge",
        weight: "Bolder",
        color: "Accent",
        horizontalAlignment: "center",
        wrap: true
      },
      {
        type: "TextBlock",
        text: "Here are some things I can do for you:",
        size: "Medium",
        weight: "Bolder",
        wrap: true,
        spacing: "Medium"
      },
      {
        type: "FactSet",
        facts: [
          { title: "/makeresume", value: "Generate a resume for a candidate (with or without job description)." },
          { title: "/search", value: "Search for candidates by name, skill, or keyword." },
          { title: "/view", value: "View a candidate's resume by employee ID or name." },
          { title: "/delete", value: "Delete a candidate by employee ID or name." },
          { title: "/uploadfolder", value: "Upload folder onedrive link containing resumes" },
          { title: "/add", value: "Add a SharePoint resume link for a candidate." }
        ]
      },
      {
        type: "TextBlock",
        text: "Quick Actions:",
        size: "Medium",
        weight: "Bolder",
        spacing: "Large"
      }
      // Quick action buttons removed from Adaptive Card
    ],
    $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
  };

  await context.sendActivity({
    type: "message",
    attachments: [
      {
        contentType: "application/vnd.microsoft.card.adaptive",
        content: card
      }
    ]
  });

  // Send suggested actions (these fill the compose box, not send immediately)
  await context.sendActivity({
    type: "message",
    text: "Here are some quick actions you can try:",
    suggestedActions: {
      actions: [
        { type: "imBack", title: "/makeresume", value: "/makeresume" },
        { type: "imBack", title: "/search", value: "/search" },
        { type: "imBack", title: "/add", value: "/add" },
        { type: "imBack", title: "/view", value: "/view" },
        { type: "imBack", title: "/delete", value: "/delete" },
        { type: "imBack", title: "/uploadfolder", value: "/uploadfolder" },
        { type: "imBack", title: "/help", value: "/help" }
      ],
      to: [context.activity.from.id]
    }
  });
}
// Listen for user to say '/reset' and then delete conversation state
teamsBot.message("/reset", async (context, state) => {
  state.deleteConversationState();
  await context.sendActivity("Ok I've deleted the current conversation state.");
});

// Test command to check environment and connectivity
teamsBot.message("/test", async (context, state) => {
  try {
    // Test basic connectivity
    const testResponse = await axiosWithFallback("get", "/", {
      config: { timeout: 5000 }
    });
    await context.sendActivity(`✅ NIFI processor is reachable. Status: ${testResponse.status}`);
  } catch (err) {
    await context.sendActivity(`❌ NIFI processor connectivity test failed: ${err.message}`);
  }
  // Test Graph API connectivity
  try {
    const graphToken = await getGraphToken();
    await context.sendActivity(`✅ Graph API token obtained successfully`);
  } catch (err) {
    await context.sendActivity(`❌ Graph API token failed: ${err.message}`);
  }
});


async function sendCandidateCards(results, context) {
  const topResults = results.slice(0, 20);

  for (const candidate of topResults) {
    const name = candidate.name || "Unknown Candidate";
    const empId = candidate.employee_id || "N/A";
    const rawScore = typeof candidate.score === 'number' ? candidate.score : 0;
    const score = (rawScore * 100).toFixed(2); // e.g., 94.56

    // 🎨 Score color logic
    let scoreColor = "Good"; // green
    if (rawScore < 0.7) scoreColor = "Attention"; // red
    else if (rawScore < 0.9) scoreColor = "Warning"; // yellow

    const card = {
      type: "AdaptiveCard",
      version: "1.4",
      body: [
        {
          type: "TextBlock",
          size: "Large",
          weight: "Bolder",
          text: `👤 ${name}`
        },
        {
          type: "TextBlock",
          text: `🆔 Employee ID: ${empId}`,
          wrap: true
        },
        {
          type: "TextBlock",
          text: `⭐ Score: ${score}%`,
          wrap: true,
          color: scoreColor,
          weight: "Bolder"
        }
      ],
      actions: [
        {
          type: "Action.Submit",
          title: "👁️ View Resume",
          data: {
            msteams: {
              type: "messageBack",
              text: `/view ${empId}`
            }
          }
        }
      ],
      $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
    };

    await context.sendActivity({
      type: "message",
      attachments: [
        {
          contentType: "application/vnd.microsoft.card.adaptive",
          content: card
        }
      ]
    });
  }
}


teamsBot.message(/^(hi|hello|hey|\/help)$/i, async (context, state) => {
  await sendWelcomeCard(context);
});

// --- /search Command ---
teamsBot.message(/^\/search\s+(.*)/i, async (context, state) => {
  const query = context.activity.text.replace(/^\/search\s+/i, "").trim();

  if (!query) {
    await context.sendActivity("❗ Please provide a query after `/search`.");
    return;
  }

  try {
    const response = await axiosWithFallback("post", "/search", {
      data: { query },
      config: {
        headers: { "Content-Type": "application/json" },
        timeout: 60000
      }
    });

    const result = response.data;

    // if (!result || !result.results || result.results.length === 0) {
    //   await context.sendActivity("⚠️ No candidates found.");
    //   return;
    // }
    console.log("🔍 Found candidates:", result.length);
    await sendCandidateCards(result, context);

  } catch (error) {
    const errMsg = error.response?.data || error.message;
    await context.sendActivity(`❌ Search Candidates Error:\n\
\  ${errMsg}\  `);
  }
});


// Helper function to display resume card
async function displayResumeCard(context, fallbackData) {
  // Build card body with sections
  const cardBody = [];
  
  // Header section
  cardBody.push({
    type: "Container",
    style: "emphasis",
    bleed: true,
    items: [
      {
        type: "TextBlock",
        size: "ExtraLarge",
        weight: "Bolder",
        text: fallbackData.name || "Resume Data",
        color: "Warning",
        horizontalAlignment: "center"
      }
      // Removed warning text here
    ]
  });

  // Contact Information Section
  const contactItems = [];
  if (fallbackData.title) {
    contactItems.push({
      type: "TextBlock",
      text: fallbackData.title,
      size: "Medium",
      weight: "Bolder",
      color: "Accent"
    });
  }
  if (fallbackData.email) {
    contactItems.push({
              type: "TextBlock",
      text: `📧 ${fallbackData.email}`,
              wrap: true
    });
  }
  if (fallbackData.phone) {
    contactItems.push({
              type: "TextBlock",
      text: `📞 ${fallbackData.phone}`,
              wrap: true
    });
  }
  if (fallbackData.location) {
    contactItems.push({
              type: "TextBlock",
      text: `📍 ${fallbackData.location}`,
              wrap: true
    });
  }
  
  if (contactItems.length > 0) {
    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "📋 CONTACT INFORMATION",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        ...contactItems
      ]
    });
  }

  // Summary Section
  if (fallbackData.summary) {
    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "📝 PROFESSIONAL SUMMARY",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        {
          type: "TextBlock",
          text: fallbackData.summary,
          wrap: true,
          spacing: "Small"
        }
      ]
    });
  }

  // Skills Section
  if (fallbackData.skills?.length) {
    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "💡 TECHNICAL SKILLS",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        {
          type: "TextBlock",
          text: fallbackData.skills.join(" • "),
          wrap: true,
          spacing: "Small"
        }
      ]
    });
  }

  // Experience Section
  if (fallbackData.experience?.length) {
    const experienceItems = fallbackData.experience.map(exp => ({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: `🔹 ${exp.title}`,
          weight: "Bolder",
          size: "Medium"
        },
        {
          type: "TextBlock",
          text: `${exp.company} • ${exp.duration}${exp.location ? ` • ${exp.location}` : ""}`,
          isSubtle: true,
          size: "Small"
        },
        {
          type: "TextBlock",
          text: exp.description,
          wrap: true,
          spacing: "Small"
        }
      ],
      spacing: "Medium"
    }));

    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "💼 WORK EXPERIENCE",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        ...experienceItems
      ]
    });
  }

  // Education Section
  if (fallbackData.education?.length) {
    const educationItems = fallbackData.education.map(edu => ({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: `🎓 ${edu.degree}`,
          weight: "Bolder",
          size: "Medium"
        },
        {
          type: "TextBlock",
          text: `${edu.institution} • ${edu.year}`,
          isSubtle: true,
          size: "Small"
        }
      ],
      spacing: "Small"
    }));

    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "🎓 EDUCATION",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        ...educationItems
      ]
    });
  }

  // Projects Section
  if (fallbackData.projects?.length) {
    const projectItems = fallbackData.projects.map(project => ({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: `🚀 ${project.title}`,
          weight: "Bolder",
          size: "Medium"
        },
        {
          type: "TextBlock",
          text: project.description,
          wrap: true,
          spacing: "Small"
        }
      ],
      spacing: "Medium"
    }));

    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "🚀 PROJECTS",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        ...projectItems
      ]
    });
  }

  // Certifications Section
  if (fallbackData.certifications?.length) {
    const certificationItems = fallbackData.certifications.map(cert => ({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: `📜 ${cert.title}`,
          weight: "Bolder",
          size: "Medium"
        },
        {
          type: "TextBlock",
          text: `${cert.issuer ? cert.issuer : ""}${cert.year ? ` • ${cert.year}` : ""}`,
          isSubtle: true,
          size: "Small"
        }
      ],
      spacing: "Small"
    }));

    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "📜 CERTIFICATIONS",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        ...certificationItems
      ]
    });
  }

  // Social Profiles Section
  if (fallbackData.social_profiles?.length) {
    cardBody.push({
      type: "Container",
      items: [
        {
          type: "TextBlock",
          text: "🌐 SOCIAL PROFILES",
          size: "Medium",
          weight: "Bolder",
          color: "Accent",
          spacing: "Medium"
        },
        {
              type: "TextBlock",
          text: fallbackData.social_profiles.map(profile => `${profile.platform}: ${profile.link}`).join(" • "),
          wrap: true,
          spacing: "Small"
        }
      ]
    });
  }

  const card = {
    type: "AdaptiveCard",
    version: "1.4",
    body: cardBody,
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
        };

        await context.sendActivity({
          type: "message",
          attachments: [
            {
              contentType: "application/vnd.microsoft.card.adaptive",
              content: card
            }
          ]
        });
  }

const { getGraphToken } = require("./utils/graphToken");
teamsBot.message("/makeresume", async (context, state) => {


  const text = context.activity.text || "";
  const args = text.replace(/^\/makeresume\s*/i, "").trim();

  let identifier_type, identifier, job_description;

  // If 'jd' is present, split args at 'jd' (case-insensitive)
  let mainPart = args;
  let jdMatch = args.match(/\bjd\b\s*(.*)$/i);
  if (jdMatch) {
    job_description = jdMatch[1].replace(/^"|"$/g, '').trim();
    mainPart = args.substring(0, jdMatch.index).trim();
  }

  // Try to extract identifier_type and identifier from mainPart
  // Accepts: name <name>, employee_id <id>, <id>, <name>
  let idMatch = mainPart.match(/^(name|employee_id)\s+(.+)$/i);
  if (idMatch) {
    identifier_type = idMatch[1].toLowerCase();
    identifier = idMatch[2].trim();
  } else if (/^\d+$/.test(mainPart) && mainPart.length > 0) {
    identifier_type = "employee_id";
    identifier = mainPart;
  } else if (mainPart.length > 0) {
    identifier_type = "name";
    identifier = mainPart;
  }

  // If nothing is provided, prompt user
  if (!identifier_type && !job_description) {
    await context.sendActivity("Please provide at least an identifier (name/employee_id) or a job description after jd.\nExample: /makeresume John Doe jd \"Job description\" or /makeresume jd \"Job description only\"");
    return;
  }

  // Build payload
  const payload = {};
  if (identifier_type && identifier) {
    payload.identifier_type = identifier_type;
    payload.identifier = identifier;
  }
  if (job_description) {
    payload.job_description = job_description;
  }

  // Ensure we have at least one identifier or job description
  if (!payload.identifier_type && !payload.job_description) {
    await context.sendActivity("❗ Please provide at least an identifier (name/employee_id) or a job description.\nExample: `/makeresume John Dow` or `/makeresume jd \"Software Engineer\"`");
    return;
  }

  try {
    // User-friendly loader for single-candidate or JD flow
    if (identifier_type && identifier && job_description) {
      await context.sendActivity('🔍 Looking for candidate...');
      await new Promise(resolve => setTimeout(resolve, 2000));
      await context.sendActivity('🛠️ Retailoring resume for the job description...');
      await new Promise(resolve => setTimeout(resolve, 3000));
      await context.sendActivity('⏳ Generating tailored resume...');
    } else if (identifier_type && identifier) {
      await context.sendActivity('🔍 Looking for candidate...');
      await new Promise(resolve => setTimeout(resolve, 2000));
      await context.sendActivity('⏳ Generating resume...');
    } else if (job_description && !identifier_type) {
      await context.sendActivity('🔍 Searching candidates...');
      await new Promise(resolve => setTimeout(resolve, 2000));
      await context.sendActivity('📊 Evaluating and scoring candidates...');
    }
    // First, try to get binary response from NIFI processor
    const response = await axiosWithFallback("post", "/makeresume", {
      data: payload,
      config: {
        responseType: "arraybuffer",
        headers: { "Content-Type": "application/json" },
        timeout: 600000
      }
    });

    // Extract JSON resume data from headers
    let resumeJsonData = null;
    try {
      // Try to extract JSON resume from headers (check common header names)
      const possibleJsonHeaders = [
        'resume-json',
        'x-resume-json', 
        'resume-data',
        'x-resume-data',
        'json-data'
      ];
      
      let jsonFromHeaders = null;
      for (const headerName of possibleJsonHeaders) {
        if (response.headers[headerName]) {
          jsonFromHeaders = response.headers[headerName];
          break;
        }
      }
      
      if (jsonFromHeaders) {
        // Try to parse the JSON from headers
        if (typeof jsonFromHeaders === 'string') {
          resumeJsonData = JSON.parse(jsonFromHeaders);
        } else {
          resumeJsonData = jsonFromHeaders;
        }
      } else {
        // Try to extract individual fields from headers
        const candidateName = response.headers['resume-name'] || response.headers['x-resume-name'] || response.headers['candidate-name'];
        const candidateEmail = response.headers['resume-email'] || response.headers['x-resume-email'] || response.headers['candidate-email'];
        
        if (candidateName) {
          // Build basic resume data from headers
          resumeJsonData = {
            name: candidateName,
            email: candidateEmail || 'Not provided',
            // Add other fields from headers as needed
          };
        }
      }
    } catch (headerParseErr) {
      // Silent fallback
    }

    // Check if we received a valid binary response (Word document)
    if (response.data && response.data.byteLength > 0) {
      const buffer = Buffer.from(response.data);
      
      // Try to detect if this is actually a Word document or JSON
      const firstBytes = buffer.slice(0, 4);
      const isWordDoc = firstBytes[0] === 0x50 && firstBytes[1] === 0x4B; // ZIP signature (Word docs are ZIP files)
      
      if (isWordDoc) {
        // This is a genuine Word document - proceed with upload
        if (context.activity.channelId === 'emulator') {
          await context.sendActivity("✅ Resume generated! (Teams Playground mode - file would be uploaded to OneDrive in production)");
          await context.sendActivity(`📄 File size: ${(buffer.length / 1024).toFixed(2)} KB`);
          await context.sendActivity("ℹ️ In production Teams, this would be uploaded to OneDrive and available for download.");
          if (resumeJsonData) {
            await context.sendActivity(`📋 Backup JSON Data: Available (${Object.keys(resumeJsonData).length} fields)`);
          }
        } else if (context.activity.conversation.conversationType === 'personal') {
          const timestamp = Date.now();
          const filename = `resume-${timestamp}.docx`;
          state.conversation.pendingWordBuffer = buffer.toString('base64');
          state.conversation.pendingWordFilename = filename;
          state.conversation.pendingWordSize = buffer.length;
    await context.sendActivity({
      type: "message",
      attachments: [
        {
          contentType: "application/vnd.microsoft.teams.card.file.consent",
                name: filename,
          content: {
                  description: "Resume document generated by HR Bot",
                  sizeInBytes: buffer.length,
                  acceptContext: { resume: true },
                  declineContext: { resume: true }
          }
        }
      ]
    });
          await context.sendActivity('✅ Resume generated!');
          if (resumeJsonData) {
            await context.sendActivity(`📋 Backup JSON Data: Available (${Object.keys(resumeJsonData).length} fields)`);
          }
        } else {
          await context.sendActivity("⚠️ File upload is only available in personal chat. Here is the resume data:");
          if (resumeJsonData) {
            await displayResumeCard(context, resumeJsonData);
          } else if (identifier_type && identifier) {
            await context.sendActivity('No resume data available to display. Attempting to fetch candidate profile...');
            await fetchAndDisplayViewCard(context, identifier_type, identifier);
          } else {
            await context.sendActivity(`❌ No resume data available to display.`);
          }
        }
      } else {
        // This might be JSON data in the body instead of headers - try to parse it
        try {
          const jsonString = buffer.toString('utf8');
          const jsonData = JSON.parse(jsonString);
          
          // If JD-only and array, show all candidates as simple cards
          if (!identifier_type && Array.isArray(jsonData)) {
            await context.sendActivity('🔍 Searching candidates...');
            await context.sendActivity('📊 Evaluating and scoring candidates...');
            // Only show candidates with score > 70
            const filteredCandidates = jsonData.filter(c => (c.score || 0) > 70);
            if (filteredCandidates.length === 0) {
              await context.sendActivity('⚠️ No candidates with a score above 70 were found for this job description.');
            } else {
              // Sort candidates by score in descending order
              const sortedCandidates = filteredCandidates.sort((a, b) => (b.score || 0) - (a.score || 0));
              await context.sendActivity('✅ Found ' + sortedCandidates.length + ' candidates for this job description:');
              for (const candidate of sortedCandidates) {
                await sendSimpleCandidateCard(context, candidate, job_description);
              }
            }
          } else {
            // Use JSON data from body, or headers if available
            const finalJsonData = resumeJsonData || jsonData;
            await context.sendActivity('⏳ Generating tailored resume...');
            await displayResumeCard(context, finalJsonData);
          }
          
        } catch (parseErr) {
          // Use JSON data from headers as final fallback
          if (resumeJsonData) {
            await context.sendActivity('⏳ Generating tailored resume...');
            await displayResumeCard(context, resumeJsonData);
          } else if (identifier_type && identifier) {
            await context.sendActivity('No resume data available to display. Attempting to fetch candidate profile...');
            await fetchAndDisplayViewCard(context, identifier_type, identifier);
          } else {
            await context.sendActivity(`❌ Could not generate resume. Please try again later.`);
          }
        }
      }
    } else {
      // No binary data received - use JSON from headers if available
      if (resumeJsonData) {
        await displayResumeCard(context, resumeJsonData);
      } else if (identifier_type && identifier) {
        await context.sendActivity('No resume data available to display. Attempting to fetch candidate profile...');
        await fetchAndDisplayViewCard(context, identifier_type, identifier);
      } else {
        throw new Error("Empty response received with no JSON data in headers");
      }
    }

  } catch (err) {
    // Try to get JSON fallback response
    let fallbackData = null;
    let fallbackText = "Resume generation failed.";

    try {
      // Attempt to get JSON response instead of binary
      const jsonResponse = await axiosWithFallback("post", "/makeresume", {
        data: payload,
        config: {
          headers: { "Content-Type": "application/json" },
          timeout: 600000
        }
      });

      if (jsonResponse.data && typeof jsonResponse.data === "object") {
        fallbackData = jsonResponse.data;
      } else if (typeof jsonResponse.data === "string") {
        fallbackData = JSON.parse(jsonResponse.data);
      }
    } catch (jsonErr) {
      // Try alternative payload format
      try {
        const altPayload = {
          name: payload.identifier_type === "name" ? payload.identifier : undefined,
          employee_id: payload.identifier_type === "employee_id" ? payload.identifier : undefined,
          job_description: payload.job_description
        };
        
        const jsonResponse = await axiosWithFallback("post", "/makeresume", {
          data: payload,
          config: {
            headers: { "Content-Type": "application/json" },
            timeout: 600000
          }
        });
        
        if (altResponse.data && typeof altResponse.data === "object") {
          fallbackData = altResponse.data;
        } else if (typeof altResponse.data === "string") {
          fallbackData = JSON.parse(altResponse.data);
        }
      } catch (altErr) {
        // If JSON request also fails, try to parse error response
        try {
          const errorResponse = err?.response?.data;
          if (errorResponse) {
            if (typeof errorResponse === "string") {
              fallbackData = JSON.parse(errorResponse);
            } else if (typeof errorResponse === "object") {
              fallbackData = errorResponse;
            }
          }
        } catch (parseErr) {
          fallbackText = err?.response?.data?.toString?.() || err.message || "Resume generation failed.";
        }
      }
    }

    // Display fallback adaptive card if we have valid JSON data
    if (fallbackData && typeof fallbackData === "object") {
      if (!identifier_type && Array.isArray(fallbackData)) {
        await context.sendActivity('🔍 Searching candidates...');
        await new Promise(resolve => setTimeout(resolve, 2000));
        await context.sendActivity('📊 Evaluating and scoring candidates...');
        // Only show candidates with score > 70
        const filteredCandidates = fallbackData.filter(c => (c.score || 0) > 70);
        if (filteredCandidates.length === 0) {
          await context.sendActivity('⚠️ No candidates with a score above 70 were found for this job description.');
        } else {
          // Sort candidates by score in descending order
          const sortedCandidates = filteredCandidates.sort((a, b) => (b.score || 0) - (a.score || 0));
          await context.sendActivity('✅ Found ' + sortedCandidates.length + ' candidates for this job description:');
          for (const candidate of sortedCandidates) {
            await sendSimpleCandidateCard(context, candidate, job_description);
          }
        }
      } else if (fallbackData.name || fallbackData.skills || fallbackData.experience) {
        await context.sendActivity('⏳ Generating tailored resume...');
        await displayResumeCard(context, fallbackData);
      } else {
        await context.sendActivity(`❌ Resume generation failed. Please try again later.`);
        await context.sendActivity(`📊 Error Details: \`${fallbackText}\``);
        if (identifier_type && identifier) {
          await context.sendActivity('Attempting to fetch candidate profile as fallback...');
          await fetchAndDisplayViewCard(context, identifier_type, identifier);
        }
      }
    } else {
      // Final fallback - show error message
      await context.sendActivity({
        type: "message",
        attachments: [
          {
            contentType: "application/vnd.microsoft.card.adaptive",
            content: {
              type: "AdaptiveCard",
              version: "1.4",
              body: [
                {
                  type: "TextBlock",
                  text: "❌ Resume Generation Failed",
                  size: "Large",
                  weight: "Bolder",
                  color: "Attention",
                  wrap: true
                },
                {
                  type: "TextBlock",
                  text: fallbackText,
                  wrap: true
                },
                {
                  type: "TextBlock",
                  text: "Please verify the candidate information or try again later.",
                  wrap: true,
                  spacing: "Small"
                }
              ],
              $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
            }
          }
        ]
      });
    }
  }

});

// Helper: Send a simple candidate card for JD-only /makeresume
async function sendSimpleCandidateCard(context, candidate, jobDescription) {
        const card = {
          type: "AdaptiveCard",
          version: "1.4",
          body: [
      {
              type: "TextBlock",
        size: "Large",
        weight: "Bolder",
        text: `👤 ${candidate.name || "Unknown"}`
      },
      {
        type: "TextBlock",
        text: `🆔 Employee ID: ${candidate.employee_id ?? "N/A"}`,
              wrap: true
      },
      {
              type: "TextBlock",
        text: `📊 Score: ${candidate.score ?? "N/A"}`,
              wrap: true
      },    
      {
              type: "TextBlock",
        text: `🔑 Keywords: ${(candidate.keywords || []).join(", ")}`,
              wrap: true
      }
    ],
    actions: [
      {
        type: "Action.Submit",
        title: "📄 Generate Resume",
        data: {
          msteams: {
            type: "messageBack",
            text: `/makeresume employee_id ${candidate.employee_id} jd "${jobDescription}"`
          }
        }
      }
    ],
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
        };
        await context.sendActivity({
          type: "message",
          attachments: [
            {
              contentType: "application/vnd.microsoft.card.adaptive",
              content: card
            }
          ]
        });
}

// Enhanced /view command: supports employee ID or name
teamsBot.message(/^\/view(?:\s+(.*))?$/i, async (context, state) => {

  const text = context.activity.text;
  const args = text.replace(/^\/view\s*/i, "").trim();

  let identifier_type = "";
  let identifier = "";

  if (!args) {
    await context.sendActivity("❗ Please provide an employee ID or a name after `/view`.\nExamples:\n- `/view 12345`\n- `/view John Doe`");
    return;
  }

  // If "name" keyword is present, extract name after it
  const nameMatch = args.match(/name\s+([^\d][^\n\r]*)/i);
  if (nameMatch) {
    identifier_type = "name";
    identifier = nameMatch[1].trim();
  } else if (/^\d+$/.test(args)) {
    identifier_type = "employee_id";
    identifier = args;
      } else {
    identifier_type = "name";
    identifier = args;
  }

  if (!identifier) {
    await context.sendActivity("❗ Please provide an employee ID or a name after `/view`.\nExamples:\n- `/view 12345`\n- `/view John Doe`");
    return;
  }

  try {
    await context.sendActivity({ type: 'typing' });
    await context.sendActivity('🔍 Looking for candidate...');
    // Build payload exactly like /makeresume
    const payload = { identifier_type, identifier };
    if (!payload.identifier_type || !payload.identifier) {
      await context.sendActivity("❗ Please provide a valid employee ID or name after `/view`.");
      return;
    }
    const response = await axiosWithFallback("post", "/view", {
      data: payload,
      config: {
        headers: { "Content-Type": "application/json" },
        timeout: 20000
      }
    });
    

    let resumeData = response.data;
    if (typeof resumeData === "string") {
      try {
        resumeData = JSON.parse(resumeData);
      } catch (e) {
        await context.sendActivity(`❌ Could not parse resume data. Raw response: \n\n\`${resumeData}\``);
        return;
      }
    }

    if (!resumeData || (!resumeData.name && !resumeData.skills && !resumeData.experience)) {
      await context.sendActivity("❌ Candidate not found in database.");
      return;
    }

    await context.sendActivity('✅ Found candidate! Displaying resume...');
    await displayResumeCard(context, resumeData);
  } catch (err) {
    let errMsg = err.response?.data || err.message;
    if (typeof errMsg === "object") {
      errMsg = JSON.stringify(errMsg, null, 2);
    }
    await context.sendActivity({
      type: "message",
      attachments: [
        {
          contentType: "application/vnd.microsoft.card.adaptive",
          content: {
            type: "AdaptiveCard",
            version: "1.4",
            body: [
              {
                type: "TextBlock",
                text: `❌ Candidate Lookup Failed`,
                size: "Large",
                weight: "Bolder",
                color: "Attention",
                wrap: true
              },
              {
                type: "TextBlock",
                text: errMsg || "Unknown error",
                wrap: true
              },
              {
                type: "TextBlock",
                text: "Please check the employee ID or name and try again.",
                wrap: true,
                spacing: "Small"
              }
            ],
            $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
          }
        }
      ]
    });
  }

});




// Enhanced /delete command: supports employee ID or name
teamsBot.message(/^\/delete(?:\s+(.*))?$/i, async (context, state) => {
  const args = context.activity.text.replace(/^\/delete\s*/i, "").trim();

  let employeeId = "";
  let name = "";

  const nameMatch = args.match(/name\s+([^\d][^\n\r]*)/i);
  if (nameMatch) {
    name = nameMatch[1].trim();
    const idMatch = args.match(/(^|\s)(\d+)(\s|$)/);
    if (idMatch) {
      employeeId = idMatch[2].trim();
    }
  } else {
    if (/^\d+$/.test(args)) {
      employeeId = args;
    } else {
      name = args;
    }
  }

  if (!employeeId && !name) {
    await context.sendActivity("❗ Usage: `/delete <employee_id>` or `/delete name John Doe`");
    return;
  }

  try {
    const payload = { employee_id: employeeId, name };
    const response = await axiosWithFallback("post", "/delete", {
      data: payload,
      config: { headers: { "Content-Type": "application/json" }, timeout: 60000 }
    });

    const result = response.data;
    if (result?.status === "success") {
      await context.sendActivity(`✅ Candidate deleted successfully.`);
    } 
    if (result?.status === "not_found") {
      await context.sendActivity(`Candidate Not found in the database.`);
    }
  } catch (err) {
    await context.sendActivity(`❌ Failed to delete candidate: ${err.message}`);
  }
});



teamsBot.message("/add", async (context, state) => {
   
  // Show spinner card
  await context.sendActivity({
    type: "message",
    attachments: [
      {
        contentType: "application/vnd.microsoft.card.adaptive",
        content: {
          type: "AdaptiveCard",
          version: "1.4",
          body: [
            {
              type: "TextBlock",
              text: "⏳ Processing your request, please wait...",
              size: "Medium",
              weight: "Bolder",
              color: "Accent",
              wrap: true
            }
          ],
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
        }
      }
    ]
  });
  const parts = context.activity.text.trim().split(" ");
  const employeeId = parts[1];

  if (!employeeId) {
    await context.sendActivity("How to use?: `/add <employee_id>`");
    return;
  }

  state.conversation.awaitingLink = true;
  state.conversation.addEmployeeId = employeeId;
  await context.sendActivity(`Please enter the SharePoint resume link for employee ID *${employeeId}*.`);

});

teamsBot.message(/^\/uploadfolder(\s|$)/, async (context, state) => {
   
  console.log("[BOT] /uploadfolder triggered:", context.activity.text);

  const parts = context.activity.text.trim().split(" ");
  const folderLink = parts[1];

  if (!folderLink || !folderLink.startsWith("http") || !folderLink.includes("sharepoint.com")) {
    await context.sendActivity({
      type: "message",
      attachments: [{
        contentType: "application/vnd.microsoft.card.adaptive",
        content: {
          type: "AdaptiveCard",
          version: "1.4",
          body: [
            {
              type: "TextBlock",
              text: "⚠️ Invalid or missing SharePoint folder link.",
              wrap: true,
              color: "Warning"
            },
            {
              type: "TextBlock",
              text: "**Usage:** `/uploadfolder <sharepoint_folder_link>`\n\nMake sure the folder contains resumes named like `employee_id.pdf`.",
              wrap: true
            }
          ],
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
        }
      }]
    });
    return;
  }

  await context.sendActivity({
    type: "message",
    attachments: [{
      contentType: "application/vnd.microsoft.card.adaptive",
      content: {
        type: "AdaptiveCard",
        version: "1.4",
        body: [
          {
            type: "TextBlock",
            text: "📂 Uploading resumes from the SharePoint folder. Please wait...",
            size: "Large",
            weight: "Bolder",
            color: "Accent",
            wrap: true
          }
        ],
        $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
      }
    }]
  });

  try {
    const response = await axiosWithFallback("post", "/bulk", {
      data: { folder_link: folderLink },
      config: {
        headers: { "Content-Type": "application/json" }
      }
    });
    const processedCount = response.data.processed ?? "All";

    await context.sendActivity({
      type: "message",
      attachments: [{
        contentType: "application/vnd.microsoft.card.adaptive",
        content: {
          type: "AdaptiveCard",
          version: "1.4",
          body: [
            {
              type: "TextBlock",
              text: "✅ Bulk Upload Completed",
              size: "ExtraLarge",
              weight: "Bolder",
              color: "Good",
              wrap: true
            },
            {
              type: "TextBlock",
              text: `${processedCount} resumes were successfully processed from the SharePoint folder.`,
              wrap: true
            }
          ],
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
        }
      }]
    });

  } catch (error) {
    console.error("Upload folder error:", error.message);

    await context.sendActivity({
      type: "message",
      attachments: [{
        contentType: "application/vnd.microsoft.card.adaptive",
        content: {
          type: "AdaptiveCard",
          version: "1.4",
          body: [
            {
              type: "TextBlock",
              text: "❌ Upload Failed",
              size: "Large",
              weight: "Bolder",
              color: "Attention",
              wrap: true
            },
            {
              type: "TextBlock",
              text: error.message || "Unknown error occurred while uploading folder.",
              wrap: true
            }
          ],
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
        }
      }]
    });
  }

});

async function sendUnknownMessageWithCommands(context) {
  const card = {
    type: "AdaptiveCard",
    version: "1.4",
    body: [
      {
        type: "TextBlock",
        text: "❓ Sorry, I couldn't understand your message.",
        size: "Large",
        weight: "Bolder",
        color: "Attention",
        wrap: true
      },
      {
        type: "TextBlock",
        text: "Please choose one of the available commands below:",
        size: "Medium",
        weight: "Bolder",
        wrap: true,
        spacing: "Medium"
      },
      {
        type: "FactSet",
        facts: [
          { title: "/makeresume", value: "Generate a resume for a candidate (with or without job description)." },
          { title: "/search", value: "Search for candidates using a query" },
          { title: "/view", value: "View a candidate's resume by employee ID or name." },
          { title: "/delete", value: "Delete a candidate by employee ID or name." },
          { title: "/uploadfolder", value: "Upload onedrive folder containing resumes" },
          { title: "/add", value: "Add a SharePoint resume link for a candidate." }
        ]
      },
      {
        type: "TextBlock",
        text: "Quick Actions:",
        size: "Medium",
        weight: "Bolder",
        spacing: "Large"
      }
    ],
    actions: [
      {
        type: "Action.Submit",
        title: "/makeresume",
        data: { msteams: { type: "messageBack", text: "/makeresume", displayText: "/makeresume" } }
      },
      {
        type: "Action.Submit",
        title: "/search",
        data: { msteams: { type: "messageBack", text: "/search", displayText: "/search"  } }
      },
      {
        type: "Action.Submit",
        title: "/view",
        data: { msteams: { type: "messageBack", text: "/view", displayText: "/view"   } }
      },
      {
        type: "Action.Submit",
        title: "/delete",
        data: { msteams: { type: "messageBack", text: "/delete",displayText: "/delete"   } }
      },
      {
        type: "Action.Submit",
        title: "/uploadfolder",
        data: { msteams: { type: "messageBack", text: "/uploafolder",displayText: "/uploadfolder"   } }
      },
      {
        type: "Action.Submit",
        title: "/add",
        data: { msteams: { type: "messageBack", text: "/add",displayText: "/add" } }
      },
      {
        type: "Action.Submit",
        title: "/help",
        data: { msteams: { type: "messageBack", text: "/help",displayText:"/help" } }
      }
    ],
    $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
  };

  await context.sendActivity({
    type: "message",
    attachments: [
      {
        contentType: "application/vnd.microsoft.card.adaptive",
        content: card
      }
    ]
  });
}


teamsBot.activity(ActivityTypes.Message, async (context, state) => {
  const text = context.activity.text?.trim();

  // Step 2: Handle resume link input
  if (state.conversation.awaitingLink) {
    // Try to extract from text first
    const urlRegex = /@?(https?:\/\/[^\s<>"]+)/i;
    let link = null;
    if (text) {
      const match = text.match(urlRegex);
      link = match && match[1] ? match[1].trim() : null;
    }
    // If not found in text, check attachments
    if (!link && context.activity.attachments && context.activity.attachments.length > 0) {
      const attachment = context.activity.attachments[0];
      // Case 1: contentUrl (for some file types)
      if (attachment.contentUrl && attachment.contentUrl.includes('sharepoint.com')) {
        link = attachment.contentUrl;
      }
      // Case 2: HTML content with <a href="...">
      else if (
        attachment.contentType === 'text/html' &&
        typeof attachment.content === 'string'
      ) {
        // Extract href from <a ...> in HTML
        const hrefMatch = attachment.content.match(/href="([^"]+)"/i);
        if (hrefMatch && hrefMatch[1] && hrefMatch[1].includes('sharepoint.com')) {
          link = hrefMatch[1];
        }
      }
    }
    if (link && link.includes('sharepoint.com')) {
      state.conversation.resumeLink = link;
      state.conversation.awaitingConfirmation = true;
      state.conversation.awaitingLink = false;
      await context.sendActivity(
        `You entered:\n\n- **Employee ID:** ${state.conversation.addEmployeeId}\n- **Resume Link:** ${link}\n\nType **yes** to confirm or **no** to cancel.`
      );
    } else {
      await context.sendActivity("❗ Please paste a valid SharePoint link.");
    }
    return;
  }

  // Step 3: Handle confirmation
  if (state.conversation.awaitingConfirmation) {
    if (text.toLowerCase() === "yes") {
      // Show spinner card for uploading
      await context.sendActivity({
        type: "message",
        attachments: [
          {
            contentType: "application/vnd.microsoft.card.adaptive",
            content: {
              type: "AdaptiveCard",
              version: "1.4",
              body: [
                {
                  type: "TextBlock",
                  text: "⏳ Uploading resume, please wait...",
                  size: "Large",
                  weight: "Bolder",
                  color: "Accent",
                  wrap: true
                }
              ],
              $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
            }
          }
        ]
      });
      // Call API
      try {
        const payload = {
          employee_id: state.conversation.addEmployeeId,
          resume_link: state.conversation.resumeLink,
        };

        // Log the payload being sent to NiFi

        const response = await axiosWithFallback("post", "/add", {
          data: payload,
          config: { headers: { "Content-Type": "application/json" } }
        });

        const filteredData = { ...response.data };
        delete filteredData.document_id;

        await context.sendActivity({
          type: "message",
          attachments: [
            {
              contentType: "application/vnd.microsoft.card.adaptive",
              content: {
                type: "AdaptiveCard",
                version: "1.4",
                body: [
                  {
                    type: "TextBlock",
                    text: "✅ Candidate Added Successfully!",
                    size: "ExtraLarge",
                    weight: "Bolder",
                    color: "Good",
                    wrap: true,
                    horizontalAlignment: "Center",
                    spacing: "Large"
                  },
            
                ],
                actions: [
                  {
                  type: "Action.Submit",
                  title: "👁️ View Resume",
                  data: {
                  employee_id: state.conversation.addEmployeeId,
                  msteams: {
                      type: "messageBack",
                      text: `/view ${state.conversation.addEmployeeId}`
                    }
                  }
                }
                ],
                $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
              }
            }
          ]
        });

      } catch (error) {
        await context.sendActivity({
          type: "message",
          attachments: [
            {
              contentType: "application/vnd.microsoft.card.adaptive",
              content: {
                type: "AdaptiveCard",
                version: "1.4",
                body: [
                  {
                    type: "TextBlock",
                    text: "❌ File Upload Failed",
                    size: "Large",
                    weight: "Bolder",
                    color: "Attention",
                    wrap: true
                  },
                  {
                    type: "TextBlock",
                    text: error.message || "Unknown error",
                    wrap: true
                  },
                  {
                    type: "TextBlock",
                    text: "Please try again later or contact support if the issue persists.",
                    wrap: true,
                    spacing: "Small"
                  }
                ],
                $schema: "http://adaptivecards.io/schemas/adaptive-card.json"
              }
            }
          ]
        });
      }
    } else {
      await context.sendActivity("❌ Operation cancelled.");
    }

    // Clear conversation state
    delete state.conversation.awaitingConfirmation;
    delete state.conversation.addEmployeeId;
    delete state.conversation.resumeLink;
  }
});


// Helper: Send unknown message fallback with command list


// -------------------------------------------------------------------------------
// Activity Handlers

// Handle file consent invoke activity for file upload
teamsBot.activity("invoke", async (context, state) => {
  if (
    context.activity.name === "fileConsent/invoke" &&
    context.activity.value &&
    context.activity.value.action === "accept"
  ) {
    const uploadUrl = context.activity.value.uploadInfo.uploadUrl;
    const fileName = context.activity.value.uploadInfo.name;
    // Retrieve the buffer and filename from state
    const bufferBase64 = state.conversation.pendingWordBuffer;
    const buffer = Buffer.from(bufferBase64, 'base64');
    // Debug: log first 100 bytes of buffer
    console.log('First 100 bytes of buffer:', buffer.slice(0, 100));
    try {
      if (uploadUrl.includes('/uploadSession')) {
        // Use Content-Range header for upload session
        const totalSize = buffer.length;
        await axios.put(uploadUrl, buffer, {
          headers: {
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "Content-Range": `bytes 0-${totalSize - 1}/${totalSize}`
          },
          maxContentLength: Infinity,
          maxBodyLength: Infinity
        });
      } else {
        // Simple upload
        await axios.put(uploadUrl, buffer, {
          headers: {
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          },
          maxContentLength: Infinity,
          maxBodyLength: Infinity
        });
      }
      // Send a confirmation message with a file info card
      await context.sendActivity({
        type: "message",
        attachments: [
          {
            contentType: "application/vnd.microsoft.teams.card.file.info",
            contentUrl: context.activity.value.uploadInfo.contentUrl,
            name: fileName,
            content: {
              uniqueId: context.activity.value.uploadInfo.uniqueId,
              fileType: "docx"
            }
          }
        ]
      });
    } catch (err) {
      await context.sendActivity(`❌ **DEBUG:** Failed to upload file to Teams-provided uploadUrl: ${err.message}`);
      if (err.response?.data) {
        await context.sendActivity(`❌ Graph API error details: ${JSON.stringify(err.response.data)}`);
      }
    }
    // Clean up state
    state.conversation.pendingWordBuffer = undefined;
    state.conversation.pendingWordFilename = undefined;
    state.conversation.pendingWordSize = undefined;
  } else if (
    context.activity.name === "fileConsent/invoke" &&
    context.activity.value &&
    context.activity.value.action === "decline"
  ) {
    await context.sendActivity("File upload declined by user.");
    // Clean up state
    state.conversation.pendingWordBuffer = undefined;
    state.conversation.pendingWordFilename = undefined;
    state.conversation.pendingWordSize = undefined;
  }
});

teamsBot.conversationUpdate("membersAdded", async (context, state) => {
  await sendWelcomeCard(context);
});

// Helper: Fetch and display /view card as fallback
async function fetchAndDisplayViewCard(context, identifier_type, identifier) {
  try {
    await context.sendActivity('🔍 Fetching candidate profile as fallback...');

    const payload = { identifier_type, identifier };
    const response = await axiosWithFallback("post", "/view", {
      data: payload,
      config: {
        headers: { "Content-Type": "application/json" },
        timeout: 20000
      }
    });
    let resumeData = response.data;
    if (typeof resumeData === "string") {
      try {
        resumeData = JSON.parse(resumeData);
      } catch (e) {
        await context.sendActivity(`❌ Could not parse resume data. Raw response: \n\n\`${resumeData}\``);
        return;
      }
    }
    if (!resumeData || (!resumeData.name && !resumeData.skills && !resumeData.experience)) {
      await context.sendActivity("❌ Candidate not found in database.");
      return;
    }
    await context.sendActivity('✅ Found candidate! Displaying resume...');
    await displayResumeCard(context, resumeData);
  } catch (err) {
    let errMsg = err.response?.data || err.message;
    if (typeof errMsg === "object") {
      errMsg = JSON.stringify(errMsg, null, 2);
    }
    await context.sendActivity(`❌ Error while searching for candidate as fallback: \n\n\`${errMsg}\``);
  }
}

teamsBot.activity(
  async (context) => Promise.resolve(context.activity.type === "message"),
  async (context, state) => {
    await context.sendActivity(`Matched function: ${context.activity.type}`);
  }
);


module.exports.teamsBot = teamsBot;
