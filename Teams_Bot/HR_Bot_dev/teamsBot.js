const axios = require("axios");
const FormData = require("form-data");
const fs = require("fs");
const path = require("path");

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

// Listen for user to say '/reset' and then delete conversation state
teamsBot.message("/reset", async (context, state) => {
  state.deleteConversationState();
  await context.sendActivity("Ok I've deleted the current conversation state.");
});

teamsBot.message("/count", async (context, state) => {
  const count = state.conversation.count ?? 0;
  await context.sendActivity(`The count is ${count}`);
});

teamsBot.message("/diag", async (context, state) => {
  await state.load(context, storage);
  await context.sendActivity(JSON.stringify(context.activity));
});

teamsBot.message("/state", async (context, state) => {
  await state.load(context, storage);
  await context.sendActivity(JSON.stringify(state));
});

teamsBot.message("/runtime", async (context, state) => {
  const runtime = {
    nodeversion: process.version,
    sdkversion: version,
  };
  await context.sendActivity(JSON.stringify(runtime));
});

// Test command to check environment and connectivity
teamsBot.message("/test", async (context, state) => {
  try {
    // Test basic connectivity
    const testResponse = await axios.get("http://104.208.162.61:8083/", {
      timeout: 5000
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
 
  for (const r of topResults) {
    const rawText = r.text || "";
    let name = r.name || "";
    let empId = r.employee_id || r.filename?.replace(".txt", "") || "";
    let summary = r.summary || "";
    let phone = r.phone || "";
    let email = r.email || "";

    // Fallback extraction from rawText if fields are missing
    if (!name) {
      const nameMatch = rawText.match(/name\s*=\s*([^,}]+)/i);
      if (nameMatch) name = nameMatch[1].trim();
    }
    if (!empId) {
      const idMatch = rawText.match(/employee_id\s*=\s*([^,}]+)/i);
      if (idMatch) empId = idMatch[1].trim();
    }
    if (!summary) {
      const summaryMatch = rawText.match(/summary\s*=\s*([^,}]+)/i);
      if (summaryMatch) summary = summaryMatch[1].trim();
    }
    if (!phone) {
      const phoneMatch = rawText.match(/phone\s*=\s*([^,}]+)/i);
      if (phoneMatch) phone = phoneMatch[1].trim();
    }
    if (!email) {
      const emailMatch = rawText.match(/email\s*=\s*([^,}]+)/i);
      if (emailMatch) email = emailMatch[1].trim();
    }

    const card = {
      type: "AdaptiveCard",
      version: "1.4",
      body: [
        {
          type: "TextBlock",
          size: "Large",
          weight: "Bolder",
          text: `👤 ${name || "Unknown"}`
        },
        {
          type: "TextBlock",
          text: `🆔 Employee ID: ${empId || "N/A"}`,
          wrap: true
        },
        summary && {
          type: "TextBlock",
          text: `📝 Summary: ${summary}`,
          wrap: true
        },
        phone && {
          type: "TextBlock",
          text: `📞 Phone: ${phone}`,
          wrap: true
        },
        email && {
          type: "TextBlock",
          text: `📧 Email: ${email}`,
          wrap: true
        }
      ].filter(Boolean),
      actions: [
        {
          type: "Action.Submit",
          title: "👁️ View Resume",
          data: {
            msteams: {
              type: "messageBack",
              text: empId ? `/view ${empId}` : `/view ${name}`
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

 
// --- Main Feature: /search_candidates ---
teamsBot.message(/^\/search_candidates\s+(.*)/i, async (context, state) => {
  const query = context.activity.text.replace(/^\/search_candidates\s+/i, "").trim();
 
  if (!query) {
    await context.sendActivity("❗ Please provide a query after `/search_candidates`.");
    return;
  }
 
  await context.sendActivity('🔍 Searching candidates...');
  await context.sendActivity('📊 Evaluating and scoring candidates...');
 
  try {
    const response = await axios.post("http://104.208.162.61:8083/search_candidates", {
      query
    }, {
      headers: { "Content-Type": "application/json" },
      timeout: 30000
    });
 
    const result = response.data;
 
    if (!result || !result.results || result.results.length === 0) {
      await context.sendActivity("⚠️ No candidates found.");
      return;
    }
 
    // Sort by score descending if available
    const topResults = result.results
      .slice(0, 20)
      .sort((a, b) => (b.score || 0) - (a.score || 0));

    await context.sendActivity(`✅ Found ${topResults.length} candidates:`);
 
    for (const r of topResults) {
      // Try to extract fields for the card
      let name = r.name || "Unknown";
      let empId = r.employee_id || (r.filename ? r.filename.replace(".txt", "") : "N/A");
      let score = r.score ?? "N/A";
      let summary = r.summary || r.text || "(No summary provided)";
      let keywords = r.keywords || [];
      let reason = r.reason || "";

      // Use the same card layout as displayResumeCard for consistency
      const cardBody = [
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
          text: `📊 Score: ${score}`,
            wrap: true
          },
        reason && {
            type: "TextBlock",
          text: `📝 Reason: ${reason}`,
          wrap: true
        },
        keywords.length > 0 && {
          type: "TextBlock",
          text: `🔑 Keywords: ${keywords.join(", ")}`,
          wrap: true
        },
        summary && {
          type: "TextBlock",
          text: `📝 Summary: ${summary}`,
            wrap: true
          }
      ].filter(Boolean);

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
 
  } catch (error) {
    const errMsg = error.response?.data || error.message;
    await context.sendActivity(`❌ Search Candidates Error:\n\`\`\`${errMsg}\`\`\``);
  }
});
   

// --- /search and /skills Command (merged) ---
teamsBot.message(/^\/(search|skills)\s+(.*)/i, async (context, state) => {
  const match = context.activity.text.match(/^\/(search|skills)\s+(.*)/i);
  const command = match[1];
  const query = match[2].trim();

  if (!query) {
    await context.sendActivity(`❗ Please provide a query after "/${command}".`);
    return;
  }

  const endpoint = command === "skills" ? "skills" : "search";
  try {
    const response = await axios.post(`http://104.208.162.61:8083/${endpoint}`, {
      query
    }, {
      headers: { "Content-Type": "application/json" },
      timeout: 10000
    });

    const result = response.data;

    if (!result || !result.results || result.results.length === 0) {
      await context.sendActivity("⚠️ No candidates found.");
      return;
    }

    await sendCandidateCards(result.results, context);

  } catch (error) {
    const errMsg = error.response?.data || error.message;
    await context.sendActivity(`❌ ${command.charAt(0).toUpperCase() + command.slice(1)} Search Error:\n\`\`\`${errMsg}\`\`\``);
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
    await context.sendActivity("Please provide at least an identifier (name/employee_id) or a job description after jd.\nExample: /makeresume name Kushagra Wadhwa jd \"Job description\" or /makeresume jd \"Job description only\"");
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
    await context.sendActivity("❗ Please provide at least an identifier (name/employee_id) or a job description.\nExample: `/makeresume name Kushagra Wadhwa` or `/makeresume jd \"Software Engineer\"`");
    return;
  }

  try {
    // User-friendly loader for single-candidate or JD flow
    if (identifier_type && identifier && job_description) {
      await context.sendActivity('🔍 Looking for candidate...');
      await context.sendActivity('🛠️ Retailoring resume for the job description...');
      await context.sendActivity('⏳ Generating tailored resume...');
    } else if (identifier_type && identifier) {
      await context.sendActivity('🔍 Looking for candidate...');
      await context.sendActivity('⏳ Generating resume...');
    } else if (job_description && !identifier_type) {
      await context.sendActivity('🔍 Searching candidates...');
      await context.sendActivity('📊 Evaluating and scoring candidates...');
    }
    // First, try to get binary response from NIFI processor
    const response = await axios.post("http://104.208.162.61:8083/makeresume", payload, {
      responseType: "arraybuffer",
      headers: { "Content-Type": "application/json" },
      timeout: 600000 // 10 minutes
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
          await context.sendActivity('✅ Resume generated and uploaded!');
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
      const jsonResponse = await axios.post("http://104.208.162.61:8083/makeresume", payload, {
        headers: { "Content-Type": "application/json" },
        timeout: 600000 // 10 minutes
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
        
        const altResponse = await axios.post("http://104.208.162.61:8083/makeresume", altPayload, {
          headers: { "Content-Type": "application/json" },
          timeout: 600000 // 10 minutes
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
      await context.sendActivity(`❌ **FINAL RESULT:** Resume generation failed`);
      await context.sendActivity(`📊 **Error Details:** \`${fallbackText}\``);
      if (identifier_type && identifier) {
        await context.sendActivity('Attempting to fetch candidate profile as fallback...');
        await fetchAndDisplayViewCard(context, identifier_type, identifier);
      }
    }
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
        text: `📝 Reason: ${candidate.reason || "N/A"}`,
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
    const nifiViewUrl = "http://104.208.162.61:8083/view";
    // Build payload exactly like /makeresume
    const payload = {};
    if (identifier_type && identifier) {
      payload.identifier_type = identifier_type;
      payload.identifier = identifier;
    }
    if (!payload.identifier_type || !payload.identifier) {
      await context.sendActivity("❗ Please provide a valid employee ID or name after `/view`.");
      return;
    }
    const response = await axios.post(nifiViewUrl, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 20000, // 20 seconds for testing
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
    await context.sendActivity(`❌ Error while searching for candidate \`${identifier}\`:\n\n\`${errMsg}\``);
  }
});


// Enhanced /delete command: supports employee ID or name
teamsBot.message(/^\/delete(?:\s+(.*))?$/i, async (context, state) => {
  const text = context.activity.text;
  const args = text.replace(/^\/delete\s*/i, "").trim();
 
  let employeeId = "";
 
  if (!args) {
    await context.sendActivity("❗ Please provide an employee ID after `/delete`.\nExample:\n- `/delete 12345`");
    return;
  }
 
  // Only allow numeric employee ID
  if (/^\d+$/.test(args)) {
    employeeId = args;
  } else {
    await context.sendActivity("❗ Please provide a valid numeric employee ID after `/delete`.\nExample:\n- `/delete 12345`");
    return;
  }
 
  try {
    const nifiDeleteUrl = "http://104.208.162.61:8083/delete";
    const response = await axios.post(nifiDeleteUrl, {
      employee_id: employeeId
    }, {
      headers: { "Content-Type": "application/json" },
      timeout: 10000,
    });

    let nifiResp = response.data?.nifi_response || response.data || "No response";
    let parsedResp;
    try {
      parsedResp = typeof nifiResp === 'string' ? JSON.parse(nifiResp) : nifiResp;
    } catch {
      parsedResp = nifiResp;
    }

    if (parsedResp && parsedResp.status === "success") {
      await context.sendActivity(`🗑️ Candidate with employee ID \`${employeeId}\` has been deleted successfully.`);
    } else {
      await context.sendActivity(`❌ Failed to delete candidate.`);
    }
  } catch (err) {
    await context.sendActivity(`❌ Failed to delete candidate.`);
  }
});
 

teamsBot.message("/upload", async (context, state) => {
  state.conversation.awaitingUpload = true;
  state.conversation.awaitingEmployeeId = true;
  state.conversation.uploadData = {};
  await context.sendActivity("Please enter the employee ID for the file you want to upload. (Employee ID is compulsory to add the resume.)\n\nType `exit` anytime to cancel the upload process.");
});
// Handle file uploads and upload workflow - MUST BE BEFORE ECHO HANDLER
teamsBot.activity(ActivityTypes.Message, async (context, state) => {
  const attachments = context.activity.attachments;
  const messageText = context.activity.text?.trim() || "";
 
  // Skip processing if this is a command (starts with /)
  if (messageText.startsWith('/')) {
    return; // Let other handlers process commands
  }
 
  // Allow user to exit upload flow at any step
  if (
    (state.conversation.awaitingUpload || state.conversation.awaitingEmployeeId || state.conversation.awaitingConfirmation)
    && /^exit$/i.test(messageText)
  ) {
    await context.sendActivity("Upload process cancelled. If you want to upload again, type /upload.");
    resetUploadState(state);
    return;
  }
 
  // Step 1: Get employee_id from user
  if (state.conversation.awaitingEmployeeId && state.conversation.awaitingUpload) {
    if (messageText) {
      state.conversation.uploadData.employee_id = messageText;
      state.conversation.awaitingEmployeeId = false;
      await context.sendActivity("Now, please upload a PDF, DOC, or DOCX file for this employee.");
      return;
    } else {
      await context.sendActivity("❗ Employee ID is compulsory. Please enter a valid employee ID.");
      return;
    }
  }
 
  // Step 2: If awaiting upload and a supported file is attached
  if (state.conversation.awaitingUpload && !state.conversation.awaitingEmployeeId && attachments && attachments.length > 0) {
    const attachment = attachments[0];
    const supportedTypes = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ];
    if (supportedTypes.includes(attachment.contentType)) {
      state.conversation.awaitingConfirmation = true;
      state.conversation.pendingAttachment = attachment;
      state.conversation.awaitingUpload = false;
      await context.sendActivity(`You uploaded **${attachment.name || "a file"}** for employee ID **${state.conversation.uploadData.employee_id}**. Do you want to send it to NiFi? (yes/no)\n\nType \`exit\` to cancel.`);
      return;
    } else {
      await context.sendActivity("Only PDF, DOC, or DOCX files are supported. Please upload a valid file or type `exit` to cancel.");
      return;
    }
  }
 
  // Step 3: If user is confirming upload
  if (state.conversation.awaitingConfirmation && /^(yes|y)$/i.test(messageText)) {
    const attachment = state.conversation.pendingAttachment;
    const employeeId = state.conversation.uploadData?.employee_id;
    if (attachment && employeeId) {
      try {
        const pdfUrl = attachment.contentUrl;
        const nifiEndpoint = "http://104.208.162.61:8083/upload";
        const nifiPayload = { pdf_url: pdfUrl, employee_id: employeeId };
        const nifiResponse = await axios.post(nifiEndpoint, nifiPayload, {
          headers: { "Content-Type": "application/json" },
        });
        await context.sendActivity("✅ File uploaded to elastic database successfully.");
      } catch (error) {
        await context.sendActivity("❌ Sorry, NIFI cluster is down please try again later. Please try again later.");
      }
    } else {
      await context.sendActivity("❗ Missing file or employee ID. Please try /upload again.");
    }
    resetUploadState(state);
    return;
  }
 
  // Step 4: If user cancels
  if (state.conversation.awaitingConfirmation && /^(no|n)$/i.test(messageText)) {
    await context.sendActivity("Upload cancelled. If you want to upload again, type /upload.");
    resetUploadState(state);
    return;
  }
 
  // If we reach here and there's text, it's a regular message (not a command)
  if (messageText) {
    // Show fallback card (same as welcome card, but with a different header)
    const card = {
      type: "AdaptiveCard",
      version: "1.4",
      body: [
        {
          type: "TextBlock",
          text: "❓ Sorry, I couldn't understand your message.",
          size: "ExtraLarge",
          weight: "Bolder",
          color: "Attention",
          horizontalAlignment: "center",
          wrap: true
        },
        {
          type: "TextBlock",
          text: "Please use one of the available commands below:",
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
            { title: "/skills", value: "Find candidates by specific skill(s)." },
            { title: "/view", value: "View a candidate's resume by employee ID or name." },
            { title: "/delete", value: "Delete a candidate by employee ID or name." },
            { title: "/upload", value: "Upload a PDF, DOC, or DOCX resume for a candidate." }
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
          data: { msteams: { type: "messageBack", text: "/makeresume" } }
        },
        {
          type: "Action.Submit",
          title: "/search",
          data: { msteams: { type: "messageBack", text: "/search" } }
        },
        {
          type: "Action.Submit",
          title: "/skills",
          data: { msteams: { type: "messageBack", text: "/skills" } }
        },
        {
          type: "Action.Submit",
          title: "/view",
          data: { msteams: { type: "messageBack", text: "/view" } }
        },
        {
          type: "Action.Submit",
          title: "/delete",
          data: { msteams: { type: "messageBack", text: "/delete" } }
        },
        {
          type: "Action.Submit",
          title: "/upload",
          data: { msteams: { type: "messageBack", text: "/upload" } }
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
});
 
// Add this helper function before your teamsBot.activity handlers
function resetUploadState(state) {
  state.conversation.awaitingUpload = false;
  state.conversation.awaitingEmployeeId = false;
  state.conversation.awaitingConfirmation = false;
  state.conversation.pendingAttachment = null;
  state.conversation.uploadData = {};
}


//-------------------------------------------------------------------------------
//Activity Handlers



teamsBot.activity(/^message/, async (context, state) => {
  await context.sendActivity(`Matched with regex: ${context.activity.type}`);
});

teamsBot.activity(
  async (context) => Promise.resolve(context.activity.type === "message"),
  async (context, state) => {
    await context.sendActivity(`Matched function: ${context.activity.type}`);
  }
);

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
      await context.sendActivity(`🎉 **SUCCESS:** Resume document uploaded and shared in chat!`);
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
  // Creative Adaptive Card with all available commands and buttons
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
          { title: "/skills", value: "Find candidates by specific skill(s)." },
          { title: "/view", value: "View a candidate's resume by employee ID or name." },
          { title: "/delete", value: "Delete a candidate by employee ID or name." },
          { title: "/upload", value: "Upload a PDF, DOC, or DOCX resume for a candidate." }
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
        data: { msteams: { type: "messageBack", text: "/makeresume" } }
      },
      {
        type: "Action.Submit",
        title: "/search",
        data: { msteams: { type: "messageBack", text: "/search" } }
      },
      {
        type: "Action.Submit",
        title: "/skills",
        data: { msteams: { type: "messageBack", text: "/skills" } }
      },
      {
        type: "Action.Submit",
        title: "/view",
        data: { msteams: { type: "messageBack", text: "/view" } }
      },
      {
        type: "Action.Submit",
        title: "/delete",
        data: { msteams: { type: "messageBack", text: "/delete" } }
      },
      {
        type: "Action.Submit",
        title: "/upload",
        data: { msteams: { type: "messageBack", text: "/upload" } }
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
});

// Helper: Fetch and display /view card as fallback
async function fetchAndDisplayViewCard(context, identifier_type, identifier) {
  try {
    await context.sendActivity('🔍 Fetching candidate profile as fallback...');
    const nifiViewUrl = "http://104.208.162.61:8083/view";
    const payload = { identifier_type, identifier };
    const response = await axios.post(nifiViewUrl, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 20000,
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
