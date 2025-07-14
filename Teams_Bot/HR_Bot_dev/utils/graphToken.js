const axios = require("axios");
require("dotenv").config();

async function getGraphToken() {
  const clientId = process.env.BOT_ID;
  const clientSecret = process.env.SECRET_BOT_PASSWORD;
  const tenantId = process.env.tenantId;

  if (!clientId || !clientSecret || !tenantId) {
    throw new Error("Missing required environment variables for Graph token.");
  }

  const tokenUrl = `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`;
  const params = new URLSearchParams();
  params.append("client_id", clientId);
  params.append("scope", "https://graph.microsoft.com/.default");
  params.append("client_secret", clientSecret);
  params.append("grant_type", "client_credentials");

  try {
    const result = await axios.post(tokenUrl, params, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      }
    });

    return result.data.access_token;
  } catch (error) {
    console.error("❌ Error fetching Graph token:", error.response?.data || error.message);
    throw new Error("Failed to retrieve Microsoft Graph token");
  }
}

module.exports = { getGraphToken };
