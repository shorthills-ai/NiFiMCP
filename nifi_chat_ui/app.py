import streamlit as st
import json # Import json for formatting tool results
import uuid # Added for context IDs
from loguru import logger # Import logger directly

# Set page config MUST be the first Streamlit call
st.set_page_config(page_title="NiFi Chat UI", layout="wide")

# --- Setup Logging --- 
try:
    # Use session state to ensure logging is only set up once per session, not on every script re-run
    if "logging_initialized" not in st.session_state:
        from config.logging_setup import setup_logging
        setup_logging() 
        st.session_state.logging_initialized = True
        logger.info("Logging initialized for new session")
    else:
        logger.debug("Logging already initialized for this session")
except ImportError:
    print("Warning: Logging setup failed. Check config/logging_setup.py")
# ---------------------

# Restore imports
from chat_manager import get_gemini_response, get_openai_response, get_formatted_tool_definitions, get_azure_openai_response
from chat_manager import configure_llms, is_initialized
from mcp_handler import get_available_tools, execute_mcp_tool
# Import config from the new location
try:
    from config import settings as config # Updated import
except ImportError:
    logger.error("Failed to import config.settings. Ensure config/__init__.py exists if needed, or check PYTHONPATH.")
    st.error("Configuration loading failed. Application cannot start.")
    st.stop()

# Initialize LLM clients after page config
if not is_initialized:
    logger.info("Initializing LLM clients...")
    configure_llms()

# --- Constants ---
MAX_LOOP_ITERATIONS = 10 # Safety break for the execution loop
SYSTEM_PROMPT_FILE = "nifi_chat_ui/system_prompt.md"

# --- Session State Initialization ---
# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = [] 

# Initialize objective
if "current_objective" not in st.session_state:
    st.session_state.current_objective = ""
    
# Initialize recovery flags
# if "run_recovery_loop" not in st.session_state:
#     st.session_state.run_recovery_loop = False
# if "history_cleared_for_next_llm_call" not in st.session_state:
#     st.session_state.history_cleared_for_next_llm_call = False

