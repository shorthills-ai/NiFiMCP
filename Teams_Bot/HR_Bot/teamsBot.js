/**
 * ===================================================================================================
 * HR RESUME ASSISTANT BOT
 * ===================================================================================================
 * 
 * @fileoverview Microsoft Teams bot for HR recruitment and resume management
 * @description AI-powered bot that helps HR professionals manage candidate resumes,
 *             generate tailored documents, search through talent pools, and streamline
 *             the recruitment process.
 * 
 * @version 2.0.0
 * @author HR Bot Development Team
 * @license MIT
 * 
 * Features:
 * - Resume generation with/without job descriptions
 * - Candidate search and management
 * - Bulk resume upload and processing
 * - OneDrive integration for file storage
 * - Adaptive card UI for enhanced user experience
 * 
 * Dependencies:
 * - @microsoft/agents-activity
 * - @microsoft/agents-hosting
 * - axios (for HTTP requests)
 * - dotenv (for environment variables)
 * 
 * Environment Variables Required:
 * - PRIMARY_NIFI_URL: Primary NIFI processor endpoint
 * - FALLBACK_NIFI_URL: Fallback NIFI processor endpoint
 * ===================================================================================================
 */

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
 * ===================================================================================================
 * UTILITY FUNCTIONS
 * ===================================================================================================
 */

/**
 * Axios wrapper with automatic fallback to secondary endpoint
 * Provides high availability by automatically switching to fallback URL if primary fails
 * 
 * @async
 * @function axiosWithFallback
 * @param {'get'|'post'} method - HTTP method to use
 * @param {string} path - API endpoint path (e.g., '/search', '/add')
 * @param {Object} options - Request options
 * @param {Object} [options.data={}] - Request payload data
 * @param {Object} [options.config={}] - Additional axios configuration
 * @returns {Promise<Object>} Axios response object
 * @throws {Error} If both primary and fallback endpoints fail
 * 
 * @example
 * const response = await axiosWithFallback("post", "/search", {
 *   data: { query: "software engineer" },
 *   config: { timeout: 30000 }
 * });
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
/**
 * ===================================================================================================
 * UI COMPONENT FUNCTIONS
 * ===================================================================================================
 */

/**
 * Sends an enhanced, beautiful welcome card to new users
 * Displays a comprehensive introduction with feature highlights and quick action buttons
 * 
 * @async
 * @function sendWelcomeCard
 * @param {Object} context - The Teams bot context containing activity and sendActivity method
 * @returns {Promise<void>}
 * 
 * @description
 * Creates a visually appealing adaptive card that includes:
 * - Branded header with bot name and tagline
 * - Feature overview with colored containers
 * - Complete command reference
 * - Quick action buttons for common tasks
 */
