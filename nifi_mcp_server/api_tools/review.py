import asyncio
from typing import List, Dict, Optional, Any, Union, Literal
from datetime import datetime # Added import

# Import necessary components from parent/utils
from loguru import logger # Keep global logger for potential module-level logging if needed
# Import mcp ONLY (client comes from context)
from ..core import mcp
# Removed nifi_api_client import
from .utils import (
    tool_phases,
    # ensure_authenticated, # Removed - authentication handled by factory
    _format_processor_summary,
    _format_connection_summary,
    _format_port_summary,
    filter_processor_data, # Keep if needed by helpers here
    filter_connection_data # Add missing import
)
# Keep NiFiClient type hint and error imports
from nifi_mcp_server.nifi_client import NiFiClient, NiFiAuthenticationError
from mcp.server.fastmcp.exceptions import ToolError

# Import flow documentation tools specifically needed by document_nifi_flow
from nifi_mcp_server.flow_documenter import (
    extract_important_properties,
    analyze_expressions,
    build_graph_structure,
    format_connection,
    find_decision_branches
)

# Import context variables
from ..request_context import current_nifi_client, current_request_logger,current_process_group # Added
# Import new context variables for IDs
from ..request_context import current_user_request_id, current_action_id # Added


# --- Helper Functions (Now use context vars) --- 

async def _get_process_group_name(pg_id: str) -> str:
    """Helper to safely get a process group's name."""
    # Get client, logger, and IDs from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"

    if not nifi_client:
        local_logger.error("NiFi client not found in context for _get_process_group_name")
        return f"Error PG ({pg_id})"
        
    if pg_id == "root":
        return "Root"
    try:
        # Pass IDs directly to client method
        details = await nifi_client.get_process_group_details(
            pg_id, user_request_id=user_request_id, action_id=action_id
        )
        return details.get("component", {}).get("name", f"Unnamed PG ({pg_id})")
    except (ConnectionError, ValueError, NiFiAuthenticationError) as e:
        local_logger.warning(f"Could not fetch details for PG {pg_id} to get name: {e}")
        return f"Unknown PG ({pg_id})"
    except Exception as e:
        local_logger.error(f"Unexpected error fetching name for PG {pg_id}: {e}", exc_info=True)
        return f"Error PG ({pg_id})"

async def _get_process_group_contents_counts(pg_id: str) -> Dict[str, int]:
    """Fetches counts of components within a specific process group."""
    # Get client, logger, and IDs from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    
    if not nifi_client:
        local_logger.error("NiFi client not found in context for _get_process_group_contents_counts")
        return {"processors": -1, "connections": -1, "ports": -1, "process_groups": -1}

    counts = {"processors": 0, "connections": 0, "ports": 0, "process_groups": 0}
    # Extract context IDs from logger for the client calls
    # context = local_logger._context # REMOVED
    # user_request_id = context.get("user_request_id", "-") # REMOVED
    # action_id = context.get("action_id", "-") # REMOVED
    try:
        # Attempt to use the more efficient /flow endpoint first
        nifi_req = {"operation": "get_process_group_flow", "process_group_id": pg_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_req).debug("Calling NiFi API (for counts)")
        pg_flow_details = await nifi_client.get_process_group_flow(pg_id) # Flow endpoint doesn't take context IDs
        nifi_resp = {"has_flow_details": bool(pg_flow_details and 'processGroupFlow' in pg_flow_details)}
        local_logger.bind(interface="nifi", direction="response", data=nifi_resp).debug("Received from NiFi API (for counts)")
        
        if pg_flow_details and 'processGroupFlow' in pg_flow_details:
            flow_content = pg_flow_details['processGroupFlow'].get('flow', {})
            counts["processors"] = len(flow_content.get('processors', []))
            counts["connections"] = len(flow_content.get('connections', []))
            counts["ports"] = len(flow_content.get('inputPorts', [])) + len(flow_content.get('outputPorts', []))
            counts["process_groups"] = len(flow_content.get('processGroups', []))
            local_logger.debug(f"Got counts for PG {pg_id} via /flow endpoint: {counts}")
            return counts
        else:
             local_logger.warning(f"Could not get counts via /flow for PG {pg_id}, falling back to individual calls.")
             # Pass IDs explicitly to client methods that need them
             processors = await nifi_client.list_processors(pg_id, user_request_id=user_request_id, action_id=action_id)
             connections = await nifi_client.list_connections(pg_id, user_request_id=user_request_id, action_id=action_id)
             input_ports = await nifi_client.get_input_ports(pg_id) # Doesn't take context IDs
             output_ports = await nifi_client.get_output_ports(pg_id) # Doesn't take context IDs
             process_groups = await nifi_client.get_process_groups(pg_id) # Doesn't take context IDs
             counts["processors"] = len(processors) if processors else 0
             counts["connections"] = len(connections) if connections else 0
             counts["ports"] = (len(input_ports) if input_ports else 0) + (len(output_ports) if output_ports else 0)
             counts["process_groups"] = len(process_groups) if process_groups else 0
             local_logger.debug(f"Got counts for PG {pg_id} via individual calls: {counts}")
             return counts
             
    except (ConnectionError, ValueError, NiFiAuthenticationError) as e:
        local_logger.error(f"Error fetching counts for PG {pg_id}: {e}")
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API (for counts)")
        return counts
    except Exception as e:
         local_logger.error(f"Unexpected error fetching counts for PG {pg_id}: {e}", exc_info=True)
         local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received unexpected error from NiFi API (for counts)")
         return counts

async def _list_components_recursively(
    object_type: Literal["processors", "connections", "ports"],
    pg_id: str,
    depth: int = 0,
    max_depth: int = 3
) -> List[Dict]:
    """Recursively lists processors, connections, or ports within a process group hierarchy."""
    # Get client, logger, and IDs from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"

    if not nifi_client:
        local_logger.error("NiFi client not found in context for _list_components_recursively")
        return [{
             "process_group_id": pg_id,
             "process_group_name": "Unknown (Client Error)",
             "error": f"NiFi Client not available"
        }]

    all_results = [] 
    current_pg_name = await _get_process_group_name(pg_id)
    
    current_level_objects = []
    try:
        if object_type == "processors":
            raw_objects = await nifi_client.list_processors(pg_id, user_request_id=user_request_id, action_id=action_id)
            current_level_objects = _format_processor_summary(raw_objects)
        elif object_type == "connections":
            raw_objects = await nifi_client.list_connections(pg_id, user_request_id=user_request_id, action_id=action_id)
            current_level_objects = _format_connection_summary(raw_objects)
        elif object_type == "ports":
            input_ports = await nifi_client.get_input_ports(pg_id)
            output_ports = await nifi_client.get_output_ports(pg_id)
            current_level_objects = _format_port_summary(input_ports, output_ports)
            
        if current_level_objects:
            all_results.append({
                "process_group_id": pg_id,
                "process_group_name": current_pg_name,
                "objects": current_level_objects
            })
            
    except (ConnectionError, ValueError, NiFiAuthenticationError) as e:
        local_logger.error(f"Error fetching {object_type} for PG {pg_id} during recursion: {e}")
        all_results.append({
             "process_group_id": pg_id,
             "process_group_name": current_pg_name,
             "error": f"Failed to retrieve {object_type}: {e}"
        })
    except Exception as e:
        local_logger.error(f"Unexpected error fetching {object_type} for PG {pg_id} during recursion: {e}", exc_info=True)
        all_results.append({
             "process_group_id": pg_id,
             "process_group_name": current_pg_name,
             "error": f"Unexpected error retrieving {object_type}: {e}"
        })

    # Check if max depth is reached before fetching child groups
    if depth >= max_depth:
        local_logger.debug(f"Max recursion depth ({max_depth}) reached for PG {pg_id}. Stopping recursion.")
        return all_results

    try:
        child_groups = await nifi_client.get_process_groups(pg_id) # Doesn't take context IDs
        if child_groups:
            for child_group_entity in child_groups:
                child_id = child_group_entity.get('id')
                if child_id:
                    # Call recursively without passing client/logger
                    recursive_results = await _list_components_recursively(
                        object_type=object_type,
                        pg_id=child_id,
                        depth=depth + 1,  # Increment depth
                        max_depth=max_depth # Pass max_depth down
                    )
                    all_results.extend(recursive_results)
                    
    except (ConnectionError, ValueError, NiFiAuthenticationError) as e:
        local_logger.error(f"Error fetching child groups for PG {pg_id} during recursion: {e}")
        all_results.append({
             "process_group_id": pg_id,
             "process_group_name": current_pg_name,
             "error_fetching_children": f"Failed to retrieve child groups: {e}"
        })
    except Exception as e:
        local_logger.error(f"Unexpected error fetching child groups for PG {pg_id}: {e}", exc_info=True)
        all_results.append({
             "process_group_id": pg_id,
             "process_group_name": current_pg_name,
             "error_fetching_children": f"Unexpected error retrieving child groups: {e}"
        })
        
    return all_results

