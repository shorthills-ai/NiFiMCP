// const { ActivityTypes } = require("@microsoft/agents-activity");
// const {
//   AgentApplication,
//   AttachmentDownloader,
//   MemoryStorage,
// } = require("@microsoft/agents-hosting");
// const { version } = require("@microsoft/agents-hosting/package.json");

// const downloader = new AttachmentDownloader();

// // Define storage and application
// const storage = new MemoryStorage();
// const teamsBot = new AgentApplication({
//   storage,
//   fileDownloaders: [downloader],
// });

// // Listen for user to say '/reset' and then delete conversation state
// teamsBot.message("/reset", async (context, state) => {
//   state.deleteConversationState();
//   await context.sendActivity("Ok I've deleted the current conversation state.");
// });

// teamsBot.message("/count", async (context, state) => {
//   const count = state.conversation.count ?? 0;
//   await context.sendActivity(`The count is ${count}`);
// });

// teamsBot.message("/diag", async (context, state) => {
//   await state.load(context, storage);
//   await context.sendActivity(JSON.stringify(context.activity));
// });

// teamsBot.message("/state", async (context, state) => {
//   await state.load(context, storage);
//   await context.sendActivity(JSON.stringify(state));
// });

// teamsBot.message("/runtime", async (context, state) => {
//   const runtime = {
//     nodeversion: process.version,
//     sdkversion: version,
//   };
//   await context.sendActivity(JSON.stringify(runtime));
// });


// teamsBot.conversationUpdate("membersAdded", async (context, state) => {
//   await context.sendActivity(
//     `Hi there! I'm an echo bot running on Agents SDK version ${version} that will echo what you said to me.`
//   );
// });

// // Listen for ANY message to be received. MUST BE AFTER ANY OTHER MESSAGE HANDLERS
// teamsBot.activity(ActivityTypes.Message, async (context, state) => {
//   // Increment count state
//   let count = state.conversation.count ?? 0;
//   state.conversation.count = ++count;

//   // Echo back users request
//   await context.sendActivity(`[${count}] you said: ${context.activity.text}`);
// });

// teamsBot.activity(/^message/, async (context, state) => {
//   await context.sendActivity(`Matched with regex: ${context.activity.type}`);
// });

// teamsBot.activity(
//   async (context) => Promise.resolve(context.activity.type === "message"),
//   async (context, state) => {
//     await context.sendActivity(`Matched function: ${context.activity.type}`);
//   }
// );

// module.exports.teamsBot = teamsBot;


// const { ActivityTypes } = require("@microsoft/agents-activity");
// const {
//   AgentApplication,
//   AttachmentDownloader,
//   MemoryStorage,
// } = require("@microsoft/agents-hosting");
// const { version } = require("@microsoft/agents-hosting/package.json");
// const axios = require("axios"); // Add axios for making HTTP requests

// const downloader = new AttachmentDownloader();

// // Define storage and application
// const storage = new MemoryStorage();
// const teamsBot = new AgentApplication({
//   storage,
//   fileDownloaders: [downloader],
// });

// // Listen for user to say '/reset' and then delete conversation state
// teamsBot.message("/reset", async (context, state) => {
//   state.deleteConversationState();
//   await context.sendActivity("Ok I've deleted the current conversation state.");
// });

// teamsBot.message("/count", async (context, state) => {
//   const count = state.conversation.count ?? 0;
//   await context.sendActivity(`The count is ${count}`);
// });

// teamsBot.message("/diag", async (context, state) => {
//   await state.load(context, storage);
//   await context.sendActivity(JSON.stringify(context.activity));
// });

// teamsBot.message("/state", async (context, state) => {
//   await state.load(context, storage);
//   await context.sendActivity(JSON.stringify(state));
// });

// teamsBot.message("/runtime", async (context, state) => {
//   const runtime = {
//     nodeversion: process.version,
//     sdkversion: version,
//   };
//   await context.sendActivity(JSON.stringify(runtime));
// });



// // New handler for /newppt command
// teamsBot.message("/newppt", async (context, state) => {
//   try {
//     // Extract the user's input after the /newppt command
//     const userInput = context.activity.text.replace("/newppt ", "").trim();

//     if (!userInput) {
//       await context.sendActivity("Please provide input after the /newppt command.");
//       return;
//     }

//     // Define the API endpoint and payload
//     const apiUrl = "http://172.200.58.63:8000/"; // Replace with the correct endpoint
//     const payload = { query: userInput }; // Send only the query text

//     console.log("Payload for /newppt:", payload);

//     // Make the POST request to the API
//     const response = await axios.post(apiUrl, payload, {
//       headers: {
//         "Content-Type": "application/json",
//       },
//     });

