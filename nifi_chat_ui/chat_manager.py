from __future__ import annotations # Add this import for forward references

# Placeholder for LLM interaction logic 

import google.generativeai as genai
from openai import OpenAI # Import OpenAI
import uuid # Added missing import
# Import config from new location
try:
    from config import settings as config 
except ImportError:
    # Need logger here, but setup might not have run. Use basic print.
    print("ERROR [chat_manager.py]: Failed to import config.settings.", file=sys.stderr)
    # Re-raise or handle gracefully depending on whether this module can run without config
    raise 

import streamlit as st # Import streamlit for UI error messages
import json
from typing import List, Dict, Any, Optional
# Import mcp_handler carefully, assuming it's in the same directory or PYTHONPATH
try:
    from .mcp_handler import get_available_tools, execute_mcp_tool
except ImportError:
    # Fallback if run as script or structure changes
    from mcp_handler import get_available_tools, execute_mcp_tool 
import sys
from loguru import logger # Import Loguru logger

# Import tiktoken for accurate OpenAI token counting
try:
    import tiktoken
    tiktoken_available = True
except ImportError:
    tiktoken_available = False
    logger.warning("tiktoken not available, OpenAI token counting will use approximation.") # Use logger

# Import Gemini types for correct tool formatting
try:
    # Try importing the modules first
    import google.generativeai.types as genai_types 
    # Then access the specific classes
    Tool = genai_types.Tool
    FunctionDeclaration = genai_types.FunctionDeclaration
    gemini_types_imported = True
except ImportError as e:
    # Use logger for internal errors
    logger.error(f"Failed to import google.generativeai.types: {e}", exc_info=True)
    gemini_types_imported = False
    Tool = None
    FunctionDeclaration = None
except AttributeError as e:
    logger.error(f"Failed to access attributes within google.generativeai.types: {e}", exc_info=True)
    gemini_types_imported = False
    Tool = None
    FunctionDeclaration = None
except Exception as e:
    # Catch any other unexpected import errors
    logger.error(f"An unexpected error occurred during google.generativeai.types import: {e}", exc_info=True)
    gemini_types_imported = False
    Tool = None
    FunctionDeclaration = None

# --- Client Initialization --- #
# gemini_model = None # Store the initialized model - Removed, will instantiate per request
openai_client = None
# azure_openai_client = None  
azure_openai_clients: dict[str, "AzureOpenAI"] = {}   # keyed by api-version
is_initialized = False # Flag to track whether LLM clients have been initialized 

def configure_llms():
    """Configures LLM clients based on available keys and models."""
    # global gemini_model, openai_client, is_initialized # Removed gemini_model
    global openai_client, is_initialized, azure_openai_clients 
    
    # Configure Gemini (only API key setup here)
    if config.GOOGLE_API_KEY:
        try:
            genai.configure(api_key=config.GOOGLE_API_KEY)
            # Don't instantiate a specific model here
            # We need the model name which comes per request
            logger.info(f"Gemini API key configured. Available models: {config.GEMINI_MODELS}")
        except Exception as e:
            # Log internal error, avoid UI warning during import
            logger.error(f"Failed to configure Gemini API key: {e}", exc_info=True)
            # We don't nullify anything here, maybe the key is valid but listing models failed?

    # Configure OpenAI client
    # Always reinitialize when this function is called
    if config.OPENAI_API_KEY:
        try:
            # First set to None to force a clean initialization
            openai_client = None
            
            # Ensure we have a fresh API key value
            api_key = str(config.OPENAI_API_KEY).strip()
            if not api_key:
                logger.error("OpenAI API key is empty or whitespace")
                openai_client = None
                # Need to handle this failure state better - perhaps return False?
                is_initialized = False # Mark as not initialized if key is bad
                return # Don't proceed if key is bad
            
            # Create a new client with explicit parameters
            logger.debug(f"Creating new OpenAI client with API key (length: {len(api_key)})")
            openai_client = OpenAI(
                api_key=api_key,
                timeout=60.0,  # Explicit timeout
                max_retries=2  # Limit retries to avoid hanging
            )
            
            # Test the client with a minimal API call
            logger.debug("Testing OpenAI client with models.list()...")
            _ = openai_client.models.list() # Use list instead of retrieve which needs a model name
            
            logger.info(f"OpenAI client configured. Available models: {config.OPENAI_MODELS}")
        except Exception as e:
            # Log internal error, avoid UI warning during import
            logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            openai_client = None
            # is_initialized = False # Mark as not initialized if setup fails - Handled below
     
    # --- Configure Azure OpenAI (handles **all** deployments) --- #
    if config.AZURE_OPENAI_API_KEY and config.AZURE_OPENAI_ENDPOINT:
        try:
            from openai import AzureOpenAI

            azure_openai_clients.clear()                     # reset on hot-reload
            api_key   = config.AZURE_OPENAI_API_KEY.strip()
            endpoint  = config.AZURE_OPENAI_ENDPOINT.strip()

            for meta in config.AZURE_OPENAI_DEPLOYMENTS.values():
                ver = meta["api_version"]
                if ver in azure_openai_clients:
                    continue                                 # one client per version
                azure_openai_clients[ver] = AzureOpenAI(
                    api_key        = api_key,
                    azure_endpoint = endpoint,
                    api_version    = ver,
                    timeout        = 60.0,
                    max_retries    = 2,
                )
            logger.info(f"Azure OpenAI: initialised {len(azure_openai_clients)} client(s) "
                        f"for versions {list(azure_openai_clients.keys())}")
        except Exception as e:
            logger.error(f"Failed to initialise Azure OpenAI clients: {e}", exc_info=True)
            azure_openai_clients.clear()


    # Update initialization status based on whether *at least one* client/key is ready
    # And if *at least one* model list is non-empty for the configured keys
    gemini_ready = bool(config.GOOGLE_API_KEY and config.GEMINI_MODELS)
    openai_ready = bool(openai_client and config.OPENAI_MODELS) # Check client and models
    azure_openai_ready = bool(azure_openai_clients)
    
    is_initialized = gemini_ready or openai_ready or azure_openai_ready
    
    if not is_initialized:
         logger.warning("LLM configuration incomplete: No valid API key and corresponding model list found.")
    else:
         logger.info(f"LLM configuration status: Gemini Ready={gemini_ready}, OpenAI Ready={openai_ready}, Azure Ready={azure_openai_ready}")