async def _get_process_group_hierarchy(
    pg_id: str, 
    recursive_search: bool
) -> Dict[str, Any]:
    """Fetches the hierarchy starting from pg_id, optionally recursively."""
    # Get client, logger, and IDs from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"

    if not nifi_client:
        local_logger.error("NiFi client not found in context for _get_process_group_hierarchy")
        return { "id": pg_id, "name": "Unknown (Client Error)", "child_process_groups": [], "error": "NiFi Client not available"}

    hierarchy_data = { "id": pg_id, "name": "Unknown", "child_process_groups": [] }
    # Extract context IDs from logger for the client calls - REMOVED
    # context = local_logger._context
    # user_request_id = context.get("user_request_id", "-")
    # action_id = context.get("action_id", "-")
    try:
        parent_name = await _get_process_group_name(pg_id) # Calls helper which now uses context
        hierarchy_data["name"] = parent_name

        nifi_req_children = {"operation": "get_process_groups", "process_group_id": pg_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_req_children).debug("Calling NiFi API")
        child_groups_response = await nifi_client.get_process_groups(pg_id)
        child_count = len(child_groups_response) if child_groups_response else 0
        nifi_resp_children = {"child_group_count": child_count}
        local_logger.bind(interface="nifi", direction="response", data=nifi_resp_children).debug("Received from NiFi API")
        child_groups_list = child_groups_response

        if child_groups_list:
            for child_group_entity in child_groups_list:
                child_id = child_group_entity.get('id')
                child_component = child_group_entity.get('component', {})
                child_name = child_component.get('name', f"Unnamed PG ({child_id})")

                if child_id:
                    counts = await _get_process_group_contents_counts(child_id) # Calls helper which now uses context
                    child_data = {
                        "id": child_id,
                        "name": child_name,
                        "counts": counts
                    }
                    
                    if recursive_search:
                        local_logger.debug(f"Recursively fetching hierarchy for child PG: {child_id}")
                        # Call recursively without passing client/logger
                        child_hierarchy = await _get_process_group_hierarchy(
                            pg_id=child_id, 
                            recursive_search=True
                        )
                        child_data["children"] = child_hierarchy.get("child_process_groups", [])
                    
                    hierarchy_data["child_process_groups"].append(child_data)

        return hierarchy_data

    except (ConnectionError, ValueError, NiFiAuthenticationError) as e:
        local_logger.error(f"Error fetching process group hierarchy for {pg_id}: {e}")
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        hierarchy_data["error"] = f"Failed to retrieve full hierarchy for process group {pg_id}: {e}"
        return hierarchy_data
    except Exception as e:
         local_logger.error(f"Unexpected error fetching hierarchy for {pg_id}: {e}", exc_info=True)
         local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received unexpected error from NiFi API")
         hierarchy_data["error"] = f"Unexpected error retrieving hierarchy for {pg_id}: {e}"
         return hierarchy_data

# --- Tool Definitions --- 

@mcp.tool()
@tool_phases(["Review", "Build", "Modify", "Operate"])
async def list_nifi_objects(
    object_type: Literal["processors", "connections", "ports", "process_groups"],
    process_group_id: str | None = None,
    search_scope: Literal["current_group", "recursive"] = "current_group",
    # mcp_context: dict = {} # Removed context parameter
) -> Union[List[Dict], Dict]:
    """
    Lists NiFi objects or provides a hierarchy view for process groups within a specified scope.

    Parameters
    ----------
    object_type : Literal["processors", "connections", "ports", "process_groups"]
        The type of NiFi objects to list.
        - 'processors': Lists processors with basic details and status.
        - 'connections': Lists connections with basic details and status.
        - 'ports': Lists input and output ports with basic details and status.
        - 'process_groups': Lists child process groups under the target group (see search_scope).
    process_group_id : str | None, optional
        The ID of the target process group. If None, defaults to the root process group.
    search_scope : Literal["current_group", "recursive"], optional
        Determines the scope of the search when listing objects.
        - 'current_group': Lists objects only directly within the target process group (default).
        - 'recursive': Lists objects within the target process group and all its descendants.
        Note: For 'process_groups' object_type, 'recursive' provides a nested hierarchy view.
    # Removed mcp_context from docstring

    Returns
    -------
    Union[List[Dict], Dict]
        - For object_type 'processors', 'connections', 'ports':
            - If search_scope='current_group': A list of simplified object summaries.
            - If search_scope='recursive': A list of dictionaries, each containing 'process_group_id', 'process_group_name', and a list of 'objects' found within that group (or an 'error' key).
        - For object_type 'process_groups':
            - If search_scope='current_group': A list of child process group summaries (id, name, counts).
            - If search_scope='recursive': A nested dictionary representing the process group hierarchy including names, IDs, component counts, and children.
    """
    # Get client and logger from context variables
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger # Fallback to global logger if needed

    if not nifi_client:
        raise ToolError("NiFi client not found in context.")
    if not isinstance(nifi_client, NiFiClient):
         raise ToolError(f"Invalid NiFi client type found in context: {type(nifi_client)}")

    # await ensure_authenticated(nifi_client, local_logger) # Removed - handled by factory
    
    # --- Get IDs from context --- 
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    # --------------------------

    try:
        session_pg_id = current_process_group.get() or None
        target_pg_id = process_group_id
        if not target_pg_id:
            target_pg_id = session_pg_id
            if not target_pg_id:
                local_logger.info("process_group_id not provided, defaulting to root.")
                target_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
            local_logger.info(f"Resolved root process group ID: {target_pg_id}")

        local_logger.info(f"Listing NiFi objects of type '{object_type}' in scope '{search_scope}' for PG '{target_pg_id}'")
        if not await nifi_client.is_descendant(target_pg_id, session_pg_id):
            raise ToolError(f"Target process group {target_pg_id} is not a descendant of the current session process group {session_pg_id}.")
        # --- Process Group Handling --- 
        if object_type == "process_groups":
            local_logger.debug("Handling object_type 'process_groups'...")
            if search_scope == "current_group":
                local_logger.debug(f"Fetching direct children for PG {target_pg_id}")
                child_groups_response = await nifi_client.get_process_groups(target_pg_id)
                results = []
                if child_groups_response:
                    for child_group_entity in child_groups_response:
                        child_id = child_group_entity.get('id')
                        child_component = child_group_entity.get('component', {})
                        child_name = child_component.get('name', f"Unnamed PG ({child_id})")
                        if child_id:
                            counts = await _get_process_group_contents_counts(child_id)
                            results.append({"id": child_id, "name": child_name, "counts": counts})
                local_logger.info(f"Found {len(results)} direct child process groups in PG {target_pg_id}")
                return results
            else: # recursive
                local_logger.debug(f"Recursively fetching hierarchy starting from PG {target_pg_id}")
                hierarchy = await _get_process_group_hierarchy(target_pg_id, True)
                local_logger.info(f"Finished fetching recursive hierarchy for PG {target_pg_id}")
                return hierarchy

        # --- Processor, Connection, Port Handling --- 
        else:
            local_logger.debug(f"Handling object_type '{object_type}'...")
            if search_scope == "current_group":
                local_logger.debug(f"Fetching objects directly within PG {target_pg_id}")
                objects = []
                if object_type == "processors":
                    raw_objects = await nifi_client.list_processors(target_pg_id, user_request_id=user_request_id, action_id=action_id)
                    objects = _format_processor_summary(raw_objects)
                elif object_type == "connections":
                    raw_objects = await nifi_client.list_connections(target_pg_id, user_request_id=user_request_id, action_id=action_id)
                    objects = _format_connection_summary(raw_objects)
                elif object_type == "ports":
                    input_ports = await nifi_client.get_input_ports(target_pg_id)
                    output_ports = await nifi_client.get_output_ports(target_pg_id)
                    objects = _format_port_summary(input_ports, output_ports)
                    
                local_logger.info(f"Found {len(objects)} {object_type} directly within PG {target_pg_id}")
                return objects
            else: # recursive
                local_logger.debug(f"Recursively fetching {object_type} starting from PG {target_pg_id}")
                recursive_results = await _list_components_recursively(
                    object_type=object_type,
                    pg_id=target_pg_id,
                    max_depth=10 # Set a reasonable max depth
                )
                local_logger.info(f"Finished recursive search for {object_type} starting from PG {target_pg_id}")
                return recursive_results

    except NiFiAuthenticationError as e:
         local_logger.error(f"Authentication error during list_nifi_objects: {e}", exc_info=False)
         raise ToolError(f"Authentication error accessing NiFi: {e}") from e
    except (ValueError, ConnectionError, ToolError) as e:
        local_logger.error(f"Error listing NiFi objects: {e}", exc_info=False)
        raise ToolError(f"Error listing NiFi {object_type}: {e}") from e
    except Exception as e:
        local_logger.error(f"Unexpected error listing NiFi objects: {e}", exc_info=True)
        raise ToolError(f"An unexpected error occurred: {e}") from e