//     console.log("API Response for /newppt:", response.data);

//     // Extract the response fields
//     const  {message}  = response.data;
//     console.log("Message from API:", message);

//     // Send the answer directly to the user
//     await context.sendActivity(message);
//   } catch (error) {
//     // Handle errors and send an error message to the user
//     console.error("Error fetching data from /newppt API:", error.message);
//     await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
//   }
// });




// // New handler for fetching data from the API
// teamsBot.message("/fetchdata", async (context, state) => {
//   try {
//     // Define the API endpoint and payload
//     const apiUrl = "http://4.227.13.15:8000/docs#/default/process_query_query_post";
//     const payload = {
//       query: context.activity.text.replace("/fetchdata ", ""), // Extract query from user input
//     };

//     // Make the POST request
//     const response = await axios.post(apiUrl, payload, {
//       headers: {
//         "Content-Type": "application/json",
//       },
//     });

//     // Send the API response back to the user
//     await context.sendActivity(`API Response: ${JSON.stringify(response.data)}`);
//   } catch (error) {
//     // Handle errors and send an error message to the user
//     console.error("Error fetching data from API:", error);
//     await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
//   }
// });

// // Listen for ANY message to be received. MUST BE AFTER ANY OTHER MESSAGE HANDLERS
// teamsBot.activity(ActivityTypes.Message, async (context, state) => {
//   try {
//     // Extract the user's message
//     const userMessage = context.activity.text.trim().toLowerCase();
//     if (userMessage === "hi") {
//       console.log("User said 'hi', sending greeting message.");
//       await context.sendActivity("Hello! Hope you are fine. Please ask your query, and I will try to resolve it.");
//       return; // Exit early to avoid further processing
//     }

//     // Define the API endpoint and payload
//     const apiUrl = "http://0.0.0.0:8000/query";
//     const payload = { query: userMessage };
//     console.log("Payload:", payload);

//     // Make the POST request to the API
//     console.log("Sending request to API:", apiUrl);
//     const response = await axios.post(apiUrl, payload, {
//       headers: {
//         "Content-Type": "application/json",
//       },
//     });
//     //console.log("API Response:", response.data);

//     // Extract the response fields
//     const { answer, sources } = response.data;

//     // Check if the answer indicates insufficient information
//     if (answer === "I don't have enough information to answer this question based on the context.") {
//       console.log(" if Insufficient information to answer the question.");
//       await context.sendActivity(answer); // Send only the answer
//     } else {
//       // Format the response using Markdown
//       console.log(" else Formatting the response with sources.");
//       let formattedResponse = `**Answer:**\n${answer}\n\n**Sources:**\n`;
//       sources.forEach((source, index) => {
//         const link = source.metadata?.filepath || "No link available"; // Extract the link from metadata
//         const sourceFile = source.metadata?.source_file || "Unnamed Source"; // Extract the source file name
//         formattedResponse += `\n${index + 1}. ${source.text}\n   **Source File:** ${sourceFile}\n   [Link to PPT/docs](${link})`;
//       });

//       // Send the formatted response back to the user
//       await context.sendActivity(formattedResponse);
//     }
//   } catch (error) {
//     // Handle errors and send an error message to the user
//     console.error("Error fetching data from API:", error.message);
//     await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
//   }
// });



// teamsBot.activity(/^message/, async (context, state) => {
//   await context.sendActivity(`Matched with regex: ${context.activity.type}`);
// });

// teamsBot.activity(
//   async (context) => Promise.resolve(context.activity.type === "message"),
//   async (context, state) => {
//     await context.sendActivity(`Matched function: ${context.activity.type}`);
//   }
// );

// teamsBot.conversationUpdate("membersAdded", async (context, state) => {
//   await context.sendActivity(
//     `Hi there! I'm an echo bot running on Agents SDK version ${version} that will echo what you said to me.`
//   );
// });

// module.exports.teamsBot = teamsBot;






// const { ActivityTypes } = require("@microsoft/agents-activity");
// const {
//   AgentApplication,
//   AttachmentDownloader,
//   MemoryStorage,
// } = require("@microsoft/agents-hosting");
// const { version } = require("@microsoft/agents-hosting/package.json");
// const axios = require("axios"); // Add axios for making HTTP requests

// const downloader = new AttachmentDownloader();

// // Define storage and application
// const storage = new MemoryStorage();
// const teamsBot = new AgentApplication({
//   storage,
//   fileDownloaders: [downloader],
// });

// // Listen for user to say '/reset' and then delete conversation state
// teamsBot.message("/reset", async (context, state) => {
//   state.deleteConversationState();
//   await context.sendActivity("Ok I've deleted the current conversation state.");
// });