# Do NOT call configure_llms() during module import as it can cause
# Streamlit errors with set_page_config(). Instead, we'll call this
# function from app.py after setting the page config.

# --- Tool Management --- #

# @st.cache_data(ttl=3600) # Consider caching if MCP calls are slow
def get_formatted_tool_definitions(
    provider: str,
    raw_tools: list[dict] | None, # Accept raw tools as input
    user_request_id: str | None = None
) -> List[Dict[str, Any]] | List["genai_types.FunctionDeclaration"] | None:
    """Formats a given list of raw tool definitions for the specified LLM provider."""
    bound_logger = logger.bind(user_request_id=user_request_id) # Bind context
    global FunctionDeclaration  # Make FunctionDeclaration accessible in function scope
    
    # Convert provider to lowercase for case-insensitive comparison
    provider = provider.lower()
    bound_logger.debug(f"Formatting tools for provider: {provider}")
    
    # Use the provided raw_tools list instead of fetching
    # tools = get_available_tools(user_request_id=user_request_id) # REMOVED fetch
    tools = raw_tools # Use the passed-in list
    
    if not tools:
        bound_logger.warning("No raw tools provided for formatting.")
        # st.warning("Failed to retrieve tools from MCP handler.") # Don't show UI warning here
        return None # Return None if fetching failed

    if provider in ["openai", "azure-openai"]:
        # OpenAI format matches our API format directly, but let's clean up the schema
        cleaned_tools = []
        for tool in tools:
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                function_def = tool["function"]
                tool_name = function_def.get("name", "") # Get tool name for specific fixes
                
                # Clean up parameters if present
                if "parameters" in function_def and isinstance(function_def["parameters"], dict):
                    params = function_def["parameters"]
                    # Remove top-level additionalProperties field which might cause issues
                    params.pop("additionalProperties", None)
                    
                    # Clean individual properties
                    if "properties" in params and isinstance(params["properties"], dict):
                        props = params["properties"]
                        for prop_name, prop_value in props.items():
                            # Ensure prop_value is a dict before cleaning
                            if isinstance(prop_value, dict):
                                prop_value.pop("additionalProperties", None)
                            # If prop_value is not a dict or becomes empty after cleaning, set default type
                            if not isinstance(prop_value, dict) or not prop_value:
                                bound_logger.debug(f"Setting default type 'string' for empty/invalid property '{prop_name}' in tool '{tool_name}'")
                                props[prop_name] = {"type": "string"} # Default to string type
                                prop_value = props[prop_name] # Update prop_value for subsequent checks
                            
                            # --- SPECIFIC FIX for update_nifi_processor_config.update_data --- 
                            if tool_name == "update_nifi_processor_config" and prop_name == "update_data":
                                bound_logger.debug(f"Applying specific schema fix for {tool_name}.{prop_name}")
                                props[prop_name] = {
                                    # Keep original description if available
                                    "description": prop_value.get("description", "A dictionary (for 'properties') or list (for 'relationships') representing the update."),
                                    # Use anyOf to represent Union[Dict, List]
                                    "anyOf": [
                                        { "type": "object" },
                                        { 
                                            "type": "array",
                                            "items": { "type": "string" } # Specify items are strings
                                        }
                                    ]
                                }
                            # --- END SPECIFIC FIX --- 
                
                cleaned_tools.append(tool)
        
        bound_logger.debug(f"Formatted {len(cleaned_tools)} tools for OpenAI.")
        return cleaned_tools
    elif provider == "gemini":
        if not gemini_types_imported:
            bound_logger.error("Required google-generativeai types could not be imported. Cannot format tools for Gemini.")
            st.error("Required google-generativeai types could not be imported. Cannot format tools for Gemini.") # Keep UI error
            return None
            
        if not FunctionDeclaration:
            bound_logger.error("Gemini FunctionDeclaration class is not available. Cannot format tools.")
            st.error("Internal Error: Gemini FunctionDeclaration class is not available.") # Keep UI error
            return None
        
        # Convert OpenAI format list to a list containing Gemini FunctionDeclaration objects
        all_declarations = []
        
        for tool_data in tools:
            func_details = tool_data.get("function", {})
            name = func_details.get("name")
            description = func_details.get("description")
            parameters_schema = func_details.get("parameters") 
            
            if not name or not description:
                continue
                
            # Clean up parameters schema for Gemini
            cleaned_schema = parameters_schema.copy() if parameters_schema else {}
            if isinstance(cleaned_schema, dict):
                # Always set top-level type to OBJECT if it has properties
                if "properties" in cleaned_schema:
                    cleaned_schema["type"] = "OBJECT"
                
                # Recursively clean properties and array items
                def clean_gemini_schema(schema_node):
                    if not isinstance(schema_node, dict):
                        return schema_node

                    # Remove problematic fields
                    schema_node.pop("additionalProperties", None)
                    
                    # Handle properties
                    if "properties" in schema_node:
                        # If we have properties, this must be an OBJECT type
                        schema_node["type"] = "OBJECT"
                        props = schema_node["properties"]
                        for prop_name, prop_value in list(props.items()): # Use list for safe iteration
                            if isinstance(prop_value, dict):
                                # Clean nested schema
                                props[prop_name] = clean_gemini_schema(prop_value.copy())
                                # Ensure type is specified
                                if "type" not in props[prop_name]:
                                    if "properties" in props[prop_name]:
                                        props[prop_name]["type"] = "OBJECT"
                                    elif "items" in props[prop_name]:
                                        props[prop_name]["type"] = "ARRAY"
                                    else:
                                        props[prop_name]["type"] = "STRING"
                                # Convert type to uppercase for Gemini
                                if "type" in props[prop_name]:
                                    props[prop_name]["type"] = props[prop_name]["type"].upper()
                            else:
                                # Non-dict properties default to STRING type
                                props[prop_name] = {"type": "STRING"}
                    
                    # Handle arrays
                    if "items" in schema_node:
                        schema_node["type"] = "ARRAY"
                        if isinstance(schema_node["items"], dict):
                            schema_node["items"] = clean_gemini_schema(schema_node["items"].copy())
                    
                    # Ensure type is uppercase for Gemini
                    if "type" in schema_node:
                        schema_node["type"] = schema_node["type"].upper()
                    elif not any(key in schema_node for key in ["properties", "items", "enum"]):
                        # If no type and no complex structure, default to STRING
                        schema_node["type"] = "STRING"
                    
                    return schema_node

                cleaned_schema = clean_gemini_schema(cleaned_schema)
                # Use a different variable name to avoid confusion if cleaning returns None unexpectedly
                schema_to_use = cleaned_schema if cleaned_schema is not None else {"type": "OBJECT", "properties": {}}

            # Create FunctionDeclaration with the fully cleaned schema
            try:
                 declaration = FunctionDeclaration(
                     name=name,
                     description=description,
                     parameters=schema_to_use # Use the cleaned schema 
                 )
                 all_declarations.append(declaration)
            except Exception as decl_error:
                 # Log internal error, show UI warning
                 bound_logger.error(f"Error creating FunctionDeclaration for '{name}': {decl_error}. Schema: {json.dumps(schema_to_use, indent=2)}", exc_info=True)
                 # print(f"ERROR creating FunctionDeclaration for '{name}': {decl_error}", file=sys.stderr)
                 # print(f"Schema that caused error: {json.dumps(schema_to_use, indent=2)}", file=sys.stderr)
                 st.warning(f"Skipping tool '{name}' due to schema error during FunctionDeclaration creation.") # Simplified UI warning
                 continue # Skip to the next tool
            
        if not all_declarations:
            bound_logger.warning("No valid tool declarations found after formatting for Gemini.")
            st.warning("No valid tool declarations could be formatted for Gemini.") # Keep UI warning
            return None
        
        bound_logger.debug(f"Formatted {len(all_declarations)} tools for Gemini.")
        return all_declarations
    else:
        bound_logger.error(f"Unsupported LLM provider for tool formatting: {provider}")
        st.error(f"Unsupported LLM provider for tool formatting: {provider}") # Keep UI error
        return None