@mcp.tool()
@tool_phases(["Review", "Build", "Modify", "Operate"])
async def get_nifi_object_details(
    object_type: Literal["processor", "connection", "port", "process_group"],
    object_id: str,
    # mcp_context: dict = {} # Removed context parameter
) -> Dict:
    """
    Retrieves detailed information for a specific NiFi processor, connection, port, or process group.

    Parameters
    ----------
    object_type : Literal["processor", "connection", "port", "process_group"]
        The type of NiFi object to retrieve details for.
    object_id : str
        The ID of the specific NiFi object.
    # Removed mcp_context from docstring

    Returns
    -------
    Dict
        A dictionary containing the detailed entity information for the specified object, including component details, configuration, status, and revision.
    """
    # Get client and logger from context variables
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger

    if not nifi_client:
        raise ToolError("NiFi client not found in context.")
    if not isinstance(nifi_client, NiFiClient):
         raise ToolError(f"Invalid NiFi client type found in context: {type(nifi_client)}")
         
    # await ensure_authenticated(nifi_client, local_logger) # Removed
    
    # --- Get IDs from context --- 
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    # --------------------------

    local_logger.info(f"Getting details for NiFi object type '{object_type}' with ID '{object_id}'")
    nifi_req = {"operation": f"get_{object_type}_details", "id": object_id}
    local_logger.bind(interface="nifi", direction="request", data=nifi_req).debug("Calling NiFi API")
    session_pg_id = current_process_group.get() or None
    try:
        details = {}
        if object_type == "processor":
            details = await nifi_client.get_processor_details(object_id)
        elif object_type == "connection":
            details = await nifi_client.get_connection(object_id)
        elif object_type == "process_group":
            # Use the method that passes context IDs
            details = await nifi_client.get_process_group_details(
                object_id, user_request_id=user_request_id, action_id=action_id
            )
        elif object_type == "port":
            # Need to determine if input or output port. Try input first.
            try:
                details = await nifi_client.get_input_port_details(object_id)
                local_logger.debug(f"Object {object_id} identified as an input port.")
            except ValueError:
                local_logger.debug(f"Object {object_id} not found as input port, trying output port.")
                try:
                    details = await nifi_client.get_output_port_details(object_id)
                    local_logger.debug(f"Object {object_id} identified as an output port.")
                except ValueError as e_out:
                    local_logger.error(f"Could not find port with ID '{object_id}' as either input or output port.")
                    raise ToolError(f"Port with ID '{object_id}' not found.") from e_out
        else:
            # Should not happen due to Literal validation, but good practice
            raise ToolError(f"Invalid object_type specified: {object_type}")
        if session_pg_id:
            if object_type == "process_group":
                # Check if the process group is a descendant of the session process group
                if not await nifi_client.is_descendant(object_id, session_pg_id):
                    raise ToolError(f"Process group {object_id} is not a descendant of the current session process group {session_pg_id}.")
            else:
                # Check if the object is a descendant of the session process group
                if not await nifi_client.is_descendant(details.get("component", {}).get("parentGroupId"), session_pg_id):
                    raise ToolError(f"{object_type.capitalize()} {object_id} is not a descendant of the current session process group {session_pg_id}.")
        local_logger.bind(interface="nifi", direction="response", data={
            "object_id": object_id, 
            "object_type": object_type, 
            "has_details": bool(details)
            }).debug("Received from NiFi API")
        local_logger.info(f"Successfully retrieved details for {object_type} {object_id}")
        return details

    except NiFiAuthenticationError as e:
         local_logger.error(f"Authentication error getting details for {object_type} {object_id}: {e}", exc_info=False)
         raise ToolError(f"Authentication error accessing NiFi: {e}") from e
    except ValueError as e:
        # Catch not found errors specifically
        local_logger.warning(f"Could not find {object_type} with ID '{object_id}': {e}")
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        raise ToolError(f"{object_type.capitalize()} with ID '{object_id}' not found.") from e
    except (ConnectionError, ToolError) as e:
        local_logger.error(f"Error getting details for {object_type} {object_id}: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        raise ToolError(f"Error getting details for {object_type} {object_id}: {e}") from e
    except Exception as e:
        local_logger.error(f"Unexpected error getting details for {object_type} {object_id}: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received unexpected error from NiFi API")
        raise ToolError(f"An unexpected error occurred: {e}") from e

@mcp.tool()
@tool_phases(["Review", "Build", "Modify", "Operate"])
async def document_nifi_flow(
    process_group_id: str | None = None,
    starting_processor_id: str | None = None,
    max_depth: int = 10,
    include_properties: bool = True,
    include_descriptions: bool = True,
    # mcp_context: dict = {} # Removed context parameter
) -> Dict[str, Any]:
    """
    Analyzes and documents a NiFi flow starting from a given process group or processor.

    This tool traverses the flow graph, extracts key information about processors and connections,
    identifies decision points, and generates a structured representation of the flow logic.

    Parameters
    ----------
    process_group_id : str, optional
        The ID of the process group to start documentation from. If None, `starting_processor_id` must be provided, and the tool will start from that processor's parent group.
    starting_processor_id : str, optional
        The ID of a specific processor to focus the documentation around. The tool will analyze the flow connected to this processor within its parent group.
    max_depth : int, optional
        The maximum depth to traverse the flow graph from the starting point. Defaults to 10.
    include_properties : bool, optional
        Whether to include important processor properties in the documentation. Defaults to True.
    include_descriptions : bool, optional
        Whether to include processor and connection descriptions/comments (if available). Defaults to True.
    # Removed mcp_context from docstring

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the documented flow, including:
        - 'start_point': Information about the starting process group or processor.
        - 'flow_structure': A list representing the main flow path(s).
        - 'decision_branches': Information about identified decision branches (e.g., RouteOnAttribute).
        - 'unconnected_components': Lists of processors or ports not connected in the main flow.
        - 'errors': Any errors encountered during documentation.
    """
    # Get client and logger from context variables
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger

    if not nifi_client:
        raise ToolError("NiFi client not found in context.")
    if not isinstance(nifi_client, NiFiClient):
         raise ToolError(f"Invalid NiFi client type found in context: {type(nifi_client)}")
         
    # await ensure_authenticated(nifi_client, local_logger) # Removed
    
    # --- Get IDs from context --- 
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    # --------------------------
    
    local_logger.info(f"Starting NiFi flow documentation. PG: {process_group_id}, Start Proc: {starting_processor_id}, Max Depth: {max_depth}")
    results = {
        "start_point": None,
        "flow_structure": [],
        "decision_branches": [],
        "unconnected_components": {"processors": [], "ports": []},
        "errors": []
    }
    session_pg_id = current_process_group.get()
    target_pg_id = process_group_id
    
    try:
        # Determine the target process group ID
        if starting_processor_id and not target_pg_id:
            local_logger.info(f"No process_group_id provided, finding parent group for starting processor {starting_processor_id}")
            nifi_req = {"operation": "get_processor_details", "id": starting_processor_id}
            local_logger.bind(interface="nifi", direction="request", data=nifi_req).debug("Calling NiFi API")
            proc_details = await nifi_client.get_processor_details(starting_processor_id)
            nifi_resp = {"has_proc_details": bool(proc_details and 'component' in proc_details)}
            local_logger.bind(interface="nifi", direction="response", data=nifi_resp).debug("Received from NiFi API")
            
            target_pg_id = proc_details.get("component", {}).get("parentGroupId")
            if not target_pg_id:
                raise ToolError(f"Could not determine parent process group ID for processor {starting_processor_id}")
            results["start_point"] = {"type": "processor", "id": starting_processor_id, "name": proc_details.get("component", {}).get("name"), "process_group_id": target_pg_id}
            local_logger.info(f"Determined target process group ID: {target_pg_id} from starting processor.")
        elif not target_pg_id:
            local_logger.info("No process_group_id or starting_processor_id provided, defaulting to root process group.")
            target_pg_id = session_pg_id
            if not target_pg_id:
                target_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
            if not target_pg_id:
                 raise ToolError("Could not retrieve the root process group ID.")
            results["start_point"] = {"type": "process_group", "id": target_pg_id, "name": "Root"}
            local_logger.info(f"Resolved root process group ID: {target_pg_id}")
        else:
            # PG ID was provided, get its name for the start point
            if not await nifi_client.is_descendant(target_pg_id, session_pg_id):
                raise ToolError(f"Target process group {target_pg_id} is not a descendant of the current session process group {session_pg_id}.")
            pg_name = await _get_process_group_name(target_pg_id)
            results["start_point"] = {"type": "process_group", "id": target_pg_id, "name": pg_name}
            local_logger.info(f"Using provided process group ID: {target_pg_id} ({pg_name})")
            
        if not target_pg_id:
             raise ToolError("Failed to determine a target process group ID for documentation.")

        # Fetch components for the target process group
        local_logger.info(f"Fetching components for process group {target_pg_id}...")
        nifi_req_components = {"operation": "list_all", "process_group_id": target_pg_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_req_components).debug("Calling NiFi API (multiple calls)")
        
        processors_resp = await nifi_client.list_processors(target_pg_id, user_request_id=user_request_id, action_id=action_id)
        connections_resp = await nifi_client.list_connections(target_pg_id, user_request_id=user_request_id, action_id=action_id)
        input_ports_resp = await nifi_client.get_input_ports(target_pg_id)
        output_ports_resp = await nifi_client.get_output_ports(target_pg_id)
        
        nifi_resp_components = {
            "processor_count": len(processors_resp or []),
            "connection_count": len(connections_resp or []),
            "port_count": len(input_ports_resp or []) + len(output_ports_resp or [])
        }
        local_logger.bind(interface="nifi", direction="response", data=nifi_resp_components).debug("Received from NiFi API (multiple calls)")

        processors = {p['id']: p for p in processors_resp if 'id' in p}
        connections = {c['id']: c for c in connections_resp if 'id' in c}
        input_ports = {p['id']: p for p in input_ports_resp if 'id' in p}
        output_ports = {p['id']: p for p in output_ports_resp if 'id' in p}
        all_components = {**processors, **input_ports, **output_ports}

        # Build the graph structure (new return format)
        local_logger.info("Building graph structure from fetched components...")
        graph_data = build_graph_structure(list(processors.values()), list(connections.values())) # Pass lists
        outgoing_graph = graph_data.get("outgoing", {}) # Use the 'outgoing' part
        incoming_graph = graph_data.get("incoming", {}) # Keep if needed

        # Manually create nodes_by_id map for easy lookup
        nodes_by_id = {}
        for comp_id, comp_details in all_components.items():
            comp_type = comp_details.get('component', {}).get('type', 'UNKNOWN')
            # Map NiFi types to documentation types if needed
            comp_type_lower = comp_type.lower() # Convert to lowercase for case-insensitive check
            doc_type = "UNKNOWN"
            if "processor" in comp_type_lower:
                doc_type = "PROCESSOR"
            elif "input_port" in comp_type_lower:
                doc_type = "INPUT_PORT"
            elif "output_port" in comp_type_lower:
                doc_type = "OUTPUT_PORT"
                
            nodes_by_id[comp_id] = {
                "name": comp_details.get('component', {}).get('name', 'Unknown'),
                "type": doc_type # Use mapped type
            }
        
        # --- Debugging Graph and Source Node Logic ---
        local_logger.debug(f"Nodes identified (nodes_by_id keys): {list(nodes_by_id.keys())}")
        local_logger.debug(f"Incoming graph keys (nodes with inputs): {list(incoming_graph.keys())}")

        # Check Generate Flow File node specifically
        gen_flow_file_id = '2ca23583-0196-1000-8dfe-fdf4f50b40d8' # Hardcode ID from image/logs
        if gen_flow_file_id in nodes_by_id:
             gen_node_info = nodes_by_id[gen_flow_file_id]
             gen_node_type = gen_node_info['type']
             is_processor = gen_node_type == 'PROCESSOR'
             not_in_incoming = gen_flow_file_id not in incoming_graph
             local_logger.debug(f"Check for {gen_flow_file_id}: Type is '{gen_node_type}'. Is 'PROCESSOR'? {is_processor}. Not in incoming keys? {not_in_incoming}")
        else:
             local_logger.warning(f"Generate Flow File ID {gen_flow_file_id} not found in nodes_by_id!")

        _potential_source_nodes = [nid for nid, node in nodes_by_id.items()
                                   if node['type'] == 'INPUT_PORT' or 
                                   (node['type'] == 'PROCESSOR' and nid not in incoming_graph)]
        local_logger.debug(f"Calculated potential source nodes: {_potential_source_nodes}")
        # --- End Debugging ---

        # Analyze and document the flow
        local_logger.info("Analyzing flow structure...")
        start_node_id = starting_processor_id # Use provided start if available
        
        # If no specific processor start, try to find source nodes (input ports or processors with no incoming connections)
        if not start_node_id:
            # Use the PREVIOUSLY calculated source nodes from the debug step
            if _potential_source_nodes:
                start_node_id = _potential_source_nodes[0] # Pick the first source node found
                local_logger.info(f"No starting_processor_id given, starting analysis from calculated source node: {start_node_id}")
            else:
                # Fallback if no clear source, maybe pick first processor?
                if processors:
                    start_node_id = list(processors.keys())[0]
                    local_logger.warning(f"No source nodes identified, starting analysis from arbitrary processor: {start_node_id}")
                else:
                    raise ToolError("Cannot document flow: No starting point specified and no processors found in the group.")
        else:
             local_logger.info(f"Using provided starting processor ID: {start_node_id}")

        if not start_node_id: # Final safety check before traversal
             raise ToolError("Could not determine a valid starting node ID for traversal.")
                    
        traversed_path = []
        visited_nodes = set()
        queue = [(start_node_id, 0)] # (node_id, current_depth)
        unconnected_processors = set(processors.keys())
        unconnected_ports = set(input_ports.keys()) | set(output_ports.keys())

        local_logger.debug(f"Starting traversal. Initial Queue: {queue}") # Log initial queue

        while queue:
            current_node_id, depth = queue.pop(0)

            local_logger.debug(f"Processing Node: {current_node_id} at depth {depth}. Current Queue: {queue}") # Log current node and queue

            if current_node_id in visited_nodes or depth > max_depth:
                local_logger.debug(f"Skipping Node {current_node_id}: Visited or max depth reached.") # Log skip reason
                continue
            visited_nodes.add(current_node_id)
            local_logger.debug(f"Added Node {current_node_id} to visited set.") # Log visited add

            if current_node_id in unconnected_processors: unconnected_processors.remove(current_node_id)
            if current_node_id in unconnected_ports: unconnected_ports.remove(current_node_id)

            node_info = nodes_by_id.get(current_node_id)
            if not node_info:
                local_logger.warning(f"Node details not found for ID: {current_node_id} in nodes_by_id map.") # Changed log level
                results["errors"].append(f"Node details not found for ID: {current_node_id}")
                continue

            component_details = all_components.get(current_node_id, {})
            component_config = component_details.get('component', {}).get('config', {})
            component_props = component_config.get('properties', {})

            doc_entry = {
                "id": current_node_id,
                "name": node_info["name"],
                "type": node_info["type"],
                "outgoing_connections": [] # Initialize list for outgoing connections
            }
            if include_descriptions:
                doc_entry["description"] = component_details.get("component", {}).get("comments", "") or component_details.get("component", {}).get("name", "")
            if include_properties and node_info["type"] == "PROCESSOR":
                 # Use extract_important_properties which now returns all props + expressions
                 prop_analysis = extract_important_properties(component_details) # Pass full details
                 doc_entry["properties"] = prop_analysis["all_properties"]
                 doc_entry["expressions"] = prop_analysis["expressions"]
                 
            # Relationship info will be added in the loop below
            traversed_path.append(doc_entry)
            local_logger.debug(f"Appended {current_node_id} ({node_info['name']}) to traversed_path.") # Log path append
            
            # Add neighbors to queue
            # Use outgoing_graph now
            if current_node_id in outgoing_graph:
                 # Corrected loop: iterate directly over the list of connection details
                 connection_details_list = outgoing_graph[current_node_id]
                 local_logger.debug(f"Found {len(connection_details_list)} outgoing connections for {current_node_id}.") # Log connection count
                 for connection_detail in connection_details_list: # Iterate list directly
                     neighbor_id = connection_detail.get("destination", {}).get("id")
                     if not neighbor_id:
                         neighbor_id = connection_detail.get("destinationId")
                         
                     if neighbor_id:
                         local_logger.debug(f"  Checking neighbor: {neighbor_id} via connection {connection_detail.get('id')}") # Log neighbor check
                         # Format connection info
                         formatted_conn = format_connection(connection_detail, all_components) # Pass all_components for name lookup
                         # Append connection info to the CURRENT node's entry in traversed_path
                         # Since doc_entry was just appended, it's the last item
                         if traversed_path:
                              traversed_path[-1]["outgoing_connections"].append(formatted_conn)
                          
                         if neighbor_id not in visited_nodes:
                             queue.append((neighbor_id, depth + 1))
                             local_logger.debug(f"    Added neighbor {neighbor_id} to queue.") # Log queue add
                         else:
                              local_logger.debug(f"    Neighbor {neighbor_id} already visited.") # Log neighbor visited
                     else:
                         local_logger.warning(f"  Could not find destination ID in connection detail: {connection_detail}") # Log missing ID
            else:
                 local_logger.debug(f"Node {current_node_id} has no outgoing connections in graph.") # Log no outgoing

        local_logger.debug(f"Traversal loop finished. Final traversed_path: {traversed_path}") # Log final path
        results["flow_structure"] = traversed_path
        results["decision_branches"] = find_decision_branches(all_components, graph_data) # Pass all_components and the raw graph_data
        
        # Populate unconnected
        for proc_id in unconnected_processors:
             proc_info = processors.get(proc_id, {})
             results["unconnected_components"]["processors"].append({
                "id": proc_id,
                "name": proc_info.get('component', {}).get('name', 'Unknown Processor'),
                "type": proc_info.get('component', {}).get('type', 'Unknown Type')
             })
        for port_id in unconnected_ports:
             port_info = all_components.get(port_id, {})
             results["unconnected_components"]["ports"].append({
                "id": port_id,
                "name": port_info.get('component', {}).get('name', 'Unknown Port'),
                "type": port_info.get('component', {}).get('type', 'Unknown Port Type') 
             })
        
        local_logger.info("Flow documentation analysis complete.")
        return results

    except NiFiAuthenticationError as e:
         local_logger.error(f"Authentication error during document_nifi_flow: {e}", exc_info=False)
         results["errors"].append(f"Authentication error accessing NiFi: {e}")
         raise ToolError(f"Authentication error accessing NiFi: {e}") from e # Re-raise as ToolError
    except (ValueError, ConnectionError, ToolError) as e:
        local_logger.error(f"Error documenting NiFi flow: {e}", exc_info=False)
        results["errors"].append(f"Error documenting flow: {e}")
        # Don't re-raise, return partial results with errors
        return results
    except Exception as e:
        local_logger.error(f"Unexpected error documenting NiFi flow: {e}", exc_info=True)
        results["errors"].append(f"An unexpected error occurred: {e}")
        # Don't re-raise, return partial results with errors
        return results

@mcp.tool()
@tool_phases(["Review", "Operate"])
async def search_nifi_flow(
    query: str,
    filter_object_type: Optional[Literal["processor", "connection", "port", "process_group","process_groups"]] = None,
    filter_process_group_id: Optional[str] = None,
    # mcp_context: dict = {} # Removed context parameter
) -> Dict[str, List[Dict]]:
    """
    Performs a search across the entire NiFi flow for components matching the query.

    Optionally filters results by object type and/or containing process group ID.

    Parameters
    ----------
    query : str
        The search term (e.g., processor name, property value, comment text).
    filter_object_type : Optional[Literal["processor", "connection", "port", "process_group"]], optional
        Filter results to only include objects of this type. 'port' includes both input and output ports.
    filter_process_group_id : Optional[str], optional
        Filter results to only include objects within the specified process group (including nested groups).
    # Removed mcp_context from docstring

    Returns
    -------
    Dict[str, List[Dict]]
        A dictionary containing lists of matching objects, keyed by type (e.g., 'processorResults', 'connectionResults').
        Each result includes basic information like id, name, and parent group.
    """
    # Get client and logger from context variables
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    session_pg_id = current_process_group.get()
    if not filter_process_group_id:
        filter_process_group_id = session_pg_id
    if not nifi_client:
        raise ToolError("NiFi client not found in context.")
    if not isinstance(nifi_client, NiFiClient):
         raise ToolError(f"Invalid NiFi client type found in context: {type(nifi_client)}")
         
    # await ensure_authenticated(nifi_client, local_logger) # Removed
    
    local_logger.info(f"Searching NiFi flow with query: '{query}'. Filters: type={filter_object_type}, group={filter_process_group_id}")
    nifi_req = {"operation": "search_flow", "query": query}
    local_logger.bind(interface="nifi", direction="request", data=nifi_req).debug("Calling NiFi API")

    try:
        search_results_data = await nifi_client.search_flow(query)
        raw_results = search_results_data.get("searchResultsDTO", {})
        
        nifi_resp = {"has_results": bool(raw_results)}
        local_logger.bind(interface="nifi", direction="response", data=nifi_resp).debug("Received from NiFi API")

        # --- Filtering Logic --- 
        filtered_results = {}
        object_type_map = {
            "processor": "processorResults",
            "connection": "connectionResults",
            "process_group": "processGroupResults",
            "process_groups": "processGroupResults", # Alias for process_group
            "input_port": "inputPortResults", # Map generic port to specific results
            "output_port": "outputPortResults" # Map generic port to specific results
        }

        # Determine which result keys to process based on filter_object_type
        keys_to_process = []
        if not filter_object_type:
            keys_to_process = list(object_type_map.values())
        elif filter_object_type == "port":
            keys_to_process = [object_type_map["input_port"], object_type_map["output_port"]]
        elif filter_object_type in object_type_map:
            keys_to_process = [object_type_map[filter_object_type]]
            
        if not keys_to_process:
            local_logger.warning(f"Invalid filter_object_type: '{filter_object_type}', returning all types.")
            keys_to_process = list(object_type_map.values()) # Fallback to all if filter is invalid
        
        for result_key in keys_to_process:
            if result_key in raw_results:
                filtered_list = []
                for item in raw_results[result_key]:
                    # Apply process group filter if specified
                    if filter_process_group_id:
                        item_pg_id = item.get("groupId")
                        if item_pg_id != filter_process_group_id:
                            # TODO: Implement recursive check if needed
                            # For now, only direct parent match
                            parent_pg_id=await nifi_client.get_process_group_details(item_pg_id).get('component',{}).get('parentGroupId')
                            if not await nifi_client.is_descendant(filter_process_group_id, parent_pg_id):
                                # Skip this item if it doesn't match the filter
                                local_logger.trace(f"Skipping item {item.get('id')} due to PG filter mismatch (Item PG: {item_pg_id}, Filter PG: {filter_process_group_id})")
                                continue
                            
                    
                    # Add basic info for the summary
                    filtered_list.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "groupId": item.get("groupId"),
                        "matches": item.get("matches", []) # Include matching fields
                    })
                if filtered_list:
                    filtered_results[result_key] = filtered_list
        # ---------------------
        
        local_logger.info(f"Flow search completed. Found results across {len(filtered_results)} types.")
        return filtered_results

    except NiFiAuthenticationError as e:
         local_logger.error(f"Authentication error during search_nifi_flow: {e}", exc_info=False)
         raise ToolError(f"Authentication error accessing NiFi: {e}") from e
    except (ConnectionError, ToolError) as e:
        local_logger.error(f"Error searching NiFi flow: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        raise ToolError(f"Error searching NiFi flow: {e}") from e
    except Exception as e:
        local_logger.error(f"Unexpected error searching NiFi flow: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received unexpected error from NiFi API")
        raise ToolError(f"An unexpected error occurred: {e}") from e

@mcp.tool()
@tool_phases(["Review", "Operate"])
async def get_process_group_status(
    process_group_id: str | None = None,
    include_bulletins: bool = True,
    bulletin_limit: int = 20,
) -> Dict[str, Any]:
    """
    Provides a consolidated status overview of a process group.

    Includes component state summaries, validation issues, connection queue sizes,
    and optionally, recent bulletins for the group.

    Args:
        process_group_id: The ID of the target process group. Defaults to root if None.
        include_bulletins: Whether to fetch and include bulletins specific to this group.
        bulletin_limit: Max number of bulletins to fetch if include_bulletins is True.

    Returns:
        A dictionary summarizing the status as defined in the plan.
    """
    # Get client, logger, and context IDs
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    session_pg_id = current_process_group.get()

    if not nifi_client:
        raise ToolError("NiFi client not found in context.")

    local_logger = local_logger.bind(pg_id_param=process_group_id, include_bulletins=include_bulletins)
    local_logger.info("Getting process group status overview.")

    results = {
        "process_group_id": None,
        "process_group_name": "Unknown",
        "component_summary": {
            "processors": {"total": 0, "running": 0, "stopped": 0, "invalid": 0, "disabled": 0},
            "input_ports": {"total": 0, "running": 0, "stopped": 0, "invalid": 0, "disabled": 0},
            "output_ports": {"total": 0, "running": 0, "stopped": 0, "invalid": 0, "disabled": 0},
        },
        "invalid_components": [],
        "queue_summary": {
             "total_queued_count": 0,
             "total_queued_size_bytes": 0,
             "total_queued_size_human": "0 B",
             "connections_with_data": []
        },
        "bulletins": []
    }

    try:
        # --- Step 0: Resolve PG ID and Name ---
        target_pg_id = process_group_id
        if not target_pg_id:
            local_logger.info("process_group_id not provided, resolving root.")
            target_pg_id = session_pg_id
            if not target_pg_id:
                target_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
                results["process_group_name"] = "Root"
            else:
                # Use the session PG ID as the target
                results["process_group_name"] = await _get_process_group_name(target_pg_id)
            local_logger.info(f"Resolved root process group ID: {target_pg_id}")
            
        else:
            # Use helper to get name, handles errors internally
            results["process_group_name"] = await _get_process_group_name(target_pg_id)
            if not await nifi_client.is_descendant(target_pg_id, session_pg_id):
                raise ToolError(f"Process group {target_pg_id} is not a descendant of the current session process group {session_pg_id}.")
        
        results["process_group_id"] = target_pg_id
        local_logger = local_logger.bind(process_group_id=target_pg_id) # Bind resolved ID

        # --- Step 1: Get Components (Processors, Connections, Ports) ---
        local_logger.info("Fetching components (processors, connections, ports)...")
        # Use asyncio.gather for concurrency
        tasks = {
            "processors": nifi_client.list_processors(target_pg_id, user_request_id=user_request_id, action_id=action_id),
            "connections": nifi_client.list_connections(target_pg_id, user_request_id=user_request_id, action_id=action_id),
            "input_ports": nifi_client.get_input_ports(target_pg_id),
            "output_ports": nifi_client.get_output_ports(target_pg_id)
        }
        # Log the request details (simplified)
        nifi_req = {"operation": "list_components", "process_group_id": target_pg_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_req).debug("Calling NiFi API (multiple component lists)")
        
        component_responses = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        processors_resp, connections_resp, input_ports_resp, output_ports_resp = component_responses
        
        # Log the response details (simplified)
        nifi_resp = {
            "processor_count": len(processors_resp) if isinstance(processors_resp, list) else -1,
            "connection_count": len(connections_resp) if isinstance(connections_resp, list) else -1,
            "input_port_count": len(input_ports_resp) if isinstance(input_ports_resp, list) else -1,
            "output_port_count": len(output_ports_resp) if isinstance(output_ports_resp, list) else -1,
        }
        local_logger.bind(interface="nifi", direction="response", data=nifi_resp).debug("Received from NiFi API (multiple component lists)")

        # Handle potential errors from gather
        if isinstance(processors_resp, Exception): local_logger.error(f"Error listing processors: {processors_resp}"); processors_resp = []
        if isinstance(connections_resp, Exception): local_logger.error(f"Error listing connections: {connections_resp}"); connections_resp = []
        if isinstance(input_ports_resp, Exception): local_logger.error(f"Error listing input ports: {input_ports_resp}"); input_ports_resp = []
        if isinstance(output_ports_resp, Exception): local_logger.error(f"Error listing output ports: {output_ports_resp}"); output_ports_resp = []
        
        # --- Step 2: Process Components for Status and Validation ---
        local_logger.info("Processing component statuses...")
        comp_summary = results["component_summary"]
        invalid_list = results["invalid_components"]

        for proc in processors_resp:
            comp = proc.get("component", {})
            state = comp.get("state", "UNKNOWN").lower()
            comp_summary["processors"]["total"] += 1
            if state in comp_summary["processors"]: comp_summary["processors"][state] += 1
            # --- Updated Condition ---
            validation_status = comp.get("validationStatus", "UNKNOWN") # Get the status
            if validation_status == "INVALID": # Check specifically for INVALID
                invalid_list.append({
                    "id": proc.get("id"),
                    "name": comp.get("name"),
                    "type": "processor",
                    "validation_status": validation_status, # Include the status
                    "validation_errors": comp.get("validationErrors", [])
                })

        for port in input_ports_resp:
            comp = port.get("component", {})
            state = comp.get("state", "UNKNOWN").lower()
            comp_summary["input_ports"]["total"] += 1
            if state in comp_summary["input_ports"]: comp_summary["input_ports"][state] += 1
            # --- Updated Condition ---
            validation_status = comp.get("validationStatus", "UNKNOWN") # Get the status
            if validation_status == "INVALID": # Check specifically for INVALID
                invalid_list.append({
                    "id": port.get("id"),
                    "name": comp.get("name"),
                    "type": "input_port",
                    "validation_status": validation_status, # Include the status
                    "validation_errors": comp.get("validationErrors", [])
                })

        for port in output_ports_resp:
            comp = port.get("component", {})
            state = comp.get("state", "UNKNOWN").lower()
            comp_summary["output_ports"]["total"] += 1
            if state in comp_summary["output_ports"]: comp_summary["output_ports"][state] += 1
            # --- Updated Condition ---
            validation_status = comp.get("validationStatus", "UNKNOWN") # Get the status
            if validation_status == "INVALID": # Check specifically for INVALID
                invalid_list.append({
                    "id": port.get("id"),
                    "name": comp.get("name"),
                    "type": "output_port",
                    "validation_status": validation_status, # Include the status
                    "validation_errors": comp.get("validationErrors", [])
                })

        # --- Step 3: Get Queue Status for Connections --- 
        local_logger.info("Fetching connection queue statuses via process group snapshot...")
        queue_summary = results["queue_summary"]
        # Clear previous connection-specific details needed for old method
        # connection_status_tasks = []
        # connection_ids = [conn.get("id") for conn in connections_resp if conn.get("id")]
        # connection_details_map = {conn.get("id"): filter_connection_data(conn) for conn in connections_resp}
        
        # Fetch the single status snapshot for the entire group
        nifi_req_q = {"operation": "get_process_group_status_snapshot", "process_group_id": target_pg_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_req_q).debug("Calling NiFi API")
        group_status_snapshot = {}
        try:
            group_status_snapshot = await nifi_client.get_process_group_status_snapshot(target_pg_id)
            nifi_resp_q = {"has_snapshot": bool(group_status_snapshot)}
            local_logger.bind(interface="nifi", direction="response", data=nifi_resp_q).debug("Received from NiFi API")
        except (ConnectionError, ValueError, NiFiAuthenticationError) as status_err:
             local_logger.error(f"Failed to get process group status snapshot for queue summary: {status_err}")
             # Log error but continue, queue summary will be empty/zero
             nifi_resp_q = {"error": str(status_err)}
             local_logger.bind(interface="nifi", direction="response", data=nifi_resp_q).debug("Received error from NiFi API")
             # Explicitly set snapshot to empty dict to avoid errors below
             group_status_snapshot = {}
        except Exception as status_exc:
             local_logger.error(f"Unexpected error getting process group status snapshot: {status_exc}", exc_info=True)
             nifi_resp_q = {"error": str(status_exc)}
             local_logger.bind(interface="nifi", direction="response", data=nifi_resp_q).debug("Received unexpected error from NiFi API")
             # Explicitly set snapshot to empty dict to avoid errors below
             group_status_snapshot = {}

        # Process the snapshots from the single response
        connection_snapshots = group_status_snapshot.get("aggregateSnapshot", {}).get("connectionStatusSnapshots", [])
        local_logger.debug(f"Processing {len(connection_snapshots)} connection snapshots from group status.")

        # We need connection details (like name) to enrich the summary.
        # Reuse connections_resp obtained in Step 1
        connections_map = {conn.get("id"): conn for conn in connections_resp if conn.get("id")}

        for snapshot_entity in connection_snapshots:
            # Extract the actual snapshot data
            snapshot_data = snapshot_entity.get("connectionStatusSnapshot")
            if not snapshot_data:
                local_logger.warning(f"Skipping connection snapshot due to missing data: {snapshot_entity}")
                continue
                
            conn_id = snapshot_data.get("id")
            if not conn_id:
                 local_logger.warning(f"Skipping connection snapshot due to missing ID: {snapshot_data}")
                 continue
                 
            queued_count = int(snapshot_data.get("flowFilesQueued", 0))
            queued_bytes = int(snapshot_data.get("bytesQueued", 0))
            
            # Get connection details from the map populated earlier
            conn_info = connections_map.get(conn_id, {})
            conn_component = conn_info.get("component", {})
            conn_name = conn_component.get("name", "")
            source_name = conn_component.get("source", {}).get("name", "Unknown Source")
            dest_name = conn_component.get("destination", {}).get("name", "Unknown Destination")

            if queued_count > 0:
                queue_summary["total_queued_count"] += queued_count
                queue_summary["total_queued_size_bytes"] += queued_bytes
                queue_summary["connections_with_data"].append({
                    "id": conn_id,
                    "name": conn_name,
                    "sourceName": source_name,
                    "destName": dest_name,
                    "queued_count": queued_count,
                    "queued_size_bytes": queued_bytes,
                    "queued_size_human": snapshot_data.get("queuedSize", "0 B") # Use pre-formatted string
                })
                
        # Format total size (logic remains the same)
        total_bytes = queue_summary["total_queued_size_bytes"]
        if total_bytes < 1024:
            queue_summary["total_queued_size_human"] = f"{total_bytes} B"
        elif total_bytes < 1024**2:
            queue_summary["total_queued_size_human"] = f"{total_bytes/1024:.1f} KB"
        elif total_bytes < 1024**3:
             queue_summary["total_queued_size_human"] = f"{total_bytes/(1024**2):.1f} MB"
        else:
             queue_summary["total_queued_size_human"] = f"{total_bytes/(1024**3):.1f} GB"

        # --- Step 4: Get Bulletins (if requested) ---
        if include_bulletins:
            local_logger.info(f"Fetching bulletins (limit {bulletin_limit})...")
            try:
                nifi_req_b = {"operation": "get_bulletin_board", "group_id": target_pg_id, "limit": bulletin_limit}
                local_logger.bind(interface="nifi", direction="request", data=nifi_req_b).debug("Calling NiFi API")
                bulletins = await nifi_client.get_bulletin_board(group_id=target_pg_id, limit=bulletin_limit)
                nifi_resp_b = {"bulletin_count": len(bulletins)}
                local_logger.bind(interface="nifi", direction="response", data=nifi_resp_b).debug("Received from NiFi API")
                results["bulletins"] = bulletins
            except Exception as e:
                local_logger.error(f"Failed to fetch bulletins: {e}")
                # Continue without bulletins, maybe add an error marker?
                results["bulletins"] = [{"error": f"Failed to fetch bulletins: {e}"}]
        else:
            local_logger.info("Skipping bulletin fetch as per request.")
            results["bulletins"] = None # Explicitly set to None if not included

        local_logger.info("Process group status overview fetch complete.")
        return results

    except NiFiAuthenticationError as e:
         local_logger.error(f"Authentication error getting status for PG {target_pg_id}: {e}", exc_info=False)
         raise ToolError(f"Authentication error accessing NiFi: {e}") from e
    except (ValueError, ConnectionError, ToolError) as e:
        local_logger.error(f"Error getting status for PG {target_pg_id}: {e}", exc_info=False)
        raise ToolError(f"Error getting status for PG {target_pg_id}: {e}") from e
    except Exception as e:
        local_logger.error(f"Unexpected error getting status for PG {target_pg_id}: {e}", exc_info=True)
        raise ToolError(f"An unexpected error occurred: {e}") from e

@mcp.tool()
@tool_phases(["Review", "Operate"])
async def list_flowfiles(
    target_id: str,
    target_type: Literal["connection", "processor"],
    max_results: int = 100,
    polling_interval: float = 0.5,
    polling_timeout: float = 30.0 # Increased default timeout to 30s
) -> Dict[str, Any]:
    """
    Lists FlowFile summaries from a connection queue or processor provenance.

    For connections, lists FlowFiles currently queued.
    For processors, lists FlowFiles recently processed via provenance events.

    Args:
        target_id: The ID of the connection or processor.
        target_type: Whether the target_id refers to a 'connection' or 'processor'.
        max_results: Maximum number of FlowFile summaries to return.
        polling_interval: Seconds between polling for async request completion (queue/provenance).
        polling_timeout: Maximum seconds to wait for async request completion.

    Returns:
        A dictionary containing the list of FlowFile summaries and metadata.
    """
    # Get client and logger
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set.")

    local_logger = local_logger.bind(target_id=target_id, target_type=target_type, max_results=max_results)
    local_logger.info(f"Listing flowfiles for {target_type} {target_id}")

    results = {
        "target_id": target_id,
        "target_type": target_type,
        "listing_source": "unknown",
        "flowfile_summaries": [],
        "error": None
    }

    try:
        if target_type == "connection":
            results["listing_source"] = "queue"
            local_logger.info("Listing via connection queue...")
            request_id = None
            try:
                # 1. Create request
                nifi_req_create = {"operation": "create_flowfile_listing_request", "connection_id": target_id}
                local_logger.bind(interface="nifi", direction="request", data=nifi_req_create).debug("Calling NiFi API")
                listing_request = await nifi_client.create_flowfile_listing_request(target_id)
                request_id = listing_request.get("id")
                nifi_resp_create = {"request_id": request_id}
                local_logger.bind(interface="nifi", direction="response", data=nifi_resp_create).debug("Received from NiFi API")
                if not request_id:
                    raise ToolError("Failed to get request ID from NiFi for queue listing.")
                local_logger.info(f"Submitted queue listing request: {request_id}")

                # 2. Poll for completion
                start_time = asyncio.get_event_loop().time()
                while True:
                    if (asyncio.get_event_loop().time() - start_time) > polling_timeout:
                        raise TimeoutError(f"Timed out waiting for queue listing request {request_id} to complete.")
                    
                    nifi_req_get = {"operation": "get_flowfile_listing_request", "connection_id": target_id, "request_id": request_id}
                    local_logger.bind(interface="nifi", direction="request", data=nifi_req_get).debug("Calling NiFi API (polling)")
                    request_status = await nifi_client.get_flowfile_listing_request(target_id, request_id)
                    nifi_resp_get = {"finished": request_status.get("finished"), "percentCompleted": request_status.get("percentCompleted")}
                    local_logger.bind(interface="nifi", direction="response", data=nifi_resp_get).debug("Received from NiFi API (polling)")
                    
                    if request_status.get("finished"): 
                        local_logger.info(f"Queue listing request {request_id} finished.")
                        # 3. Extract results (already in the final status response)
                        summaries_raw = request_status.get("flowFileSummaries", [])
                        # Limit results here if necessary, though API might have internal limit
                        results["flowfile_summaries"] = [
                            {
                                "uuid": ff.get("uuid"),
                                "filename": ff.get("filename"),
                                "size": ff.get("size"),
                                "queued_duration": ff.get("queuedDuration"),
                                "attributes": ff.get("attributes", {}), # Queue listing includes attributes
                                "position": ff.get("position")
                            }
                            for ff in summaries_raw[:max_results]
                        ]
                        break
                    await asyncio.sleep(polling_interval)

            finally:
                 # 4. Delete request (always attempt cleanup)
                 if request_id:
                    local_logger.info(f"Cleaning up queue listing request {request_id}...")
                    try:
                        nifi_req_del = {"operation": "delete_flowfile_listing_request", "connection_id": target_id, "request_id": request_id}
                        local_logger.bind(interface="nifi", direction="request", data=nifi_req_del).debug("Calling NiFi API")
                        await nifi_client.delete_flowfile_listing_request(target_id, request_id)
                        local_logger.bind(interface="nifi", direction="response", data={"deleted": True}).debug("Received from NiFi API")
                    except Exception as del_e:
                        local_logger.warning(f"Failed to delete queue listing request {request_id}: {del_e}")
                        # Don't fail the whole operation if cleanup fails

        elif target_type == "processor":
            results["listing_source"] = "provenance"
            local_logger.info("Listing via processor provenance...")
            query_id = None
            try:
                # 1. Submit query
                provenance_payload = {
                    "searchTerms": {"componentId": target_id},
                    # "maxResults": max_results, # Removed - Let client handle default, limit applied after fetch/sort
                    # "summarize": True, # May be useful later?
                    # "sortColumn": "eventTime", # Default is usually time - sorting handled client-side now
                    # "sortOrder": "DESC"     # Default is usually time - sorting handled client-side now
                }
                nifi_req_create = {"operation": "submit_provenance_query", "payload": provenance_payload}
                local_logger.bind(interface="nifi", direction="request", data=nifi_req_create).debug("Calling NiFi API")
                query_response = await nifi_client.submit_provenance_query(provenance_payload)
                # --- Corrected ID extraction ---
                # query_id = query_response.get("query", {}).get("id") # Old incorrect way
                query_id = query_response.get("id") # Correct: ID is directly in the returned dict
                # -----------------------------
                nifi_resp_create = {"query_id": query_id}
                local_logger.bind(interface="nifi", direction="response", data=nifi_resp_create).debug("Received from NiFi API")
                if not query_id:
                    raise ToolError("Failed to get query ID from NiFi for provenance search.")
                local_logger.info(f"Submitted provenance query: {query_id}")

                # 2. Poll for completion
                start_time = asyncio.get_event_loop().time()
                while True:
                    if (asyncio.get_event_loop().time() - start_time) > polling_timeout:
                        raise TimeoutError(f"Timed out waiting for provenance query {query_id} to complete.")

                    nifi_req_get = {"operation": "get_provenance_query", "query_id": query_id}
                    local_logger.bind(interface="nifi", direction="request", data=nifi_req_get).debug("Calling NiFi API (polling)")
                    query_status = await nifi_client.get_provenance_query(query_id)
                    nifi_resp_get = {"finished": query_status.get("query", {}).get("finished"), "percentCompleted": query_status.get("query", {}).get("percentCompleted")}
                    local_logger.bind(interface="nifi", direction="response", data=nifi_resp_get).debug("Received from NiFi API (polling)")

                    # --- Corrected Finished Check ---
                    # if query_status.get("query", {}).get("finished"): # Old incorrect check
                    if query_status.get("finished"): # Correct check directly on the status dict
                    # ------------------------------
                        local_logger.info(f"Provenance query {query_id} finished.")
                        # 3. Get results
                        # get_provenance_results already handles getting from completed query
                        events = await nifi_client.get_provenance_results(query_id)
                        
                        # --- Added Logging for Raw Events --- 
                        local_logger.debug(f"Retrieved {len(events)} raw provenance events from client.")
                        # if events:
                        #      local_logger.trace(f"First raw event details: {events[0]}") # Log first event details
                        # ------------------------------------

                        # --- Client-side Sorting & Limiting --- 
                        def parse_event_time(event_time_str: str) -> Optional[datetime]:
                            """Helper to parse NiFi timestamp string, stripping timezone."""
                            try:
                                # Expect format like "04/27/2025 10:55:06.137 EDT"
                                time_part = event_time_str.rsplit(' ', 1)[0] # Remove timezone part
                                return datetime.strptime(time_part, "%m/%d/%Y %H:%M:%S.%f")
                            except (ValueError, IndexError, AttributeError) as e:
                                local_logger.warning(f"Could not parse eventTime '{event_time_str}': {e}")
                                return None

                        # Sort events by time descending (most recent first)
                        sorted_events = sorted(
                            [e for e in events if parse_event_time(e.get("eventTime", "")) is not None], # Filter out unparseable
                            key=lambda e: parse_event_time(e["eventTime"]), 
                            reverse=True
                        )
                        
                        # Apply max_results limit
                        limited_events = sorted_events[:max_results]
                        local_logger.debug(f"Applied max_results={max_results}, using {len(limited_events)} events for summary.")
                        # -------------------------------------
                        
                        # Format events into summaries
                        # Note: Provenance events might show multiple stages for the same FlowFile.
                        # We will return one entry per event for simplicity, ordered by event time (default). 
                        results["flowfile_summaries"] = [
                            {
                                "uuid": event.get("flowFileUuid"),
                                "filename": event.get("previousAttributes", {}).get("filename") or event.get("updatedAttributes", {}).get("filename"), # Try both
                                # "size": event.get("fileSize"), # Use bytes value instead
                                "size_bytes": event.get("fileSizeBytes"), # Corrected field
                                "event_id": event.get("eventId"),
                                "event_type": event.get("eventType"),
                                "event_time": event.get("eventTime"),
                                "component_name": event.get("componentName"),
                                "attributes": event.get("updatedAttributes", {}), # Use updated attributes for the event
                            }
                            for event in limited_events # Use the sorted and limited list
                        ]
                        break
                    await asyncio.sleep(polling_interval)

            finally:
                # 4. Delete query
                if query_id:
                    local_logger.info(f"Cleaning up provenance query {query_id}...")
                    try:
                        nifi_req_del = {"operation": "delete_provenance_query", "query_id": query_id}
                        local_logger.bind(interface="nifi", direction="request", data=nifi_req_del).debug("Calling NiFi API")
                        await nifi_client.delete_provenance_query(query_id)
                        local_logger.bind(interface="nifi", direction="response", data={"deleted": True}).debug("Received from NiFi API")
                    except Exception as del_e:
                        local_logger.warning(f"Failed to delete provenance query {query_id}: {del_e}")

        else:
            raise ToolError(f"Invalid target_type: {target_type}. Must be 'connection' or 'processor'.")

        local_logger.info(f"Successfully listed {len(results['flowfile_summaries'])} flowfile summaries.")
        return results

    except (NiFiAuthenticationError, ConnectionError, ToolError, ValueError, TimeoutError) as e:
        local_logger.error(f"Error listing flowfiles for {target_type} {target_id}: {e}", exc_info=False)
        results["error"] = str(e)
        # Return partial results with error message
        return results
    except Exception as e:
        local_logger.error(f"Unexpected error listing flowfiles for {target_type} {target_id}: {e}", exc_info=True)
        results["error"] = f"An unexpected error occurred: {e}"
        # Return partial results with error message
        return results

@mcp.tool()
@tool_phases(["Review", "Operate"])
async def get_flowfile_event_details( # Renamed function
    event_id: int, # Changed parameter from flowfile_uuid
    max_content_bytes: int = 4096
    # Removed target_id, target_type, polling params
) -> Dict[str, Any]:
    """
    Retrieves detailed attributes and content for a specific FlowFile provenance event.

    Fetches the event details using the event ID and attempts to retrieve both the 
    input and output content associated with that event, subject to availability and limits.

    Args:
        event_id: The specific numeric ID of the provenance event.
        max_content_bytes: Max bytes of content to return for EACH direction (input/output).
                           -1 for unlimited (use with caution).

    Returns:
        A dictionary containing the event and content details.
    """
    # Get client and logger
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set.")

    local_logger = local_logger.bind(
        event_id=event_id, 
        max_content_bytes=max_content_bytes
    )
    local_logger.info("Getting FlowFile event details.")

    # Initialize results structure
    results = {
        "status": "error",
        "message": "",
        "event_id": event_id,
        "event_details": None,
        "attributes": None,
        "input_content_available": False,
        "input_content_truncated": False,
        "input_content_bytes": 0,
        "input_content": None, # Store content as string (decoded or base64)
        "output_content_available": False,
        "output_content_truncated": False,
        "output_content_bytes": 0,
        "output_content": None # Store content as string (decoded or base64)
    }
    
    # Helper function to process content stream
    async def _process_content(direction: Literal["input", "output"]) -> None:
        nonlocal results # Allow modifying the outer results dict
        content_resp = None
        try:
            nifi_req_content = {"operation": "get_provenance_event_content", "event_id": event_id, "direction": direction}
            local_logger.bind(interface="nifi", direction="request", data=nifi_req_content).debug(f"Calling NiFi API for {direction} content")
            content_resp = await nifi_client.get_provenance_event_content(event_id, direction)
            local_logger.bind(interface="nifi", direction="response", data={
                "status_code": content_resp.status_code, 
                "headers": dict(content_resp.headers)
                }).debug(f"Received from NiFi API for {direction} content")
            
            results[f"{direction}_content_available"] = True
            content_bytes_list = []
            bytes_read = 0
            async for chunk in content_resp.aiter_bytes():
                if max_content_bytes != -1 and (bytes_read + len(chunk)) > max_content_bytes:
                    chunk = chunk[:max_content_bytes - bytes_read]
                    content_bytes_list.append(chunk)
                    bytes_read += len(chunk)
                    results[f"{direction}_content_truncated"] = True
                    local_logger.warning(f"{direction.capitalize()} content truncated to {max_content_bytes} bytes.")
                    break
                content_bytes_list.append(chunk)
                bytes_read += len(chunk)
            
            results[f"{direction}_content_bytes"] = bytes_read
            full_content_bytes = b"".join(content_bytes_list)
            
            # Attempt to decode as UTF-8, fallback to base64
            try:
                results[f"{direction}_content"] = full_content_bytes.decode('utf-8')
                local_logger.info(f"Successfully fetched and decoded {bytes_read} bytes of {direction} content.")
            except UnicodeDecodeError:
                import base64
                results[f"{direction}_content"] = base64.b64encode(full_content_bytes).decode('ascii')
                local_logger.warning(f"Fetched {bytes_read} bytes of {direction} content, but failed to decode as UTF-8. Returning as base64.")
        
        except ValueError as content_err:
             # Specific error from get_provenance_event_content (e.g., 404)
             local_logger.warning(f"Could not retrieve {direction} content for event {event_id}: {content_err}")
             results[f"{direction}_content_available"] = False
        except Exception as content_exc:
             local_logger.error(f"Unexpected error retrieving {direction} content for event {event_id}: {content_exc}", exc_info=True)
             results[f"{direction}_content_available"] = False
             results["message"] += f" Unexpected error retrieving {direction} content." # Append error info
        finally:
             if content_resp:
                 await content_resp.aclose()
                 local_logger.debug(f"Closed {direction} content response stream.")

    try:
        # --- Step 1: Get Event Details --- 
        local_logger.info(f"Fetching details for provenance event {event_id}...")
        nifi_req_event = {"operation": "get_provenance_event", "event_id": event_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_req_event).debug("Calling NiFi API")
        event_details = await nifi_client.get_provenance_event(event_id)
        local_logger.bind(interface="nifi", direction="response", data=event_details).debug("Received from NiFi API")

        if not event_details:
             raise ValueError(f"No details returned for event {event_id}.")

        results["event_details"] = event_details # Store raw event details
        # Attributes can be complex, decide how much to expose
        # Using the flattened list structure like the UI might be good
        results["attributes"] = event_details.get("attributes", []) 
        local_logger.info(f"Found event {event_id} (Type: {event_details.get('eventType')}). Details retrieved.")

        # --- Step 2: Get Input Content --- 
        if event_details.get("inputContentAvailable"): # Check if claim exists
            local_logger.info(f"Input content reported as available for event {event_id}. Attempting fetch...")
            await _process_content("input")
        else:
             local_logger.info(f"Input content not available for event {event_id}.")
             results["input_content_available"] = False

        # --- Step 3: Get Output Content --- 
        if event_details.get("outputContentAvailable"): # Check if claim exists
            local_logger.info(f"Output content reported as available for event {event_id}. Attempting fetch...")
            await _process_content("output")
        else:
             local_logger.info(f"Output content not available for event {event_id}.")
             results["output_content_available"] = False

        # --- Final Status --- 
        if results["attributes"] is not None:
            results["status"] = "success"
            if results["input_content_available"] or results["output_content_available"]:
                results["message"] = f"Successfully retrieved event details and available content for event {event_id}."
            else:
                 results["message"] = f"Successfully retrieved event details for event {event_id}. No content was available."
        else:
            # Should have errored earlier if event details failed, but good fallback
            results["message"] = f"Failed to retrieve details for event {event_id}."
        
        return results

    except (NiFiAuthenticationError, ConnectionError, ToolError, ValueError, TimeoutError) as e:
        local_logger.error(f"Error getting flowfile event details for event {event_id}: {e}", exc_info=False)
        results["status"] = "error"
        results["message"] = str(e)
        return results
    except Exception as e:
        local_logger.error(f"Unexpected error getting flowfile event details for event {event_id}: {e}", exc_info=True)
        results["status"] = "error"
        results["message"] = f"An unexpected error occurred: {e}"
        return results
    # Removed finally block with query cleanup as query is no longer submitted here