// // Listen for user to say '/count' and increment count state
// teamsBot.message("/count", async (context, state) => {
//   const count = state.conversation.count ?? 0;
//   state.conversation.count = count + 1;
//   await context.sendActivity(`The count is ${state.conversation.count}`);
// });

// // Diagnostic command to display activity details
// teamsBot.message("/diag", async (context, state) => {
//   await state.load(context, storage);
//   await context.sendActivity(JSON.stringify(context.activity));
// });

// // Diagnostic command to display state details
// teamsBot.message("/state", async (context, state) => {
//   await state.load(context, storage);
//   await context.sendActivity(JSON.stringify(state));
// });

// // Runtime information command
// teamsBot.message("/runtime", async (context, state) => {
//   const runtime = {
//     nodeversion: process.version,
//     sdkversion: version,
//   };
//   await context.sendActivity(JSON.stringify(runtime));
// });

// // New handler for /newppt command
// teamsBot.message("/newppt", async (context, state) => {
//   try {
//     // Load the conversation state
//     await state.load(context, storage);

//     // Retrieve the previous response from the conversation state
//     console.log("Retrieving previous response from conversation state.", state.conversation.previousResponse);
//     const previousResponse = state.conversation.previousResponse || "No previous context available.";

//     // Define the API endpoint and payload
//     const apiUrl = "http://172.200.58.63:8099/"; // Replace with the correct endpoint
//     const payload = {
//       query: previousResponse, // Use the previous response as the query
//     };

//     console.log("Payload for /newppt:", JSON.stringify(payload, null, 2));

//     // Make the POST request to the API
//     const response = await axios.post(apiUrl, payload, {
//       headers: {
//         "Content-Type": "application/json",
//       },
//     });

//     console.log("API Response for /newppt:", response.data);

//     // Extract the response fields
//     const { message } = response.data;

//     // Save the current response in the conversation state
//     state.conversation.previousResponse = message;

//     // Send the answer directly to the user
//     await context.sendActivity(message);

//     // Save the updated state
//     await state.save(context, storage);
//   } catch (error) {
//     // Handle errors and send an error message to the user
//     console.error("Error fetching data from /newppt API:", error.response?.data || error.message);
//     await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
//   }
// });

// // Listen for ANY message to be received. MUST BE AFTER ANY OTHER MESSAGE HANDLERS
// teamsBot.activity(ActivityTypes.Message, async (context, state) => {
//   try {
//     // Load the conversation state
//     await state.load(context, storage);

//     // Extract the user's message
//     const userMessage = context.activity.text.trim().toLowerCase();
//     if (userMessage === "hi") {
//       console.log("User said 'hi', sending greeting message.");
//       await context.sendActivity("Hello! Hope you are fine. Please ask your query, and I will try to resolve it.");
//       return; // Exit early to avoid further processing
//     }

//     // Define the API endpoint and payload
//     const apiUrl = "http://0.0.0.0:8000/query"; // Replace with the correct endpoint
//     const payload = { query: userMessage };
//     console.log("Payload:", payload);

//     // Make the POST request to the API
//     console.log("Sending request to API:", apiUrl);
//     const response = await axios.post(apiUrl, payload, {
//       headers: {
//         "Content-Type": "application/json",
//       },
//     });

//     // Extract the response fields
//     const { answer, sources } = response.data;

//     // Format the response using Markdown
//     let formattedResponse = `**Answer:**\n${answer}\n\n**Sources:**\n`;
//     sources.forEach((source, index) => {
//       const link = source.metadata?.filepath || "No link available"; // Extract the link from metadata
//       const sourceFile = source.metadata?.source_file || "Unnamed Source"; // Extract the source file name
//       formattedResponse += `\n${index + 1}. ${source.text}\n   **Source File:** ${sourceFile}\n   [Link to PPT/docs](${link})`;
//     });

//     // Save the formatted response in the conversation state
//     state.conversation.previousResponse = formattedResponse;

//     // Send the formatted response back to the user
//     await context.sendActivity(formattedResponse);

//     // Save the updated state
//     await state.save(context, storage);
//   } catch (error) {
//     // Handle errors and send an error message to the user
//     console.error("Error fetching data from API:", error.message);
//     await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
//   }
// });

// // Conversation update handler
// teamsBot.conversationUpdate("membersAdded", async (context, state) => {
//   await context.sendActivity(
//     `Hi there! I'm an echo bot running on Agents SDK version ${version} that will echo what you said to me.`
//   );
// });

// module.exports.teamsBot = teamsBot;