# --- Helper Functions --- #

def count_tokens_openai(text: str, model: str) -> int: # Require model name
    """Count tokens using OpenAI's tiktoken library"""
    if not tiktoken_available:
        # Fallback to approximation if tiktoken isn't available
        return len(text.split())
    
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Error counting tokens with tiktoken for model {model}: {e}. Using approximation.") # Use logger
        return len(text.split())

def count_tokens_gemini(text: str) -> int:
    """Approximate token count for Gemini models (character-based estimate)"""
    # For Gemini, we'll use a character-based estimate since there's no official tokenizer
    # Roughly 4 characters per token is a common approximation
    return len(text) // 4

def calculate_input_tokens(messages: List[Dict], provider: str, model_name: str) -> int: # Added model_name
    """Calculate total input tokens based on message history and provider."""
    total_tokens = 0
    # model_name = config.OPENAI_MODEL if provider.lower() == "openai" else config.GEMINI_MODEL # Removed

    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            if provider.lower() == "openai":
                total_tokens += count_tokens_openai(content, model_name)
            else:
                total_tokens += count_tokens_gemini(content)
        # Add rough estimate for tool calls/results if needed
        elif message.get("role") == "tool":
            # Simple approximation for tool results
            total_tokens += len(str(content)) // 4 
        elif isinstance(message.get("tool_calls"), list):
            # Simple approximation for tool requests
            total_tokens += len(json.dumps(message["tool_calls"])) // 4
            
    # logger.debug(f"Calculated input tokens: {total_tokens} for {provider}") # Optional: Log token count
    return total_tokens