async function sendWelcomeCard(context) {
  const card = {
    type: "AdaptiveCard",
    version: "1.4",
    body: [
      {
        type: "Container",
        style: "emphasis",
        bleed: true,
        items: [
          {
            type: "ColumnSet",
            columns: [
              {
                type: "Column",
                width: "stretch",
                items: [
                  {
                    type: "TextBlock",
                    text: "🎯 HR Resume Assistant",
                    size: "ExtraLarge",
                    weight: "Bolder",
                    color: "Default",
                    horizontalAlignment: "Center"
                  },
                  {
                    type: "TextBlock",
                    text: "Your AI-powered recruitment companion",
                    size: "Medium",
                    color: "Default",
                    horizontalAlignment: "Center",
                    isSubtle: true
                  }
                ]
              }
            ]
          }
        ]
      },
      {
        type: "Container",
        spacing: "Large",
        items: [
          {
            type: "TextBlock",
            text: "👋 Welcome! I'm here to streamline your recruitment process",
            size: "Large",
            weight: "Bolder",
            wrap: true
          },
          {
            type: "TextBlock",
            text: "I can help you manage candidate resumes, generate tailored documents, and search through your talent pool efficiently.",
            wrap: true,
            spacing: "Small"
          }
        ]
      },
      {
        type: "Container",
        spacing: "Large",
        separator: true,
        items: [
          {
            type: "TextBlock",
            text: "🚀 **What I can do for you**",
            size: "Medium",
            weight: "Bolder",
            color: "Accent"
          },
          {
            type: "ColumnSet",
            spacing: "Medium",
            columns: [
              {
                type: "Column",
                width: "stretch",
                items: [
                  {
                    type: "Container",
                    style: "good",
                    items: [
                      {
                        type: "TextBlock",
                        text: "📄 **Resume Generation**",
                        weight: "Bolder",
                        size: "Medium"
                      },
                      {
                        type: "TextBlock",
                        text: "Create professional resumes with or without job descriptions",
                        wrap: true,
                        size: "Small"
                      }
                    ]
                  }
                ]
              },
              {
                type: "Column",
                width: "stretch",
                items: [
                  {
                    type: "Container",
                    style: "attention",
                    items: [
                      {
                        type: "TextBlock",
                        text: "🔍 **Smart Search**",
                        weight: "Bolder",
                        size: "Medium"
                      },
                      {
                        type: "TextBlock",
                        text: "Find candidates by skills, experience, or keywords",
                        wrap: true,
                        size: "Small"
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            type: "ColumnSet",
            spacing: "Medium",
            columns: [
              {
                type: "Column",
                width: "stretch",
                items: [
                  {
                    type: "Container",
                    style: "accent",
                    items: [
                      {
                        type: "TextBlock",
                        text: "📁 **Bulk Operations**",
                        weight: "Bolder",
                        size: "Medium"
                      },
                      {
                        type: "TextBlock",
                        text: "Upload and process multiple resumes at once",
                        wrap: true,
                        size: "Small"
                      }
                    ]
                  }
                ]
              },
              {
                type: "Column",
                width: "stretch",
                items: [
                  {
                    type: "Container",
                    style: "warning",
                    items: [
                      {
                        type: "TextBlock",
                        text: "👥 **Candidate Management**",
                        weight: "Bolder",
                        size: "Medium"
                      },
                      {
                        type: "TextBlock",
                        text: "View, add, or remove candidates easily",
                        wrap: true,
                        size: "Small"
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      },
      {
        type: "Container",
        spacing: "Large",
        separator: true,
        items: [
          {
            type: "TextBlock",
            text: "📌 **Available Commands**",
            size: "Medium",
            weight: "Bolder",
            spacing: "Small"
          },
          {
            type: "FactSet",
            facts: [
              { title: "📄 /makeresume", value: "Generate tailored resumes" },
              { title: "🔄 /generate", value: "Create resume from OneDrive" },
              { title: "🔍 /search", value: "Find candidates quickly" },
              { title: "👁️ /view", value: "View candidate profiles" },
              { title: "➕ /add", value: "Add new candidates" },
              { title: "🗑️ /delete", value: "Remove candidates" },
              { title: "📁 /uploadfolder", value: "Bulk upload resumes" }
            ]
          }
        ]
      },
      {
        type: "TextBlock",
        text: "**Get started with quick actions below:**",
        size: "Medium",
        weight: "Bolder",
        spacing: "Large"
      }
    ],
    actions: [
      {
        type: "Action.Submit",
        title: "📄 Make Resume",
        style: "positive",
        data: { msteams: { type: "messageBack", text: "/makeresume", displayText: "/makeresume" } }
      },
      {
        type: "Action.Submit",
        title: "🔍 Search Candidates",
        style: "positive",
        data: { msteams: { type: "messageBack", text: "/search", displayText: "/search" } }
      },
      {
        type: "Action.Submit",
        title: "➕ Add Candidate",
        data: { msteams: { type: "messageBack", text: "/add", displayText: "/add" } }
      },
      {
        type: "Action.Submit",
        title: "❓ Get Help",
        data: { msteams: { type: "messageBack", text: "/help", displayText: "/help" } }
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

/**
 * Fetches and displays candidate profile as a fallback when resume generation fails
 * Used when /makeresume or /generate commands can't produce a resume but need to show candidate info
 * 
 * @async
 * @function fetchAndDisplayViewCard
 * @param {Object} context - The Teams bot context for sending activities
 * @param {string} identifier_type - Type of identifier ('name' or 'employee_id')
 * @param {string} identifier - The actual identifier value
 * @returns {Promise<void>}
 * 
 * @description
 * Fallback mechanism that:
 * - Calls the /view endpoint to fetch candidate data
 * - Handles JSON parsing and validation
 * - Displays candidate profile using displayResumeCard
 * - Provides detailed error messages if candidate not found
 */
async function fetchAndDisplayViewCard(context, identifier_type, identifier) {
  try {
    await context.sendActivity('🔍 Fetching candidate profile...');

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

/**
 * Displays search results as interactive candidate cards
 * Creates adaptive cards for each candidate with score-based color coding and action buttons
 * 
 * @async
 * @function sendCandidateCards
 * @param {Array} results - Array of candidate objects from search results
 * @param {Object} context - The Teams bot context for sending activities
 * @returns {Promise<void>}
 * 
 * @description
 * Features:
 * - Limits display to top 20 results for performance
 * - Color-coded scores (green: >90%, yellow: 70-90%, red: <70%)
 * - Interactive buttons for view and delete actions
 * - Responsive design with proper spacing and formatting
 */
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
        },
        {
          type: "Action.Submit",
          title: "🗑️ Delete Candidate",
          data: {
            msteams: {
              type: "messageBack",
              text: `/delete ${empId}`
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

/**
 * Displays candidate resume data in a comprehensive adaptive card format
 * Creates a well-structured card showing all available candidate information
 * 
 * @async
 * @function displayResumeCard
 * @param {Object} context - The Teams bot context for sending activities
 * @param {Object} fallbackData - Candidate resume data object
 * @returns {Promise<void>}
 * 
 * @description
 * Dynamically builds an adaptive card with the following sections:
 * - Header with candidate name
 * - Contact information (title, email, phone, location)
 * - Professional summary
 * - Technical skills (comma-separated)
 * - Work experience (company, duration, description)
 * - Education (degree, institution, year)
 * - Projects (title, description)
 * - Certifications (title, issuer, year)
 * - Social profiles (platform, link)
 * 
 * Only displays sections that have data, ensuring clean presentation
 */
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

/**
 * ===================================================================================================
 * COMMAND HANDLERS
 * ===================================================================================================
 */

/**
 * Resets the conversation state for the current user
 * Clears all stored conversation data and starts fresh
 * 
 * @command /reset
 * @description Development and debugging command to clear conversation state
 * @usage /reset
 */
teamsBot.message("/reset", async (context, state) => {
  state.deleteConversationState();
  await context.sendActivity("✅ Conversation state has been reset successfully.");
});

/**
 * Tests system connectivity and environment configuration
 * Verifies both NIFI processor and Graph API connectivity
 * 
 * @command /test
 * @description Development and troubleshooting command to verify system health
 * @usage /test
 */
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


/**
 * Displays the welcome card with bot introduction and available commands
 * Handles various greeting messages and help requests
 * 
 * @command /help, hi, hello, hey
 * @description Shows comprehensive bot introduction and command reference
 * @usage /help, hi, hello, hey
 */
teamsBot.message(/^(hi|hello|hey|\/help)$/i, async (context, state) => {
  await sendWelcomeCard(context);
});

/**
 * Searches for candidates in the database using various criteria
 * Supports searching by name, skills, keywords, or any text content
 * 
 * @command /search
 * @description Searches candidate database and displays matching results
 * @usage /search <query>
 * @example /search software engineer
 * @example /search Python JavaScript
 * @example /search John Smith
 */
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


const { getGraphToken } = require("./utils/graphToken");

/**
 * Generates tailored resumes for candidates with optional job description matching
 * Creates professional Word documents that can be uploaded to OneDrive
 * 
 * @command /makeresume
 * @description Generates customized resumes for candidates
 * @usage /makeresume <identifier> [jd "job description"]
 * @example /makeresume 12345
 * @example /makeresume John Doe jd "Software Engineer with 5+ years experience"
 * @example /makeresume jd "Data Scientist with Python and ML skills"
 */
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
    // ✅ NEW: Check if candidate exists BEFORE attempting resume generation
    if (identifier_type && identifier) {
      await context.sendActivity('🔍 Looking for candidate...');
      
      // First, verify the candidate exists using /view endpoint
      try {
        const candidateCheckPayload = { identifier_type, identifier };
        const candidateCheckResponse = await axiosWithFallback("post", "/view", {
          data: candidateCheckPayload,
          config: {
            headers: { "Content-Type": "application/json" },
            timeout: 20000
          }
        });
        
        let candidateData = candidateCheckResponse.data;
        if (typeof candidateData === "string") {
          try {
            candidateData = JSON.parse(candidateData);
          } catch (e) {
            // If parsing fails, assume candidate not found
            await context.sendActivity("❌ Candidate not found in database.");
            return;
          }
        }
        
        // Check if candidate data is valid
        if (!candidateData || (!candidateData.name && !candidateData.skills && !candidateData.experience)) {
          await context.sendActivity("❌ Candidate not found in database.");
          return;
        }
        
        // Candidate found, proceed with resume generation
        if (job_description) {
          await context.sendActivity('🛠️ Retailoring resume for the job description...');
          await new Promise(resolve => setTimeout(resolve, 2000));
          await context.sendActivity('⏳ Generating tailored resume...');
        } else {
          await context.sendActivity('⏳ Generating resume...');
        }
        
      } catch (candidateCheckErr) {
        // Candidate check failed
        await context.sendActivity("❌ Candidate not found in database.");
        return;
      }
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
        // This is a genuine  Word document - proceed with upload
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
          await context.sendActivity("⚠️ Resume generation is only available in personal chat");
          if (resumeJsonData) {
            await displayResumeCard(context, resumeJsonData);
          } else if (identifier_type && identifier) {
            await context.sendActivity('No resume document available to display. Attempting to fetch candidate profile...');
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
    // ✅ KEY FIX: Check if this is valid resume data (same logic as /view command)
    if (!fallbackData || (!fallbackData.name && !fallbackData.skills && !fallbackData.experience)) {
      // This is "candidate not found" - handle it like /view command
      if (identifier_type && identifier) {
        await context.sendActivity("❌ Candidate not found in database.");
      } else {
        await context.sendActivity("❌ No candidates found for the provided job description.");
      }
      return; // Exit early, don't try to generate resume
    }

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

/**
 * Sends a simplified candidate card for job description-only resume generation
 * Used when /makeresume is called with only a job description to show matching candidates
 * 
 * @async
 * @function sendSimpleCandidateCard
 * @param {Object} context - The Teams bot context for sending activities
 * @param {Object} candidate - Candidate object with name, employee_id, score, keywords
 * @param {string} jobDescription - The job description used for matching
 * @returns {Promise<void>}
 * 
 * @description
 * Creates a compact card showing:
 * - Candidate name and employee ID
 * - Match score percentage
 * - Relevant keywords
 * - Quick action to generate tailored resume for this candidate
 */
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

/**
 * Displays candidate resume information in a formatted card
 * Supports searching by employee ID or candidate name
 * 
 * @command /view
 * @description Shows detailed candidate profile and resume information
 * @usage /view <identifier>
 * @example /view 12345
 * @example /view John Doe
 * @example /view name John Smith
 */
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


/**
 * Removes candidates from the database
 * Supports deletion by employee ID or candidate name
 * 
 * @command /delete
 * @description Permanently removes candidate records from the database
 * @usage /delete <identifier>
 * @example /delete 12345
 * @example /delete John Doe
 * @example /delete name John Smith
 */
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

/**
 * Get the onedrive resume link of the candidate
 * 
 * @command /add
 * @description Adds new candidates with their resume links
 * @usage /add (shows form) OR /add <employee_id> (legacy flow)
 * @example /add (opens form with employee ID and SharePoint link fields)
 * @example /add 12345 (legacy: prompts for SharePoint link)
 */
teamsBot.message(/^\/add$/i, async (context, state) => {
  try {
    // Check if there's an employee ID provided in the command (for backward compatibility)
    const parts = context.activity.text.trim().split(" ");
    const employeeId = parts[1];

    if (employeeId) {
      // Legacy flow: if employee ID is provided, use the old conversation flow
      state.conversation.awaitingLink = true;
      state.conversation.addEmployeeId = employeeId;
      await context.sendActivity(`Please enter the SharePoint resume link for employee ID *${employeeId}*.`);
      return;
    }

    // New flow: show adaptive card form
    const card = {
      type: "AdaptiveCard",
      $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
      version: "1.4",
      body: [
        {
          type: "TextBlock",
          text: "➕ Add New Candidate",
          size: "Large",
          weight: "Bolder",
          color: "Accent"
        },
        {
          type: "TextBlock",
          text: "Please provide the employee ID and SharePoint resume link.",
          wrap: true,
          spacing: "Medium"
        },
        {
          type: "Input.Text",
          id: "employeeId",
          label: "Employee ID",
          placeholder: "Enter employee ID (e.g., 12345)",
          isRequired: true,
          errorMessage: "Employee ID is required.",
          regex: "^[0-9]+$",
        },
        {
          type: "Input.Text",
          id: "resumeLink",
          label: "SharePoint Resume Link",
          placeholder: "Paste your SharePoint link here",
          isMultiline: false,
          style: "Url",
          isRequired: true,
          errorMessage: "A valid SharePoint link is required.",
        }
      ],
      actions: [
        {
          type: "Action.Submit",
          title: "Add Candidate",
          style: "positive",
          data: {
            action: "addCandidateFromCard" // Unique identifier for our message handler
          }
        }
      ]
    };

    await context.sendActivity({
      type: "message",
      attachments: [ { contentType: "application/vnd.microsoft.card.adaptive", content: card } ]
    });
  } catch (error) {
    console.error("[/add] Error sending adaptive card:", error);
    await context.sendActivity("❌ Error creating the input form. Please try again.");
  }
});

/**
 * Bulk uploads resumes from a SharePoint folder
 * Processes multiple resume files in a single operation
 * 
 * @command /uploadfolder
 * @description Uploads and processes multiple resumes from a SharePoint folder
 * @usage /uploadfolder <sharepoint_folder_link>
 * @example /uploadfolder https://company.sharepoint.com/sites/hr/Shared%20Documents/Resumes
 */
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
            text: "📂 Uploading resumes... Please wait...",
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


/**
 * Generates resumes from OneDrive links with form-based input
 * Creates professional Word documents that can be uploaded to OneDrive
 * 
 * @command /generate
 * @description Generates resumes from OneDrive links using form interface
 * @usage /generate (shows form with employee ID and OneDrive link fields)
 * @example /generate (opens form to input employee ID and OneDrive resume link)
 */
teamsBot.message(/^\/generate$/i, async (context, state) => {
  try {
    const card = {
      type: "AdaptiveCard",
      $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
      version: "1.4",
      body: [
        {
          type: "TextBlock",
          text: "📄 Generate Resume from OneDrive",
          size: "Large",
          weight: "Bolder",
          color: "Accent"
        },
        {
          type: "TextBlock",
          text: "Please provide the employee ID and the full OneDrive resume link.",
          wrap: true,
          spacing: "Medium"
        },
        {
          type: "Input.Text",
          id: "employeeId",
          label: "Employee ID",
          placeholder: "Enter employee ID (e.g., 12345)",
          isRequired: true,
          errorMessage: "Employee ID is required.",
          regex: "^[0-9]+$",
        },
        {
          type: "Input.Text",
          id: "resumeLink",
          label: "OneDrive Resume Link",
          placeholder: "Paste your OneDrive link here",
          isMultiline: false,
          style: "Url",
          isRequired: true,
          errorMessage: "A valid OneDrive link is required.",
        }
      ],
      actions: [
        {
          type: "Action.Submit",
          title: "Generate Resume",
          style: "positive",
          data: {
            action: "generateResumeFromCard" // Unique identifier for our message handler
          }
        }
      ]
    };

    await context.sendActivity({
      type: "message",
      attachments: [ { contentType: "application/vnd.microsoft.card.adaptive", content: card } ]
    });
  } catch (error) {
    console.error("[/generate] Error sending adaptive card:", error);
    await context.sendActivity("❌ Error creating the input form. Please try again.");
  }
});

/**
 * ===================================================================================================
 * UNIFIED MESSAGE ACTIVITY HANDLER
 * ===================================================================================================
 * This is the main message handler that processes all incoming messages and card submissions.
 * It handles:
 * - Adaptive card form submissions (from /generate and /add commands)
 * - Legacy conversation flows (for backward compatibility)
 * - Unknown message handling with helpful suggestions
 * ===================================================================================================
 */
teamsBot.activity(ActivityTypes.Message, async (context, state) => {

  // -------------------------------------------------------------------------
  // PART 1: Handle card submission from the /generate command
  // -------------------------------------------------------------------------
  if (context.activity.value?.action === 'generateResumeFromCard') {
    const employeeId = context.activity.value.employeeId?.trim();
    const resumeLink = context.activity.value.resumeLink?.trim();

    if (!employeeId || !resumeLink) {
      await context.sendActivity("⚠️ Both Employee ID and OneDrive link are required.");
      return;
    }

    try {
      await context.sendActivity('⏳ Generating resume from OneDrive link...');
      await context.sendActivity({ type: 'typing' });

      const payload = { employee_id: employeeId, resume_link: resumeLink };
      console.log(`[/generate] Sending payload to /generate endpoint:`, payload);

      const response = await axiosWithFallback("post", "/generate", {
        data: payload,
        config: {
          responseType: "arraybuffer",
          headers: { "Content-Type": "application/json" },
          timeout: 600000
        }
      });

      if (response.data && response.data.byteLength > 0) {
        const buffer = Buffer.from(response.data);
        const isWordDoc = buffer.slice(0, 2).toString() === 'PK';

        if (isWordDoc) {
          console.log(`[/generate] Received valid Word document, size: ${(buffer.length / 1024).toFixed(2)} KB`);
          const filename = `Resume_Generated_${employeeId}_${Date.now()}.docx`;

          state.conversation.pendingWordBuffer = buffer.toString('base64');
          state.conversation.pendingWordFilename = filename;
          state.conversation.pendingWordSize = buffer.length;
          console.log(`[/generate] Saved pending file to state for user consent.`);

          if (context.activity.conversation.conversationType === 'personal') {
            await context.sendActivity({
              type: "message",
              attachments: [
                {
                  contentType: "application/vnd.microsoft.teams.card.file.consent",
                  name: filename,
                  content: {
                    description: `Resume for Employee ID ${employeeId}`,
                    sizeInBytes: buffer.length,
                    acceptContext: { resume: true },
                    declineContext: { resume: true }
                  }
                }
              ]
            });
            await context.sendActivity('✅ Resume generated! Please accept the prompt to save the file.');
          } else {
            await context.sendActivity("⚠️ Resume generation is only available in personal chat. The file was created but cannot be uploaded here.");
          }
        } else {
          const responseText = buffer.toString('utf8');
          console.warn('[/generate] API returned a non-DOCX response:', responseText);
          await context.sendActivity(`❌ Failed to generate a valid document. The server responded with: \n\n\`${responseText}\``);
        }
      } else {
        console.error("[/generate] Empty response received from the server.");
        throw new Error("Empty response received from the server.");
      }
    } catch (err) {
      console.error('[ERROR] /generate card submission failed:', err);
      let errorMessage = err.message;
      if (err.response?.data) {
        errorMessage = Buffer.from(err.response.data).toString('utf8');
      }
      await context.sendActivity(`❌ An error occurred while generating the resume: ${errorMessage}`);
    }
    return; // Stop processing after handling the card action
  }

  // -------------------------------------------------------------------------
  // PART 2: Handle card submission from the /add command
  // -------------------------------------------------------------------------
  if (context.activity.value?.action === 'addCandidateFromCard') {
    const employeeId = context.activity.value.employeeId?.trim();
    const resumeLink = context.activity.value.resumeLink?.trim();

    if (!employeeId || !resumeLink) {
      await context.sendActivity("⚠️ Both Employee ID and SharePoint link are required.");
      return;
    }

    // Validate SharePoint link
    if (!resumeLink.includes('sharepoint.com')) {
      await context.sendActivity("❗ Please provide a valid SharePoint link.");
      return;
    }

    try {
      // Show uploading card
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

      const payload = {
        employee_id: employeeId,
        resume_link: resumeLink,
      };

      const response = await axiosWithFallback("post", "/add", {
        data: payload,
        config: { headers: { "Content-Type": "application/json" } }
      });

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
                    employee_id: employeeId,
                    msteams: {
                      type: "messageBack",
                      text: `/view ${employeeId}`
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
    return; // Stop processing after handling the card action
  }


  // -------------------------------------------------------------------------
  // PART 3: Legacy conversation flow for /add command (backward compatibility)
  // This handles the multi-step conversation flow where users:
  // 1. Type /add <employee_id>
  // 2. Paste the SharePoint link
  // 3. Confirm with yes/no
  // -------------------------------------------------------------------------
  const text = context.activity.text?.trim();

  // Handle resume link input for /add
  if (state.conversation.awaitingLink) {
    const urlRegex = /@?(https?:\/\/[^\s<>"]+)/i;
    let link = null;
    if (text) {
      const match = text.match(urlRegex);
      link = match && match[1] ? match[1].trim() : null;
    }
    if (!link && context.activity.attachments && context.activity.attachments.length > 0) {
      const attachment = context.activity.attachments[0];
      if (attachment.contentUrl && attachment.contentUrl.includes('sharepoint.com')) {
        link = attachment.contentUrl;
      }
      else if (
        attachment.contentType === 'text/html' &&
        typeof attachment.content === 'string'
      ) {
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

  // Handle confirmation for /add
  if (state.conversation.awaitingConfirmation) {
    if (text.toLowerCase() === "yes") {
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
      try {
        const payload = {
          employee_id: state.conversation.addEmployeeId,
          resume_link: state.conversation.resumeLink,
        };
        const response = await axiosWithFallback("post", "/add", {
          data: payload,
          config: { headers: { "Content-Type": "application/json" } }
        });
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
    delete state.conversation.awaitingConfirmation;
    delete state.conversation.addEmployeeId;
    delete state.conversation.resumeLink;
  }

  // -----------------------------------------------------------------------
});


/**
 * ===================================================================================================
 * INVOKE ACTIVITY HANDLER
 * ===================================================================================================
 * Handles special "invoke" activities that require immediate responses:
 * - Adaptive card action submissions (for cards shown in Teams app, not in chat)
 * - File consent requests (when uploading files to OneDrive)
 * 
 * IMPORTANT: Invoke activities must return a response within 5 seconds or Teams will show an error
 * ===================================================================================================
 */
teamsBot.activity("invoke", async (context, state) => {
  console.log('[INVOKE] Activity received:', context.activity.name);
  console.log('[INVOKE] Activity value:', JSON.stringify(context.activity.value));
  
  // -------------------------------------------------------------------------
  // Handle adaptive card action for /generate command
  // This is triggered when the card is shown in a task module or Teams app
  // -------------------------------------------------------------------------
  if (context.activity.name === 'adaptiveCard/action' && context.activity.value?.action === 'generateResumeFromCard') {
    console.log('Generate resume card action detected');
    
    // First, acknowledge the invoke immediately
    const invokeResponse = { status: 200 };
    
    // Process the request asynchronously
    setTimeout(async () => {
      try {
        // Initialize state.conversation if undefined
        if (!state) {
          state = {};
        }
        if (!state.conversation) {
          state.conversation = {};
        }

        const resumeLink = context.activity.value.resumeLink?.trim();
        const employeeId = context.activity.value.employeeId?.trim();

        if (!resumeLink || !employeeId) {
          await context.sendActivity('⚠️ Both Employee ID and OneDrive link are required.');
          return;
        }

        await context.sendActivity('⏳ Generating resume from OneDrive link...');

        // Build payload for generate endpoint
        const payload = {
          employee_id: employeeId,
          resume_link: resumeLink
        };

        try {
          // First, try to get binary response from NIFI processor
          const response = await axiosWithFallback("post", "/generate", {
            data: payload,
            config: {
              responseType: "arraybuffer",
              headers: { "Content-Type": "application/json" },
              timeout: 600000
            }
          });

          // Extract JSON resume data from headers (same pattern as /makeresume)
          let resumeJsonData = null;
          try {
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
              if (typeof jsonFromHeaders === 'string') {
                resumeJsonData = JSON.parse(jsonFromHeaders);
              } else {
                resumeJsonData = jsonFromHeaders;
              }
            } else {
              const candidateName = response.headers['resume-name'] || response.headers['x-resume-name'] || response.headers['candidate-name'];
              const candidateEmail = response.headers['resume-email'] || response.headers['x-resume-email'] || response.headers['candidate-email'];
              
              if (candidateName) {
                resumeJsonData = {
                  name: candidateName,
                  email: candidateEmail || 'Not provided',
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
              // This is a genuine Word document - proceed with upload (same pattern as /makeresume)
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
                await context.sendActivity("⚠️ Resume generation is only available in personal chat");
                if (resumeJsonData) {
                  await displayResumeCard(context, resumeJsonData);
                } else {
                  await context.sendActivity(`❌ No resume data available to display.`);
                }
              }
            } else {
              // This might be JSON data in the body instead of headers - try to parse it
              try {
                const jsonString = buffer.toString('utf8');
                const jsonData = JSON.parse(jsonString);
                
                // Use JSON data from body, or headers if available
                const finalJsonData = resumeJsonData || jsonData;
                await context.sendActivity('⏳ Generating resume...');
                await displayResumeCard(context, finalJsonData);
                
              } catch (parseErr) {
                // Use JSON data from headers as final fallback
                if (resumeJsonData) {
                  await context.sendActivity('⏳ Generating resume...');
                  await displayResumeCard(context, resumeJsonData);
                } else {
                  await context.sendActivity(`❌ Could not generate resume. Please try again later.`);
                }
              }
            }
          } else {
            // No binary data received - use JSON from headers if available
            if (resumeJsonData) {
              await displayResumeCard(context, resumeJsonData);
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
            const jsonResponse = await axiosWithFallback("post", "/generate", {
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

          // Display fallback adaptive card if we have valid JSON data
          if (fallbackData && typeof fallbackData === "object") {
            if (fallbackData.name || fallbackData.skills || fallbackData.experience) {
              await context.sendActivity('⏳ Generating resume...');
              await displayResumeCard(context, fallbackData);
            } else {
              await context.sendActivity(`❌ Resume generation failed. Please try again later.`);
              await context.sendActivity(`📊 Error Details: \`${fallbackText}\``);
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
                        text: "Please verify the OneDrive link and employee ID, then try again.",
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

      } catch (err) {
        console.error('[ERROR] Error generating resume:', err);
        await context.sendActivity({
          type: 'message',
          text: `❌ Failed to generate resume: ${err.message}`
        });
      }
    }, 100); // Small delay to ensure invoke response is sent first
    
    return invokeResponse;
  }
  
  // -------------------------------------------------------------------------
  // Handle file consent for file upload
  // This is triggered when user accepts/declines the file upload prompt
  // -------------------------------------------------------------------------
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

/**
 * ===================================================================================================
 * CONVERSATION UPDATE HANDLER
 * ===================================================================================================
 * Handles when new members are added to the conversation (bot installed or user joins)
 * ===================================================================================================
 */
teamsBot.conversationUpdate("membersAdded", async (context, state) => {
  await sendWelcomeCard(context);
});





/**
 * ===================================================================================================
 * MODULE EXPORTS
 * ===================================================================================================
 * Exports the configured Teams bot instance for use in the main application
 * ===================================================================================================
 */
module.exports.teamsBot = teamsBot;