# --- Load System Prompt --- 
def load_system_prompt():
    try:
        with open(SYSTEM_PROMPT_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Error: System prompt file not found at {SYSTEM_PROMPT_FILE}")
        return "You are a helpful NiFi assistant." # Fallback prompt
    except Exception as e:
        st.error(f"Error reading system prompt file: {e}")
        return "You are a helpful NiFi assistant."

# Store the base prompt loaded from the file
base_system_prompt = load_system_prompt()

# --- Sidebar --- 
with st.sidebar:
    st.title("Settings")
    
    # --- Model Selection (Combined) --- 
    available_models = []
    model_to_provider = {}
    
    if config.GOOGLE_API_KEY and config.GEMINI_MODELS:
        for model in config.GEMINI_MODELS:
            available_models.append(f"Gemini: {model}")
            model_to_provider[f"Gemini: {model}"] = ("Gemini", model)
            
    if config.OPENAI_API_KEY and config.OPENAI_MODELS:
        for model in config.OPENAI_MODELS:
            available_models.append(f"OpenAI: {model}")
            model_to_provider[f"OpenAI: {model}"] = ("OpenAI", model)

    # ----Azure OpenAI support ----
    if config.AZURE_OPENAI_API_KEY and config.AZURE_OPENAI_MODELS:
        for model in config.AZURE_OPENAI_MODELS:
            available_models.append(f"Azure-OpenAI: {model}")
            model_to_provider[f"Azure-OpenAI: {model}"] = ("Azure-OpenAI", model)
    
    selected_model_display_name = None
    provider = None # Will be derived from selection
    model_name = None # Will be derived from selection

    if not available_models:
        st.error("No LLM models configured or API keys missing. Please check your .env file.")
    else:
        # Determine default selection
        # Prioritize Gemini if available, otherwise first OpenAI, else first in list
        default_selection = None
        if config.GOOGLE_API_KEY and config.GEMINI_MODELS:
            default_selection = f"Gemini: {config.GEMINI_MODELS[0]}"
        elif config.OPENAI_API_KEY and config.OPENAI_MODELS:
            default_selection = f"OpenAI: {config.OPENAI_MODELS[0]}"
        
        # Ensure default is actually in the list
        if default_selection not in available_models:
            default_selection = available_models[0] # Fallback to first item
        
        default_index = available_models.index(default_selection)
        
        selected_model_display_name = st.selectbox(
            "Select LLM Model:", 
            available_models, 
            index=default_index,
            key="model_select" # Use a key to track selection
        )
        
        if selected_model_display_name:
            provider, model_name = model_to_provider[selected_model_display_name]
            logger.debug(f"Selected Model: {model_name}, Provider: {provider}")
            
            # Check if provider changed and reconfigure if needed
            # (Potentially less critical now if configuration is robust)
            previous_provider = st.session_state.get("previous_provider", None)
            if provider != previous_provider:
                try:
                    # configure_llms() # Re-configure only if necessary, e.g., client state management
                    st.session_state["previous_provider"] = provider
                    logger.info(f"Provider context changed to {provider} based on model selection.")
                except Exception as e:
                    logger.error(f"Error during potential reconfiguration for {provider}: {e}", exc_info=True)
                    # st.sidebar.warning(...) # Optional warning if reconfiguration fails
        else:
             # Handle case where selection somehow becomes None (shouldn't happen with selectbox)
             st.error("No model selected.")

    # --- Phase Selection --- 
    st.markdown("---") # Add separator
    phase_options = ["All", "Review", "Build", "Modify", "Operate"]
    # Initialize session state for selected_phase if it doesn't exist
    if "selected_phase" not in st.session_state:
        st.session_state.selected_phase = "All"
    
    st.selectbox(
        "Tool Phase Filter:",
        phase_options,
        key="selected_phase", # Bind directly to session state key
        help="Filter the tools shown below and available to the LLM by operational phase."
    )
    
    # --- Tool Display --- 
    st.markdown("---")
    st.subheader("Available MCP Tools")
    # Fetch tools based on the *current* value of the selectbox for sidebar display
    current_sidebar_phase = st.session_state.get("selected_phase", "All") # Read current value via key
    raw_tools_list = get_available_tools(phase=current_sidebar_phase)
    
    if raw_tools_list:
        for tool_data in raw_tools_list: 
            # No filtering needed here anymore, backend does it.
            if not isinstance(tool_data, dict) or tool_data.get("type") != "function" or not isinstance(tool_data.get("function"), dict):
                st.warning(f"Skipping unexpected tool data format: {tool_data}")
                continue
            function_details = tool_data.get("function", {})
            tool_name = function_details.get('name', 'Unnamed Tool')
            tool_description = function_details.get('description', 'No description')
            parameters = function_details.get('parameters', {}) # parameters schema
            properties = parameters.get('properties', {}) if isinstance(parameters, dict) else {}
            required_params = parameters.get('required', []) if isinstance(parameters, dict) else []
            
            with st.expander(f"🔧 {tool_name}", expanded=False):
                st.markdown(f"**Description:** {tool_description}")
                if properties:
                    st.markdown("**Parameters:**")
                    for param_name, param_info in properties.items():
                        required = "✳️ " if param_name in required_params else ""
                        desc_lines = param_info.get('description', 'No description').split('\n')
                        first_line = desc_lines[0]
                        other_lines = desc_lines[1:]
                        st.markdown(f"- {required}`{param_name}`: {first_line}")
                        if other_lines:
                            col1, col2 = st.columns([0.05, 0.95])
                            with col2:
                                for line in other_lines:
                                    st.markdown(f"{line.strip()}")
                else:
                    st.markdown("_(No parameters specified)_")
    else:
         st.warning("No MCP tools available or failed to retrieve.")
         
    # --- History Clear --- 
    if st.sidebar.button("Clear Chat History"):
        st.session_state.messages = []
        # Clear objective and flags as well
        st.session_state.current_objective = ""
        # st.session_state.run_recovery_loop = False # Removed
        # st.session_state.history_cleared_for_next_llm_call = False # Removed
        # Reset phase to default
        st.session_state.selected_phase = "All" # Reset phase on clear
        logger.info("Chat history and objective cleared by user.") 
        st.rerun()

# --- Main Chat Interface --- 
st.title("NiFi Chat UI")

# --- Objective Input Panel --- 
st.text_area(
    "Define the overall objective for this session:", 
    key="objective_input",
    value=st.session_state.current_objective, 
    height=100,
    on_change=lambda: st.session_state.update(current_objective=st.session_state.objective_input) 
)
st.markdown("---")

# --- Display Chat History --- 
for message in st.session_state.messages:
    if message.get("role") == "tool":
        continue
    # Removed system message check for HISTORY_CLEAR_MARKER
    # elif message.get("role") == "system" and message.get("content") == HISTORY_CLEAR_MARKER:
    #     st.info(HISTORY_CLEAR_MARKER)
    #     continue
        
    with st.chat_message(message["role"]):
        # Display content or tool call placeholder
        if message["role"] == "assistant" and "tool_calls" in message:
            tool_names = [tc.get('function', {}).get('name', 'unknown') for tc in message.get("tool_calls", [])]
            if tool_names:
                st.markdown(f"⚙️ Calling tool(s): `{', '.join(tool_names)}`...")
            else:
                st.markdown("_(Tool call with no details)_")
        elif "content" in message:
            st.markdown(message["content"])
        elif message["role"] == "assistant" and "tool_calls" in message and "content" not in message:
            tool_names = [tc.get('function', {}).get('name', 'unknown') for tc in message.get("tool_calls", [])]
            if tool_names:
                st.markdown(f"⚙️ Calling tool(s): `{', '.join(tool_names)}`...")
            else:
                st.markdown("_(Tool call with no details)_")
                
        # Display captions (Tokens, IDs)
        caption_parts = []
        if message["role"] == "user":
            user_req_id = message.get("user_request_id")
            if user_req_id:
                caption_parts.append(f"Request ID: `{user_req_id}`")
        elif message["role"] == "assistant":
            token_count_in = message.get("token_count_in", 0)
            token_count_out = message.get("token_count_out", 0)
            action_id = message.get("action_id")
            if token_count_in or token_count_out:
                caption_parts.append(f"Tokens: In={token_count_in}, Out={token_count_out}")
            if action_id:
                caption_parts.append(f"Action ID: `{action_id}`")
                
        if caption_parts:
            st.caption(" | ".join(caption_parts))

# --- Refactored Execution Loop Function --- 
def run_execution_loop(provider: str, model_name: str, base_sys_prompt: str, user_req_id: str):
    """Runs the main LLM interaction loop."""
    bound_logger = logger.bind(user_request_id=user_req_id)
    loop_count = 0
    while loop_count < MAX_LOOP_ITERATIONS:
        loop_count += 1
        current_loop_logger = bound_logger.bind(loop=loop_count)
        current_loop_logger.info(f"Starting execution loop iteration {loop_count}")

        # --- Prepare context for LLM call (History and System Prompt) ---
        messages_for_llm = None
        system_prompt_for_llm = None
        
        # Removed history clearing logic based on flag
        # if st.session_state.get("history_cleared_for_next_llm_call", False):
        #     current_loop_logger.info("History clear flag set. Preparing recovery context.")
        #     messages_for_llm = [st.session_state.messages[-1]] if st.session_state.messages else []
        #     system_prompt_for_llm = base_sys_prompt
        #     st.session_state.history_cleared_for_next_llm_call = False
        # else:
        
        # Always use current logic for preparing messages
        current_loop_logger.debug("Using full history and potentially dynamic system prompt.")
        messages_for_llm = st.session_state.messages
        current_objective = st.session_state.get("current_objective", "")
        if current_objective and current_objective.strip():
            system_prompt_for_llm = f"{base_sys_prompt}\\n\\n## Current Objective\\n{current_objective.strip()}"
            current_loop_logger.debug("Objective found, appending to system prompt.")
        else:
            system_prompt_for_llm = base_sys_prompt
            current_loop_logger.debug("No objective set, using base system prompt.")
        # -----------------------------------------------------------------

        # --- Prepare Tools --- 
        # Get the selected phase
        current_phase = st.session_state.get("selected_phase", "All")
        
        # Fetch the potentially filtered tools based on the selected phase
        current_loop_logger.debug(f"Fetching tools for phase: {current_phase}")
        filtered_raw_tools_list = get_available_tools(phase=current_phase, user_request_id=user_req_id)
        
        # Format the filtered tools for the current provider
        formatted_tools = None
        current_loop_logger.debug(f"Formatting tools for provider: {provider}")
        if filtered_raw_tools_list:
             try:
                  # Pass the *filtered* list to the formatter
                  formatted_tools = get_formatted_tool_definitions(provider=provider, raw_tools=filtered_raw_tools_list, user_request_id=user_req_id) 
                  if formatted_tools:
                       current_loop_logger.debug(f"Tools successfully formatted for {provider} ({len(formatted_tools)} tools).")
                  else:
                       current_loop_logger.warning(f"get_formatted_tool_definitions returned None/empty for {provider} with filtered list.")
             except Exception as fmt_e:
                  st.error(f"Error formatting tools for {provider} in loop: {fmt_e}")
                  current_loop_logger.error(f"Error formatting tools for {provider}: {fmt_e}", exc_info=True)
                  formatted_tools = None # Ensure it's None if formatting fails
        # ----------------------

        # --- Call LLM --- 
        # Generate a unique Action ID for this specific LLM call
        llm_action_id = str(uuid.uuid4())
        current_loop_logger = current_loop_logger.bind(action_id=llm_action_id) # Bind action_id for loop logging

        response_data = None
        with st.spinner(f"Thinking... (Step {loop_count})"):
            try:
                current_loop_logger.info(f"Calling LLM ({provider} - {model_name})...")
                if provider == "Gemini":
                    response_data = get_gemini_response(messages=messages_for_llm, 
                                                        system_prompt=system_prompt_for_llm, 
                                                        tools=formatted_tools, 
                                                        model_name=model_name, 
                                                        user_request_id=user_req_id, 
                                                        action_id=llm_action_id) # Pass action_id
                elif provider == "OpenAI":
                    response_data = get_openai_response(messages=messages_for_llm, 
                                                        system_prompt=system_prompt_for_llm, 
                                                        tools=formatted_tools, 
                                                        model_name=model_name, 
                                                        user_request_id=user_req_id,
                                                        action_id=llm_action_id) # Pass action_id
                elif provider == "Azure-OpenAI":
                    response_data = get_azure_openai_response(
                        messages=messages_for_llm,
                        system_prompt=system_prompt_for_llm,
                        tools=formatted_tools,
                        model_name=model_name,
                        user_request_id=user_req_id,
                        action_id=llm_action_id
                    )
                else:
                    st.error("Invalid provider selected.")
                    current_loop_logger.error(f"Invalid provider selected: {provider}")
                    break
                if response_data is None:
                     st.error("LLM response was empty.")
                     current_loop_logger.error("LLM response data was None.")
                     break
                else:
                    current_loop_logger.info(f"Received response from LLM ({provider}).")
            except Exception as e:
                st.error(f"Error calling LLM API: {e}")
                current_loop_logger.error(f"Error calling LLM API ({provider}): {e}", exc_info=True)
                break
        # ---------------
        
        # --- Process LLM Response --- 
        llm_content = response_data.get("content")
        tool_calls = response_data.get("tool_calls")
        error_message = response_data.get("error")
        token_count_in = response_data.get("token_count_in", 0)
        token_count_out = response_data.get("token_count_out", 0)
        
        if error_message:
            current_loop_logger.error(f"LLM returned an error: {error_message}")
            with st.chat_message("assistant"):
                st.markdown(f"Sorry, I encountered an error: {error_message}")
            st.session_state.messages.append({"role": "assistant", "content": f"Sorry, I encountered an error: {error_message}"})
            break
            
        # Add assistant message to history (including tool calls if any)
        assistant_message_to_add = {
            "role": "assistant", 
            "token_count_in": token_count_in, 
            "token_count_out": token_count_out,
            "action_id": llm_action_id # Add action_id here
        }
        if llm_content: assistant_message_to_add["content"] = llm_content
        if tool_calls: assistant_message_to_add["tool_calls"] = tool_calls
        st.session_state.messages.append(assistant_message_to_add)
        current_loop_logger.debug(f"Appended assistant message: Content={'present' if llm_content else 'absent'}, ToolCalls={len(tool_calls) if tool_calls else 0}")

        # Display assistant message (or tool call placeholder) generated in this loop iteration
        with st.chat_message("assistant"):
            if tool_calls:
                tool_names = [tc.get('function', {}).get('name', 'unknown') for tc in tool_calls]
                if tool_names:
                     st.markdown(f"⚙️ Calling tool(s): `{', '.join(tool_names)}`...")
                else:
                     st.markdown("_(Tool call with no details)_") # Should be rare
            elif llm_content:
                st.markdown(llm_content)
            else:
                st.markdown("_(Assistant provided no content or tool calls)_") # Should be rare

            # Add token counts and action ID caption for this message
            caption_parts = []
            if token_count_in or token_count_out:
                 caption_parts.append(f"Tokens: In={token_count_in}, Out={token_count_out}")
            if llm_action_id: # Use the ID from this loop
                 caption_parts.append(f"Action ID: `{llm_action_id}`")
            if caption_parts:
                st.caption(" | ".join(caption_parts))

        # --- Handle Tool Calls (if any) --- 
        if not tool_calls:
            current_loop_logger.info("No tool calls requested by LLM. Checking for TASK COMPLETE.")
            # If no tool calls and LLM thinks task is done, break the loop
            if llm_content and "TASK COMPLETE" in llm_content:
                current_loop_logger.info("TASK COMPLETE detected. Ending execution loop.")
                break
            else:
                # If no tool call and task not complete, this iteration might be done (e.g., clarifying question)
                # Or it could be an unexpected state. For now, assume the loop should end.
                current_loop_logger.info("No tool calls and no TASK COMPLETE. Ending loop for this user request.")
                break # Exit loop if no tools called and not explicitly complete
        else:
            current_loop_logger.info(f"Processing {len(tool_calls)} tool call(s)...")
            # Process tool calls one by one
            for tool_call in tool_calls:
                 # Decision: Use the llm_action_id for subsequent tool calls in this loop iteration
                 # This simplifies tracing for a single LLM turn, sacrificing granularity
                 # between multiple tool calls within the same turn.
                 # We could generate a unique tool_action_id = str(uuid.uuid4()) here if needed.
                # tool_action_id = str(uuid.uuid4())
                # tool_loop_logger = current_loop_logger.bind(action_id=tool_action_id) # Bind for tool logging
                tool_loop_logger = current_loop_logger # Use the logger already bound with llm_action_id
                
                tool_id = tool_call.get("id")
                function_call = tool_call.get("function")
                if not tool_id or not function_call or not isinstance(function_call, dict):
                    tool_loop_logger.error(f"Skipping invalid tool call structure: {tool_call}")
                    continue
                
                function_name = function_call.get("name")
                function_args_str = function_call.get("arguments", "{}")
                tool_loop_logger.info(f"Executing tool: {function_name} (ID: {tool_id})")
                
                try:
                    # Parse arguments
                    arguments = json.loads(function_args_str)
                    tool_loop_logger.debug(f"Parsed arguments for {function_name}: {arguments}")
                    
                    # Execute the tool using mcp_handler
                    # Pass user_request_id and the llm_action_id from this loop iteration
                    tool_result = execute_mcp_tool(
                        tool_name=function_name, 
                        params=arguments,
                        user_request_id=user_req_id, 
                        action_id=llm_action_id # Use llm_action_id here
                    )
                    
                    # Format result for the LLM
                    tool_result_content = json.dumps(tool_result) if tool_result is not None else "null"
                    tool_loop_logger.debug(f"Tool {function_name} execution result: {tool_result_content[:200]}...") # Log snippet

                    # Add tool result message to history for the next LLM iteration
                    st.session_state.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": tool_result_content, # Send result back as JSON string
                            # "name": function_name # OpenAI includes name here, Gemini doesn't use it like this
                        }
                    )
                except json.JSONDecodeError as json_err:
                    error_content = f"Error parsing arguments for {function_name}: {json_err}"
                    tool_loop_logger.error(error_content)
                    st.error(error_content)
                    st.session_state.messages.append({"role": "tool", "tool_call_id": tool_id, "content": error_content})
                except Exception as tool_err:
                    error_content = f"Error executing tool {function_name}: {tool_err}"
                    tool_loop_logger.error(error_content, exc_info=True)
                    st.error(error_content)
                    st.session_state.messages.append({"role": "tool", "tool_call_id": tool_id, "content": error_content})
            # Continue loop to send tool results back to LLM
            # No break here - loop continues automatically
    # --- Loop End --- 

# --- User Input Handling --- 
if prompt := st.chat_input("What can I help you with?"):
    if not provider:
        st.error("Please configure an API key and select a provider.")
        logger.warning("User submitted prompt but no provider was configured/selected.")
    else:
        user_request_id = str(uuid.uuid4())
        bound_logger = logger.bind(user_request_id=user_request_id)
        bound_logger.info(f"Received new user prompt (Provider: {provider})")

        # Append user message with ID to history
        user_message = {"role": "user", "content": prompt, "user_request_id": user_request_id}
        st.session_state.messages.append(user_message)
        
        # Immediately display user message
        with st.chat_message("user"):
            st.markdown(prompt)
            st.caption(f"Request ID: `{user_request_id}`")

        # Call the refactored execution loop
        run_execution_loop(provider=provider, model_name=model_name, base_sys_prompt=base_system_prompt, user_req_id=user_request_id)

# End of file - No changes needed below last removed section 