# --- Core LLM Interaction Functions --- #

def get_gemini_response(
    messages: List[Dict[str, Any]], 
    system_prompt: str,
    tools: List["genai_types.FunctionDeclaration"] | None, # Gemini requires FunctionDeclaration
    model_name: str, # Added: Specific model to use
    user_request_id: str | None = None, # Added context ID
    action_id: str | None = None # Added: Specific action ID for this LLM call
) -> Dict[str, Any]:
    """Gets a response from the Gemini model, handling potential tool calls."""
    # Bind both user_request_id and action_id to the logger
    bound_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)

    tool_id_to_name_map = {} # Initialize the map here

    if not config.GOOGLE_API_KEY: # Check if API key is configured
        bound_logger.error("Gemini API key not configured. Cannot get response.")
        # Use st.error in the calling function (app.py) if needed for UI feedback
        return {"error": "Gemini API key not configured."}
        
    if not model_name or model_name not in config.GEMINI_MODELS:
        bound_logger.error(f"Invalid or missing Gemini model specified: {model_name}. Available: {config.GEMINI_MODELS}")
        return {"error": f"Invalid Gemini model specified: {model_name}"}

    # --- Instantiate Gemini Model ---
    try:
        bound_logger.debug(f"Instantiating Gemini model: {model_name}")
        model_instance = genai.GenerativeModel(
            model_name,
            # system_instruction=system_prompt # Apply system prompt during generation if supported this way, else prepend
        )
        bound_logger.info(f"Using Gemini model: {model_name}")
    except Exception as e:
        bound_logger.error(f"Failed to instantiate Gemini model {model_name}: {e}", exc_info=True)
        return {"error": f"Failed to instantiate Gemini model {model_name}: {str(e)}"}
    # -----------------------------

    # Prepare messages: Prepend system prompt if necessary and convert format
    gemini_history = []
    system_instruction_applied = False
    
    # First pass: identify assistant tool calls and build ID-to-name mapping
    for msg in messages:
        if msg["role"] == "assistant" and "tool_calls" in msg:
            for tc in msg.get("tool_calls", []):
                if tc.get("id") and tc.get("function", {}).get("name"):
                    tool_id_to_name_map[tc["id"]] = tc["function"]["name"]
                    bound_logger.debug(f"Mapped tool ID {tc['id']} to function name {tc['function']['name']}")

    # Second pass: convert messages to Gemini format
    for msg in messages:
        role = msg["role"]
        content = msg.get("content")
        tool_calls = msg.get("tool_calls") # OpenAI format
        tool_call_id = msg.get("tool_call_id") # For tool role
        
        # Convert OpenAI roles to Gemini roles
        if role == "user":
            gemini_role = "user"
        elif role == "assistant":
            gemini_role = "model" 
        elif role == "tool":
            gemini_role = "function"
        else:
            bound_logger.warning(f"Unknown role in message: {role}, defaulting to user")
            gemini_role = "user"
        
        # For regular text messages
        if role in ["user", "assistant"] and content:
            gemini_history.append({"role": gemini_role, "parts": [content]})

        # Handle Assistant requesting tool calls (OpenAI format -> Gemini format)
        if role == "assistant" and tool_calls:
            # Build a message with both content and function call if available
            parts = []
            if content:
                parts.append(content)
            
            # Create function call parts
            for tc in tool_calls:
                function_call = tc.get("function")
                if function_call:
                    # Parse arguments as JSON
                    try:
                        args = json.loads(function_call.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                        bound_logger.warning(f"Failed to parse arguments for function {function_call.get('name')}")
                    
                    # Create the function call dictionary
                    fc_dict = {
                        "function_call": {
                            "name": function_call.get("name"),
                            "args": args
                        }
                    }
                    parts.append(fc_dict)
            
            # Only add if we have parts
            if parts:
                gemini_history.append({"role": gemini_role, "parts": parts})
        
        # Handle Tool execution results using Gemini's function format
        elif role == "tool" and tool_call_id:
            # Look up the function name from our mapping
            function_name = tool_id_to_name_map.get(tool_call_id)
            
            if not function_name:
                bound_logger.warning(f"Could not find function name for tool_call_id: {tool_call_id}. Using generic name.")
                function_name = f"unknown_function_{tool_call_id[-6:]}"
            
            # Parse the content - should be JSON if possible
            try:
                if isinstance(content, str):
                    if content.strip().startswith(("{", "[")):
                        result_content = json.loads(content)
                    else:
                        # For non-JSON strings, wrap in a result object
                        result_content = {"result": content}
                else:
                    # For non-string content (should be rare)
                    result_content = {"result": str(content)}
            except json.JSONDecodeError:
                bound_logger.warning(f"Failed to parse tool result as JSON: {content[:100]}...")
                result_content = {"result": content}
            
            # Convert lists to a specific structure for Gemini that doesn't cause items() errors
            if isinstance(result_content, list):
                # Wrap the list in a dictionary with a 'results' key
                result_content = {"results": result_content}
                bound_logger.debug(f"Converted list result to dictionary with 'results' key for {function_name}")
            
            # Add the function result in Gemini format
            gemini_history.append({
                "role": "function",
                "parts": [{
                    "function_response": {
                        "name": function_name,
                        "response": result_content
                    }
                }]
            })
        
    bound_logger.debug(f"Prepared Gemini history with {len(gemini_history)} entries.")
    
    try:
        # Configure the model instance with the system prompt for this call
        model_instance = genai.GenerativeModel(
             model_name, 
             system_instruction=system_prompt
        )
        
        # --- Log LLM Request ---
        
        # Helper function to safely serialize tools for logging
        def _safe_serialize_tools(tools_list):
            if not tools_list:
                return None
                
            safe_tools = []
            for tool in tools_list:
                # Handle Schema objects safely to avoid serialization errors
                if hasattr(tool, 'parameters'):
                    # Convert Schema to string representation for logging
                    params_str = str(tool.parameters) if tool.parameters else None
                    safe_tool = {
                        'name': getattr(tool, 'name', None),
                        'description': getattr(tool, 'description', None),
                        'parameters_str': params_str  # Use string representation
                    }
                    safe_tools.append(safe_tool)
                else:
                    # If it's not the expected structure, convert whole object to string
                    safe_tools.append(str(tool))
            
            return safe_tools

        request_payload = {
            "model": model_name,
            "history": gemini_history, # Log prepared history
            # Use helper function to safely serialize tools for logging
            "tools": _safe_serialize_tools(tools), 
            "system_instruction": system_prompt,
            # Add relevant generation_config if needed
        }
        bound_logger.bind(
            interface="llm", 
            direction="request", 
            data=request_payload
        ).debug("Sending request to Gemini API")
        # -----------------------
        
        # Generate content
        bound_logger.info(f"Sending request to Gemini model: {model_name}") # Use model_name
        
        # Add more debug tracing before the API call
        bound_logger.debug(f"Gemini history structure: {json.dumps([{'role': item.get('role'), 'parts_count': len(item.get('parts', []))} for item in gemini_history], indent=2)}")
        
        try:
            response = model_instance.generate_content(
                gemini_history,
                tools=tools if tools else None,
                # tool_config=genai_types.ToolConfig(function_calling_config="AUTO") # Let Gemini decide
                generation_config=genai.types.GenerationConfig(
                    # candidate_count=1, # Defaults to 1
                    # stop_sequences=['...'],
                    # max_output_tokens=2048,
                    temperature=0.3, # Adjust creativity/predictability - REDUCED from 0.7
                )
            )
            bound_logger.info("Received response from Gemini model.")
        except Exception as api_error:
            # Catch specific API call failures
            bound_logger.error(f"API call to Gemini failed: {api_error}", exc_info=True)
            return {"error": f"API call failed: {str(api_error)}"}

        # --- Log LLM Response --- 
        try:
            # Define helper functions for safe serialization
            def _safe_part_to_dict(part):
                if not part: 
                    return None
                data = {}
                
                # Handle text
                if hasattr(part, 'text') and part.text:
                    data['text'] = part.text
                
                # Handle function_call
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    try:
                        # Try to convert MapComposite args to dict
                        args_dict = dict(fc.args) if hasattr(fc, 'args') and fc.args else {}
                    except:
                        # If conversion fails, use string representation
                        args_dict = str(fc.args) if hasattr(fc, 'args') else {}
                    
                    data['function_call'] = {'name': fc.name, 'args': args_dict}
                
                # Handle function_response
                if hasattr(part, 'function_response') and part.function_response:
                    fr = part.function_response
                    # Handle response data safely
                    response_data = fr.response
                    try:
                        # If dict-like, convert to dict
                        if isinstance(response_data, dict) or (hasattr(response_data, 'items') and callable(response_data.items)):
                            response_data = dict(response_data)
                        # Lists should be preserved as lists
                        elif isinstance(response_data, list):
                            # No conversion needed for lists, already JSON serializable
                            pass
                        # Basic check if serializable, otherwise convert to string
                        json.dumps(response_data)
                    except (TypeError, OverflowError):
                        response_data = str(response_data) # Fallback to string
                    
                    data['function_response'] = {'name': fr.name, 'response': response_data}
                
                return data
            
            def _safe_candidate_to_dict(candidate):
                if not candidate: 
                    return None
                    
                # Extract parts safely
                parts = []
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        parts.append(_safe_part_to_dict(part))
                
                return {'parts': parts}
                
            # Safely serialize the response for logging
            response_data = {
                'candidates': [_safe_candidate_to_dict(c) for c in response.candidates] if hasattr(response, 'candidates') else None,
                'prompt_feedback': None # Add prompt feedback serialization if needed
            }
            # Log the response data
            bound_logger.bind(
                interface="llm", 
                direction="response", 
                data=response_data
            ).debug("Received response from Gemini API")
        except Exception as logging_error:
            bound_logger.error(f"Error logging Gemini response (logging error only): {logging_error}", exc_info=True)
            # Continue processing response despite logging error
        # -----------------------

        # Check response structure before processing
        if not hasattr(response, 'parts'):
            bound_logger.error(f"Unexpected Gemini response structure - missing 'parts' attribute. Response type: {type(response)}")
            
            # Debug the response structure
            response_attrs = dir(response)
            bound_logger.debug(f"Response attributes: {response_attrs}")
            
            # Check for candidates
            if hasattr(response, 'candidates'):
                bound_logger.debug(f"Response has {len(response.candidates)} candidates")
                
                # Extract parts from first candidate if available
                if response.candidates and hasattr(response.candidates[0], 'content'):
                    candidate_content = response.candidates[0].content
                    if hasattr(candidate_content, 'parts'):
                        bound_logger.debug(f"Using parts from first candidate instead")
                        # Use the first candidate's parts
                        response_parts = candidate_content.parts
                    else:
                        bound_logger.error("Candidate content doesn't have parts either")
                        response_parts = []
                else:
                    bound_logger.error("No usable content in candidates")
                    response_parts = []
            else:
                bound_logger.error("No candidates available in response")
                response_parts = []
        else:
            response_parts = response.parts
        
        # Parse the response into a standardized format matching our API
        response_content = None
        response_tool_calls = []
        
        # Check for function calls in the response parts with better error handling
        if response_parts:
            bound_logger.debug(f"Processing {len(response_parts)} parts from response")
            for i, part in enumerate(response_parts):
                try:
                    # Debug the part structure
                    part_attrs = dir(part)
                    bound_logger.debug(f"Part {i} attributes: {part_attrs}")
                    
                    if hasattr(part, 'text') and part.text:
                        response_content = part.text
                        bound_logger.debug(f"Found text content in part {i}")
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        bound_logger.debug(f"Found function_call in part {i}")
                        # Convert Gemini FunctionCall back to OpenAI format ToolCall
                        fc = part.function_call
                        
                        # Debug the function call structure
                        fc_attrs = dir(fc)
                        bound_logger.debug(f"Function call attributes: {fc_attrs}")
                        
                        # More careful args handling
                        if hasattr(fc, 'args'):
                            if isinstance(fc.args, dict):
                                args_str = json.dumps(fc.args)
                            elif hasattr(fc.args, 'items') and callable(fc.args.items):
                                # It's dict-like but not a dict
                                args_str = json.dumps(dict(fc.args))
                            else:
                                # Not a dict or dict-like, convert to string
                                args_str = json.dumps({"raw_args": str(fc.args)})
                        else:
                            args_str = "{}"
                        
                        response_tool_calls.append({
                            "id": str(uuid.uuid4()), # Generate shorter ID (just UUID)
                            "type": "function",
                            "function": {
                                "name": fc.name,
                                "arguments": args_str
                            }
                        })
                        bound_logger.debug(f"Added tool call for function: {fc.name}")
                except Exception as part_error:
                    bound_logger.error(f"Error processing response part {i}: {part_error}", exc_info=True)
                    # Continue with other parts
        else:
            bound_logger.warning("No parts found in the Gemini response")
        
        # Calculate token counts
        token_count_in = calculate_input_tokens(messages, "Gemini", model_name)
        token_count_out = count_tokens_gemini(response_content if response_content else "") if response_content else 0
        bound_logger.debug(f"Token counts - In: {token_count_in}, Out: {token_count_out}")

        # Log the response details
        bound_logger.debug(f"Gemini Response: Content={response_content is not None}, ToolCalls={len(response_tool_calls)}")

        return {
            "content": response_content, 
            "tool_calls": response_tool_calls,
            "token_count_in": token_count_in,
            "token_count_out": token_count_out
        }

    except Exception as e:
        bound_logger.error(f"Error during Gemini API call: {e}", exc_info=True)
        st.error(f"An error occurred while communicating with the Gemini API: {e}")
        return {"error": str(e)}

def get_openai_response(
    messages: List[Dict[str, Any]], 
    system_prompt: str, 
    tools: List[Dict[str, Any]] | None, # OpenAI uses dict format
    model_name: str, # Added: Specific model to use
    user_request_id: str | None = None, # Added context ID
    action_id: str | None = None # Added: Specific action ID for this LLM call
) -> Dict[str, Any]:
    """Gets a response from the OpenAI model, handling potential tool calls."""
    # Bind both user_request_id and action_id to the logger
    bound_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)

    if not openai_client: # Check if client was configured
        bound_logger.error("OpenAI client is not configured. Cannot get response.")
        # UI error handled by calling function
        return {"error": "OpenAI not configured or configuration failed."}
        
    if not model_name or model_name not in config.OPENAI_MODELS:
        bound_logger.error(f"Invalid or missing OpenAI model specified: {model_name}. Available: {config.OPENAI_MODELS}")
        return {"error": f"Invalid OpenAI model specified: {model_name}"}

    # Prepend system prompt as the first message if not already present
    openai_messages = messages.copy()
    if not openai_messages or openai_messages[0]["role"] != "system":
        openai_messages.insert(0, {"role": "system", "content": system_prompt})
    
    bound_logger.debug(f"Prepared OpenAI messages with {len(openai_messages)} entries.")

    try:
        bound_logger.info(f"Sending request to OpenAI model: {model_name}") # Use model_name
        
        # Double-check that client is properly initialized before making API call
        if openai_client is None:
            bound_logger.error("OpenAI client is not initialized or was incorrectly initialized.")
            st.error("OpenAI client not initialized. Please check your API key and try again.")
            return {"error": "OpenAI client not initialized. Please check your API key and try again."}
        
        # --- Log LLM Request ---
        request_payload = {
            "model": model_name, # Use model_name
            "messages": openai_messages,
            "tools": tools,
            "tool_choice": "auto" if tools else None,
            #"temperature": 0.7,
        }
        bound_logger.bind(
            interface="llm", 
            direction="request", 
            data=request_payload
        ).debug("Sending request to OpenAI API")
        # -----------------------
        
        # Try a small API call first to verify the client is working
        try:
            bound_logger.debug("Verifying OpenAI client is working...")
            # Simply check if we can retrieve the model info without errors
            try:
                _ = openai_client.models.retrieve(model_name) # Use model_name
                bound_logger.debug("OpenAI client verification successful.")
            except Exception as model_error:
                # Try models.list() as a fallback
                bound_logger.warning(f"Could not retrieve specific model: {model_error}. Trying models.list() instead.")
                models = openai_client.models.list()
                if not models or not hasattr(models, 'data') or not models.data:
                    raise ValueError("Models list is empty or invalid")
                bound_logger.debug(f"OpenAI client verification with models.list successful. Found {len(models.data)} models.")
        except Exception as verify_error:
            bound_logger.error(f"OpenAI client verification failed: {verify_error}", exc_info=True)
            st.error(f"OpenAI client verification failed: {str(verify_error)}")
            return {"error": f"OpenAI client verification failed: {str(verify_error)}"}
        
        # Now attempt the actual completions API call
        bound_logger.debug(f"Sending messages to OpenAI: {json.dumps(openai_messages, indent=2)}") # Log the exact payload
        response = openai_client.chat.completions.create(
            model=model_name, # Use model_name
            messages=openai_messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            #temperature=0.7,
        )
        bound_logger.info("Received response from OpenAI model.")
        
        # --- Log LLM Response --- 
        try:
            # Safely convert response object to dict for logging
            # Use a safer approach than model_dump() which might raise errors
            response_dict = {}
            
            # Extract only the fields we need
            if hasattr(response, 'id'):
                response_dict['id'] = response.id
                
            if hasattr(response, 'choices') and response.choices:
                # Safe extraction of choices
                choices = []
                for choice in response.choices:
                    choice_dict = {'index': getattr(choice, 'index', 0)}
                    
                    # Extract message safely
                    if hasattr(choice, 'message'):
                        message = choice.message
                        message_dict = {
                            'role': getattr(message, 'role', None),
                            'content': getattr(message, 'content', None)
                        }
                        
                        # Handle tool calls safely
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            tool_calls = []
                            for tc in message.tool_calls:
                                tc_dict = {
                                    'id': getattr(tc, 'id', None),
                                    'type': getattr(tc, 'type', None),
                                }
                                
                                # Extract function data safely
                                if hasattr(tc, 'function'):
                                    tc_dict['function'] = {
                                        'name': getattr(tc.function, 'name', None),
                                        # Arguments might be JSON string - keep as is
                                        'arguments': getattr(tc.function, 'arguments', None)
                                    }
                                
                                tool_calls.append(tc_dict)
                            
                            message_dict['tool_calls'] = tool_calls
                        
                        choice_dict['message'] = message_dict
                    
                    # Add finish reason
                    if hasattr(choice, 'finish_reason'):
                        choice_dict['finish_reason'] = choice.finish_reason
                        
                    choices.append(choice_dict)
                
                response_dict['choices'] = choices
            
            # Add model and usage info if available
            if hasattr(response, 'model'):
                response_dict['model'] = response.model
                
            if hasattr(response, 'usage'):
                usage = response.usage
                response_dict['usage'] = {
                    'prompt_tokens': getattr(usage, 'prompt_tokens', 0),
                    'completion_tokens': getattr(usage, 'completion_tokens', 0),
                    'total_tokens': getattr(usage, 'total_tokens', 0)
                }
                
            response_data_for_log = response_dict
        except Exception as log_e:
            response_data_for_log = {"error": f"Failed to serialize OpenAI response for logging: {log_e}"}
            bound_logger.warning(f"Could not serialize OpenAI response for logging: {log_e}")
            
        bound_logger.bind(
            interface="llm", 
            direction="response", 
            data=response_data_for_log
        ).debug("Received response from OpenAI API")
        # ------------------------

        response_message = response.choices[0].message

        # Extract content and tool calls
        response_content = response_message.content
        response_tool_calls = response_message.tool_calls
        
        # Convert ToolCall objects to dictionaries if needed by app.py
        if response_tool_calls:
            response_tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in response_tool_calls
            ]
        
        # Calculate token counts - use OpenAI's reported usage when available
        token_count_in = getattr(response.usage, 'prompt_tokens', 0) if hasattr(response, 'usage') else calculate_input_tokens(messages, "OpenAI", model_name)
        token_count_out = getattr(response.usage, 'completion_tokens', 0) if hasattr(response, 'usage') else 0

        bound_logger.debug(f"Token counts - In: {token_count_in}, Out: {token_count_out}")
        bound_logger.debug(f"OpenAI Response: Content={response_content is not None}, ToolCalls={len(response_tool_calls) if response_tool_calls else 0}")

        return {
            "content": response_content, 
            "tool_calls": response_tool_calls,
            "token_count_in": token_count_in,
            "token_count_out": token_count_out
        }

    except Exception as e:
        # Log the type of the exception for better debugging
        bound_logger.error(f"Caught exception of type: {type(e).__name__}, message: {str(e)}")
        
        # Try to extract more details if it's an OpenAI API error
        error_details = str(e)
        if hasattr(e, 'response'): # Check if it might be an httpx.HTTPStatusError or similar
            try:
                response_content = e.response.text
                error_details = f"{str(e)} - Response: {response_content[:500]}" # Limit response length
            except Exception as inner_e:
                bound_logger.warning(f"Could not extract response details from exception: {inner_e}")
        elif hasattr(e, 'body'): # Check for OpenAI specific error body
             error_details = f"{str(e)} - Body: {getattr(e, 'body', None)}" 
        
        # Log the potentially more detailed error
        bound_logger.error(f"Error during OpenAI API call: {error_details}", exc_info=True)
        st.error(f"An error occurred while communicating with the OpenAI API: {error_details}")
        # Return the more detailed error string if available
        return {"error": error_details}