const { ActivityTypes } = require("@microsoft/agents-activity");
const {
  AgentApplication,
  AttachmentDownloader,
  MemoryStorage,
} = require("@microsoft/agents-hosting");
const { version } = require("@microsoft/agents-hosting/package.json");
const axios = require("axios"); // Add axios for making HTTP requests

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

// Listen for user to say '/count' and increment count state
teamsBot.message("/count", async (context, state) => {
  const count = state.conversation.count ?? 0;
  state.conversation.count = count + 1;
  await context.sendActivity(`The count is ${state.conversation.count}`);
});

// Diagnostic command to display activity details
teamsBot.message("/diag", async (context, state) => {
  await state.load(context, storage);
  await context.sendActivity(JSON.stringify(context.activity));
});

// Diagnostic command to display state details
teamsBot.message("/state", async (context, state) => {
  await state.load(context, storage);
  await context.sendActivity(JSON.stringify(state));
});

// Runtime information command
teamsBot.message("/runtime", async (context, state) => {
  const runtime = {
    nodeversion: process.version,
    sdkversion: version,
  };
  await context.sendActivity(JSON.stringify(runtime));
});

// New handler for /newppt command
// New handler for /newppt command
teamsBot.message("/newppt", async (context, state) => {
  try {
    // Load the conversation state
    await state.load(context, storage);

    // Retrieve the previous response from the conversation state
    console.log("Retrieving previous response from conversation state.", state.conversation.previousResponse);
    const previousResponse = state.conversation.previousResponse || "No previous context available.";

    // Define the API endpoint and payload
    const apiUrl = "http://172.200.58.63:8099/"; // Replace with the correct endpoint
    const payload = {
      query: previousResponse, // Use the previous response as the query
    };

    console.log("Payload for /newppt:", JSON.stringify(payload, null, 2));

    // Make the POST request to the API
    const response = await axios.post(apiUrl, payload, {
      headers: {
        "Content-Type": "application/json",
      },
    });

    console.log("API Response for /newppt:", response.data);

    // Extract the response fields
    const { message } = response.data;

    // Save the current response in the conversation state
    state.conversation.previousResponse = message;


    // Send the answer directly to the user
    await context.sendActivity(message);
  } catch (error) {
    // Handle errors and send an error message to the user
    console.error("Error fetching data from /newppt API:", error.response?.data || error.message);
    await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
  }
});

// Generic handler for user queries
teamsBot.activity(ActivityTypes.Message, async (context, state) => {
  try {
    // Load the conversation state
    await state.load(context, storage);

    // Extract the user's message
    const userMessage = context.activity.text.trim().toLowerCase();
    if (userMessage === "hi") {
      console.log("User said 'hi', sending greeting message.");
      await context.sendActivity("Hello! Hope you are fine. Please ask your query, and I will try to resolve it.");
      return; // Exit early to avoid further processing
    }

    // Define the API endpoint and payload
    //change the url to original endpoint
    const apiUrl = "http://104.208.162.61:8000/query"; // Replace with the correct endpoint
    const payload = { query: userMessage };
    console.log("Payload:", payload);

    // Make the POST request to the API
    console.log("Sending request to API:", apiUrl);
    const response = await axios.post(apiUrl, payload, {
      headers: {
        "Content-Type": "application/json",
      },
    });

    // Extract the response fields
    const { answer, sources } = response.data;

    // Format the response using Markdown
    let formattedResponse = `**Answer:**\n${answer}\n\n**Sources:**\n`;
    sources.forEach((source, index) => {
      const link = source.metadata?.filepath || "No link available"; // Extract the link from metadata
      const sourceFile = source.metadata?.source_file || "Unnamed Source"; // Extract the source file name
      formattedResponse += `\n${index + 1}. ${source.text}\n   **Source File:** ${sourceFile}\n   [Link to PPT/docs](${link})`;
    });

    // Save the formatted response in the conversation state
    state.conversation.previousResponse = formattedResponse;

    // Save the updated state with forceWrite to avoid eTag conflicts
    await state.save(context, storage, { forceWrite: true });

    // Send the formatted response back to the user
    await context.sendActivity(formattedResponse);
  } catch (error) {
    // Handle errors and send an error message to the user
    console.error("Error fetching data from API:", error.message);
    await context.sendActivity("Sorry, I couldn't fetch data from the API. Please try again later.");
  }
});

// Conversation update handler
teamsBot.conversationUpdate("membersAdded", async (context, state) => {
  await context.sendActivity(
    `Hi there! I'm an echo bot running on Agents SDK version ${version} that will echo what you said to me.`
  );
});

module.exports.teamsBot = teamsBot;