# Later add support for flag(--shorthills) based compilation
def get_azure_openai_response(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    tools: List[Dict[str, Any]] | None,
    model_name: str,                        # deployment name
    user_request_id: str | None = None,
    action_id: str | None = None,
) -> Dict[str, Any]:
    """Call any Azure deployment (gpt-4o, o1, o3-mini) with the right api-version & token param."""
    bound_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)

    # basic sanity
    meta = config.AZURE_OPENAI_DEPLOYMENTS.get(model_name)
    if meta is None:
        msg = f"Unknown Azure deployment: {model_name}"
        bound_logger.error(msg)
        return {"error": msg}

    api_version  = meta["api_version"]
    token_param  = meta["token_param"]
    client       = azure_openai_clients.get(api_version)

    if client is None:                              # client was never initialised
        msg = f"Azure client for api-version {api_version} is missing"
        bound_logger.error(msg)
        return {"error": msg}

    # build message list
    azure_messages = messages[:]
    if not azure_messages or azure_messages[0]["role"] != "system":
        azure_messages.insert(0, {"role": "system", "content": system_prompt})

    # prepare kwargs
    kwargs: Dict[str, Any] = {
        "model":        model_name,                 # deployment name
        "messages":     azure_messages,
        "tools":        tools or None,
        "tool_choice":  "auto" if tools else None,
        token_param:    1000,                       # default; call-site may override
    }

    # network call with basic retry
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        bound_logger.error(f"Azure call failed: {e}", exc_info=True)
        return {"error": str(e)}

    # normalise output
    resp_msg          = response.choices[0].message
    response_content  = resp_msg.content
    response_toolcalls = [
        {
            "id": tc.id,
            "type": tc.type,
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            },
        }
        for tc in (resp_msg.tool_calls or [])
    ]

   
    usage      = getattr(response, "usage", None)
    token_in   = getattr(usage, "prompt_tokens", 0)      # int or 0
    token_out  = getattr(usage, "completion_tokens", 0)  # int or 0


    return {
        "content":         response_content,
        "tool_calls":      response_toolcalls,
        "token_count_in":  token_in,
        "token_count_out": token_out,
    }

def candidate_to_dict(candidate):
    # Helper to convert Candidate object safely for logging
    if not candidate: return None
    return {
        "content": {"parts": [part_to_dict(p) for p in candidate.content.parts] if candidate.content else None},
        "finish_reason": str(candidate.finish_reason) if hasattr(candidate, 'finish_reason') else None,
        "safety_ratings": [rating_to_dict(r) for r in candidate.safety_ratings] if hasattr(candidate, 'safety_ratings') else None,
        # Add other fields like token_count if available/needed
    }

def part_to_dict(part):
    # Helper to convert Part object safely for logging
    if not part: return None
    data = {}
    if hasattr(part, 'text') and part.text:
        data['text'] = part.text
    if hasattr(part, 'function_call') and part.function_call:
        fc = part.function_call
        # Convert MapComposite args to dict *before* storing for logging
        args_dict = dict(fc.args) if hasattr(fc, 'args') else {}
        data['function_call'] = {'name': fc.name, 'args': args_dict}
    if hasattr(part, 'function_response') and part.function_response:
        fr = part.function_response
        # Handle response data safely
        response_data = fr.response
        try:
            # If dict-like, convert to dict
            if isinstance(response_data, dict) or (hasattr(response_data, 'items') and callable(response_data.items)):
                response_data = dict(response_data)
            # Lists should be preserved as lists
            elif isinstance(response_data, list):
                # No conversion needed for lists, already JSON serializable
                pass
            # Basic check if serializable, otherwise convert to string
            json.dumps(response_data)
        except (TypeError, OverflowError):
            response_data = str(response_data) # Fallback to string
        data['function_response'] = {'name': fr.name, 'response': response_data}
    # Add other part types if needed (e.g., inline_data)
    return data

def prompt_feedback_to_dict(feedback):
    # Helper to convert PromptFeedback object safely for logging
    if not feedback: return None
    return {
        "block_reason": str(feedback.block_reason) if hasattr(feedback, 'block_reason') else None,
        "safety_ratings": [rating_to_dict(r) for r in feedback.safety_ratings] if hasattr(feedback, 'safety_ratings') else None,
    }

def rating_to_dict(rating):
    # Helper to convert SafetyRating object safely for logging
    if not rating: return None
    return {
        "category": str(rating.category) if hasattr(rating, 'category') else None,
        "probability": str(rating.probability) if hasattr(rating, 'probability') else None,
        "blocked": rating.blocked if hasattr(rating, 'blocked') else None,
    }

# --- (Potentially other helper functions) --- 