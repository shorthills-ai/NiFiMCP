import asyncio
from typing import List, Dict, Optional, Any, Union, Literal

# Import necessary components from parent/utils
from loguru import logger
# Import mcp ONLY
from ..core import mcp
# Removed nifi_api_client import
# Import context variables
from ..request_context import current_process_group,current_nifi_client, current_request_logger, current_user_request_id, current_action_id # Added

from .utils import (
    tool_phases,
    # ensure_authenticated, # Removed
    filter_created_processor_data,
    filter_connection_data,
    filter_port_data,
    filter_process_group_data,
    filter_processor_data # Needed for create_nifi_flow
)
from nifi_mcp_server.nifi_client import NiFiClient, NiFiAuthenticationError
from mcp.server.fastmcp.exceptions import ToolError

# --- Tool Definitions --- 

@mcp.tool()
@tool_phases(["Modify"])
async def create_nifi_processor(
    processor_type: str,
    name: str,
    position_x: int,
    position_y: int,
    process_group_id: str | None = None,
    properties: Optional[Dict[str, Any]] = None
) -> Dict:
    """
    Creates a new processor within a specified NiFi process group.

    Example Call:
    ```tool_code
    print(default_api.create_nifi_processor(processor_type='org.apache.nifi.processors.standard.LogAttribute', name='Log Test Attribute', position_x=200, position_y=300, properties={'Log Level': 'info', 'Attributes to Log': 'uuid, filename'}))
    ```

    Args:
        processor_type: The fully qualified Java class name of the processor type (e.g., 'org.apache.nifi.processors.standard.ReplaceText').
        name: The desired name for the new processor instance.
        position_x: The desired X coordinate for the processor's position on the canvas.
        position_y: The desired Y coordinate for the processor's position on the canvas.
        process_group_id: The UUID of the target process group. If None, the root process group of the NiFi instance will be used.
        properties: A dictionary containing the processor's configuration properties. Provide the properties directly as key-value pairs. Do NOT include the 'properties' key itself within this dictionary, as it will be added automatically by the underlying client. Example: {'Replacement Strategy': 'Always Replace', 'Replacement Value': 'Hello'}.

    Returns:
        A dictionary reporting the success, warning, or error status of the operation, potentially including the created processor entity details.
    """
    # Get client and logger from context
    session_pg_id=current_process_group.get()
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set. This tool requires the X-Nifi-Server-Id header.")
    if not local_logger:
         raise ToolError("Request logger context is not set.")
         
    # Authentication handled by factory
    # context = local_logger._context # REMOVED
    # user_request_id = context.get("user_request_id", "-") # REMOVED
    # action_id = context.get("action_id", "-") # REMOVED
    # --- Get IDs from context ---
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    session_pg_id=current_process_group.get()

    # --------------------------

    target_pg_id = process_group_id
    if target_pg_id is None:
        local_logger.info("No process_group_id provided for creation, fetching root process group ID.")
        try:
            nifi_request_data = {"operation": "get_root_process_group_id"}
            local_logger.bind(interface="nifi", direction="request", data=nifi_request_data).debug("Calling NiFi API")
            target_pg_id = session_pg_id
            if target_pg_id is None:
                target_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
            nifi_response_data = {"root_pg_id": target_pg_id}
            local_logger.bind(interface="nifi", direction="response", data=nifi_response_data).debug("Received from NiFi API")
        except Exception as e:
            local_logger.error(f"Failed to get root process group ID: {e}", exc_info=True)
            local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
            raise ToolError(f"Failed to determine root process group ID for creation: {e}")

    position = {"x": position_x, "y": position_y}
    local_logger = local_logger.bind(process_group_id=target_pg_id) # Bind PG ID to logger now
    local_logger.info(f"Executing create_nifi_processor: Type='{processor_type}', Name='{name}', Position={position}")

    try:
        nifi_request_data = {
            "operation": "create_processor", 
            "process_group_id": target_pg_id,
            "processor_type": processor_type,
            "name": name,
            "position": position,
            "config": properties
        }
        if not await nifi_client.is_descendant(target_pg_id, session_pg_id):
            raise ToolError(f"Target process group {target_pg_id} is not a descendant of the current process group {session_pg_id}.")
        local_logger.bind(interface="nifi", direction="request", data=nifi_request_data).debug("Calling NiFi API")
        processor_entity = await nifi_client.create_processor(
            process_group_id=target_pg_id,
            processor_type=processor_type,
            name=name,
            position=position,
            config=properties
        )
        nifi_response_data = filter_created_processor_data(processor_entity)
        local_logger.bind(interface="nifi", direction="response", data=nifi_response_data).debug("Received from NiFi API")
        
        local_logger.info(f"Successfully created processor '{name}' with ID: {processor_entity.get('id', 'N/A')}")
        
        component = processor_entity.get("component", {})
        validation_status = component.get("validationStatus", "UNKNOWN")
        validation_errors = component.get("validationErrors", [])
        
        if validation_status == "VALID":
            return {
                "status": "success",
                "message": f"Processor '{name}' created successfully.",
                "entity": nifi_response_data
            }
        else:
            error_msg_snippet = f" ({validation_errors[0]})" if validation_errors else ""
            local_logger.warning(f"Processor '{name}' created but is {validation_status}{error_msg_snippet}. Requires configuration or connections.")
            return {
                "status": "warning",
                "message": f"Processor '{name}' created but is currently {validation_status}{error_msg_snippet}. Further configuration or connections likely required.",
                "entity": nifi_response_data
            }
            
    except (NiFiAuthenticationError, ConnectionError, ValueError) as e:
        local_logger.error(f"API error creating processor: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        # Return structured error instead of raising ToolError
        return {"status": "error", "message": f"Failed to create NiFi processor: {e}", "entity": None}
    except Exception as e:
        local_logger.error(f"Unexpected error creating processor: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        return {"status": "error", "message": f"An unexpected error occurred during processor creation: {e}", "entity": None}


@mcp.tool()
@tool_phases(["Modify"])
async def create_nifi_connection(
    source_id: str,
    relationships: List[str],
    target_id: str,
) -> Dict:
    """
    Creates a connection between two components (processors or ports) within the same NiFi process group.

    Args:
        source_id: The UUID of the source component.
        relationships: A non-empty list of relationship names.
        target_id: The UUID of the target component.

    Returns:
        A dictionary representing the created connection entity or an error message.
    """
    # Get client and logger from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set. This tool requires the X-Nifi-Server-Id header.")
    if not local_logger:
         raise ToolError("Request logger context is not set.")
         
    # Authentication handled by factory
    # context = local_logger._context # REMOVED
    # user_request_id = context.get("user_request_id", "-") # REMOVED
    # action_id = context.get("action_id", "-") # REMOVED
    # --- Get IDs from context ---
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    session_pg_id=current_process_group.get()
    # --------------------------

    local_logger = local_logger.bind(source_id=source_id, target_id=target_id, relationships=relationships)
         
    if not relationships:
        raise ToolError("The 'relationships' list cannot be empty.")
    if not isinstance(relationships, list) or not all(isinstance(item, str) for item in relationships):
        raise ToolError("Invalid 'relationships' elements.")

    source_entity = None
    source_type = None
    target_entity = None
    target_type = None

    local_logger.info(f"Fetching details for source component {source_id}...")
    try:
        try:
            source_entity = await nifi_client.get_processor_details(source_id)
            source_type = "PROCESSOR"
            local_logger.info(f"Source component {source_id} identified as a PROCESSOR.")
        except ValueError:
            try:
                source_entity = await nifi_client.get_input_port_details(source_id)
                source_type = "INPUT_PORT"
                local_logger.info(f"Source component {source_id} identified as an INPUT_PORT.")
            except ValueError:
                try:
                    source_entity = await nifi_client.get_output_port_details(source_id)
                    source_type = "OUTPUT_PORT"
                    local_logger.info(f"Source component {source_id} identified as an OUTPUT_PORT.")
                except ValueError:
                    raise ToolError(f"Source component with ID {source_id} not found or is not connectable.")
        if session_pg_id:
            if not await nifi_client.is_descendant(source_entity.get('component',{}).get("parentGroupId"),session_pg_id):
                raise ToolError(f"Source component {source_id} is not in the current process group {session_pg_id}.")
        local_logger.info(f"Fetching details for target component {target_id}...")
        try:
            target_entity = await nifi_client.get_processor_details(target_id)
            target_type = "PROCESSOR"
            local_logger.info(f"Target component {target_id} identified as a PROCESSOR.")
        except ValueError:
            try:
                target_entity = await nifi_client.get_input_port_details(target_id)
                target_type = "INPUT_PORT"
                local_logger.info(f"Target component {target_id} identified as an INPUT_PORT.")
            except ValueError:
                try:
                    target_entity = await nifi_client.get_output_port_details(target_id)
                    target_type = "OUTPUT_PORT"
                    local_logger.info(f"Target component {target_id} identified as an OUTPUT_PORT.")
                except ValueError:
                     raise ToolError(f"Target component with ID {target_id} not found or is not connectable.")

        source_parent_pg_id = source_entity.get("component", {}).get("parentGroupId")
        target_parent_pg_id = target_entity.get("component", {}).get("parentGroupId")

        if not source_parent_pg_id or not target_parent_pg_id:
            missing_component = "source" if not source_parent_pg_id else "target"
            local_logger.error(f"Could not determine parent group ID for {missing_component} component.")
            raise ToolError(f"Could not determine parent group ID for {missing_component}.")

        if source_parent_pg_id != target_parent_pg_id:
            local_logger.error(f"Source ({source_parent_pg_id}) and target ({target_parent_pg_id}) are in different groups.")
            raise ToolError(f"Source and target components must be in the same process group.")

        common_parent_pg_id = source_parent_pg_id
        local_logger = local_logger.bind(process_group_id=common_parent_pg_id)
        local_logger.info(f"Validated components are in the same group: {common_parent_pg_id}")

    except (ValueError, NiFiAuthenticationError, ConnectionError) as e:
         local_logger.error(f"API error fetching component details: {e}", exc_info=False)
         raise ToolError(f"Failed to fetch details for components: {e}")
    except Exception as e:
         local_logger.error(f"Unexpected error fetching component details: {e}", exc_info=True)
         raise ToolError(f"An unexpected error occurred fetching details: {e}")

    local_logger.info(f"Checking for existing connections between {source_id} and {target_id}...")
    try:
        nifi_list_req = {"operation": "list_connections", "process_group_id": common_parent_pg_id}
        local_logger.bind(interface="nifi", direction="request", data=nifi_list_req).debug("Calling NiFi API")
        existing_connections = await nifi_client.list_connections(common_parent_pg_id, user_request_id=user_request_id, action_id=action_id)
        nifi_list_resp = {"connection_count": len(existing_connections)}
        local_logger.bind(interface="nifi", direction="response", data=nifi_list_resp).debug("Received from NiFi API")
        
        for existing_conn_entity in existing_connections:
            existing_comp = existing_conn_entity.get("component", {})
            existing_source = existing_comp.get("source", {})
            existing_dest = existing_comp.get("destination", {})
            
            if existing_source.get("id") == source_id and existing_dest.get("id") == target_id:
                existing_conn_id = existing_conn_entity.get("id")
                local_logger.warning(f"Duplicate connection detected: {existing_conn_id}")
                try:
                    existing_conn_details = await nifi_client.get_connection(existing_conn_id)
                    existing_relationships = existing_conn_details.get("component", {}).get("selectedRelationships", [])
                except Exception as detail_err:
                    local_logger.error(f"Could not fetch details for existing connection {existing_conn_id}: {detail_err}")
                    existing_relationships = ["<error retrieving>"]
                error_msg = (
                    f"A connection already exists between source '{source_id}' and target '{target_id}'. "
                    f"ID: {existing_conn_id}. Relationships: {existing_relationships}. "
                    f"Use 'update_nifi_connection' to modify."
                )
                return {"status": "error", "message": error_msg, "entity": None}
        local_logger.info("No duplicate connection found. Proceeding with creation.")
    except (NiFiAuthenticationError, ConnectionError, ValueError) as e:
        local_logger.error(f"API error checking existing connections: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        raise ToolError(f"Failed to check for existing connections: {e}")
    except Exception as e:
        local_logger.error(f"Unexpected error checking existing connections: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        raise ToolError(f"An unexpected error occurred checking connections: {e}")

    local_logger.info(f"Attempting to create connection from {source_type} '{source_id}' ({relationships}) to {target_type} '{target_id}' in group {common_parent_pg_id}")
    try:
        nifi_create_req = {
            "operation": "create_connection",
            "process_group_id": common_parent_pg_id,
            "source_id": source_id,
            "target_id": target_id,
            "relationships": relationships,
            "source_type": source_type,
            "target_type": target_type
        }
        local_logger.bind(interface="nifi", direction="request", data=nifi_create_req).debug("Calling NiFi API")
        
        connection_entity = await nifi_client.create_connection(
            process_group_id=common_parent_pg_id,
            source_id=source_id,
            target_id=target_id,
            relationships=relationships,
            source_type=source_type,
            target_type=target_type
        )
        filtered_entity = filter_connection_data(connection_entity)
        local_logger.bind(interface="nifi", direction="response", data=filtered_entity).debug("Received from NiFi API")
        
        local_logger.info(f"Successfully created connection with ID: {connection_entity.get('id', 'N/A')}")
        return {
            "status": "success",
            "message": "Connection created successfully.",
            "entity": filtered_entity
        }

    except (NiFiAuthenticationError, ConnectionError, ValueError) as e:
        local_logger.error(f"API error creating connection: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        # Return structured error instead of raising ToolError
        return {"status": "error", "message": f"Failed to create NiFi connection: {e}", "entity": None}
    except Exception as e:
        local_logger.error(f"Unexpected error creating connection: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        return {"status": "error", "message": f"An unexpected error occurred during connection creation: {e}", "entity": None}


@mcp.tool()
@tool_phases(["Modify"])
async def create_nifi_port(
    port_type: Literal["input", "output"],
    name: str,
    position_x: int,
    position_y: int,
    process_group_id: str | None = None
) -> Dict:
    """
    Creates a new input or output port within a specified NiFi process group.

    Args:
        port_type: Whether to create an "input" or "output" port.
        name: The desired name for the new port instance.
        position_x: The desired X coordinate for the port on the canvas.
        position_y: The desired Y coordinate for the port on the canvas.
        process_group_id: The UUID of the process group where the port should be created. Defaults to the root group if None.

    Returns:
        A dictionary representing the result, including status and the created port entity.
    """
    # Get client and logger from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set. This tool requires the X-Nifi-Server-Id header.")
    if not local_logger:
         raise ToolError("Request logger context is not set.")
         
    # Authentication handled by factory
    # context = local_logger._context # REMOVED
    # user_request_id = context.get("user_request_id", "-") # REMOVED
    # action_id = context.get("action_id", "-") # REMOVED
    # --- Get IDs from context ---
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    session_pg_id=current_process_group.get()
    # --------------------------

    target_pg_id = process_group_id
    if target_pg_id is None:
        local_logger.info("No process_group_id provided, fetching root process group ID.")
        try:
            nifi_request_data = {"operation": "get_root_process_group_id"}
            local_logger.bind(interface="nifi", direction="request", data=nifi_request_data).debug("Calling NiFi API")
            target_pg_id = session_pg_id
            if target_pg_id is None:
                target_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
            nifi_response_data = {"root_pg_id": target_pg_id}
            local_logger.bind(interface="nifi", direction="response", data=nifi_response_data).debug("Received from NiFi API")
        except Exception as e:
            local_logger.error(f"Failed to get root process group ID: {e}", exc_info=True)
            local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
            raise ToolError(f"Failed to determine root process group ID for port creation: {e}")

    position = {"x": position_x, "y": position_y}
    local_logger = local_logger.bind(process_group_id=target_pg_id, port_type=port_type)
    local_logger.info(f"Executing create_nifi_port: Type='{port_type}', Name='{name}', Position={position}")

    try:
        nifi_request_data = {
            "operation": f"create_{port_type}_port",
            "process_group_id": target_pg_id,
            "name": name,
            "position": position
        }
        if not await nifi_client.is_descendant(target_pg_id, session_pg_id):
            raise ToolError(f"Target process group {target_pg_id} is not a descendant of the current process group {session_pg_id}.")
        local_logger.bind(interface="nifi", direction="request", data=nifi_request_data).debug("Calling NiFi API")

        if port_type == "input":
            port_entity = await nifi_client.create_input_port(target_pg_id, name, position)
        else: # port_type == "output"
            port_entity = await nifi_client.create_output_port(target_pg_id, name, position)
            
        filtered_entity = filter_port_data(port_entity)
        local_logger.bind(interface="nifi", direction="response", data=filtered_entity).debug("Received from NiFi API")
        
        port_id = port_entity.get('id', 'N/A')
        local_logger.info(f"Successfully created {port_type} port '{name}' with ID: {port_id}")
        return {
            "status": "success",
            "message": f"{port_type.capitalize()} port '{name}' created successfully.",
            "entity": filtered_entity
        }

    except (NiFiAuthenticationError, ConnectionError, ValueError) as e:
        local_logger.error(f"API error creating {port_type} port: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        return {"status": "error", "message": f"Failed to create NiFi {port_type} port: {e}", "entity": None}
    except Exception as e:
        local_logger.error(f"Unexpected error creating {port_type} port: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        return {"status": "error", "message": f"An unexpected error occurred during {port_type} port creation: {e}", "entity": None}


@mcp.tool()
@tool_phases(["Modify"])
async def create_nifi_process_group(
    name: str,
    position_x: int,
    position_y: int,
    parent_process_group_id: str | None = None
) -> Dict:
    """
    Creates a new process group within a specified parent NiFi process group.

    Args:
        name: The desired name for the new process group.
        position_x: The desired X coordinate for the process group on the canvas.
        position_y: The desired Y coordinate for the process group on the canvas.
        parent_process_group_id: The UUID of the parent process group where the new group should be created. Defaults to the root group if None.

    Returns:
        A dictionary representing the result, including status and the created process group entity.
    """
    # Get client and logger from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set. This tool requires the X-Nifi-Server-Id header.")
    if not local_logger:
         raise ToolError("Request logger context is not set.")
         
    # Authentication handled by factory
    # context = local_logger._context # REMOVED
    # user_request_id = context.get("user_request_id", "-") # REMOVED
    # action_id = context.get("action_id", "-") # REMOVED
    # --- Get IDs from context ---
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    session_pg_id=current_process_group.get()
    # --------------------------

    target_parent_pg_id = parent_process_group_id
    if target_parent_pg_id is None:
        local_logger.info("No parent_process_group_id provided, fetching root process group ID.")
        try:
            nifi_request_data = {"operation": "get_root_process_group_id"}
            local_logger.bind(interface="nifi", direction="request", data=nifi_request_data).debug("Calling NiFi API")
            target_parent_pg_id = session_pg_id
            if target_parent_pg_id is None:
                target_parent_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
            nifi_response_data = {"root_pg_id": target_parent_pg_id}
            local_logger.bind(interface="nifi", direction="response", data=nifi_response_data).debug("Received from NiFi API")
        except Exception as e:
            local_logger.error(f"Failed to get root process group ID: {e}", exc_info=True)
            local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
            raise ToolError(f"Failed to determine root process group ID for PG creation: {e}")

    position = {"x": position_x, "y": position_y}
    local_logger = local_logger.bind(parent_process_group_id=target_parent_pg_id)
    local_logger.info(f"Executing create_nifi_process_group: Name='{name}', Position={position}")

    try:
        nifi_request_data = {
            "operation": "create_process_group",
            "parent_process_group_id": target_parent_pg_id,
            "name": name,
            "position": position
        }
        if not await nifi_client.is_descendant(target_parent_pg_id, session_pg_id):
            raise ToolError(f"Target process group {target_parent_pg_id} is not a descendant of the current process group {session_pg_id}.")
        local_logger.bind(interface="nifi", direction="request", data=nifi_request_data).debug("Calling NiFi API")

        pg_entity = await nifi_client.create_process_group(target_parent_pg_id, name, position)
        filtered_entity = filter_process_group_data(pg_entity)
        local_logger.bind(interface="nifi", direction="response", data=filtered_entity).debug("Received from NiFi API")
        
        pg_id = pg_entity.get('id', 'N/A')
        local_logger.info(f"Successfully created process group '{name}' with ID: {pg_id}")
        return {
            "status": "success",
            "message": f"Process group '{name}' created successfully.",
            "entity": filtered_entity
        }

    except (NiFiAuthenticationError, ConnectionError, ValueError) as e:
        local_logger.error(f"API error creating process group: {e}", exc_info=False)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        return {"status": "error", "message": f"Failed to create NiFi process group: {e}", "entity": None}
    except Exception as e:
        local_logger.error(f"Unexpected error creating process group: {e}", exc_info=True)
        local_logger.bind(interface="nifi", direction="response", data={"error": str(e)}).debug("Received error from NiFi API")
        return {"status": "error", "message": f"An unexpected error occurred during process group creation: {e}", "entity": None}


@mcp.tool()
@tool_phases(["Build"])
async def create_nifi_flow(
    nifi_objects: List[Dict[str, Any]],
    process_group_id: str | None = None,
    create_process_group: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Creates a NiFi flow based on a list of processors and connections.
    Can optionally create a new process group to contain the flow.

    Example:
    ```python
    nifi_objects = [
        {"type": "processor", "class": "org.apache.nifi.processors.standard.LogAttribute", "name": "LogAttribute", "position": {"x": 100, "y": 100}, "properties": {"Attribute": "mcp-test-log"}},
        {"type": "processor", "class": "org.apache.nifi.processors.standard.GenerateFlowFile", "name": "GenerateFlowFile", "position": {"x": 200, "y": 200}},
        {"type": "connection", "source": "LogAttribute", "dest": "GenerateFlowFile", "relationships": ["success"]}
    ]
    ```

    Args:
        nifi_objects: A list where each item describes a processor or connection.
            Preferred Processor Format: {"type": "processor", "class": "org.apache.nifi...", "name": "MyProc", "position": {"x": X, "y": Y}, "properties": {...}}
            Preferred Connection Format: {"type": "connection", "source": "MyProc", "dest": "OtherProc", "relationships": ["success"]} # Use 'name' from a processor in this list for 'source' and 'dest'
            Note: Processor 'name' is used for mapping connections and must be unique within this list. The tool attempts to parse common variations, but the preferred format is recommended.
        process_group_id: The ID of the existing process group to create the flow in. Ignored if `create_process_group` is provided.
        create_process_group: Optional. If provided, a new process group is created with this configuration {"name": "NewGroup", "position_x": X, "position_y": Y} and the flow is built inside it.

    Returns:
        A list of results, one for each object creation attempt (success or error).
    """
    # Get client and logger from context
    nifi_client: Optional[NiFiClient] = current_nifi_client.get()
    local_logger = current_request_logger.get() or logger
    if not nifi_client:
        raise ToolError("NiFi client context is not set. This tool requires the X-Nifi-Server-Id header.")
    if not local_logger:
         raise ToolError("Request logger context is not set.")
         
    # Authentication handled by factory
    # context = local_logger._context # REMOVED
    # user_request_id = context.get("user_request_id", "-") # REMOVED
    # action_id = context.get("action_id", "-") # REMOVED
    # --- Get IDs from context ---
    user_request_id = current_user_request_id.get() or "-"
    action_id = current_action_id.get() or "-"
    session_pg_id=current_process_group.get()
    # --------------------------
    
    results = []
    id_map = {}  # Maps local_id to actual NiFi ID
    target_pg_id = process_group_id
    parent_pg_id_for_new_group = None

    try:
        # 1. Determine target process group ID
        if create_process_group:
            local_logger.info(f"Request to create new process group: {create_process_group.get('name')}")
            pg_name = create_process_group.get("name")
            pg_pos_x = create_process_group.get("position_x", 0)
            pg_pos_y = create_process_group.get("position_y", 0)
            parent_pg_id_for_new_group = process_group_id # Parent for the *new* group
            
            if not pg_name:
                raise ToolError("Missing 'name' in create_process_group configuration.")

            # Determine the parent ID for the new PG (defaults to root if not specified)
            if parent_pg_id_for_new_group is None:
                parent_pg_id_for_new_group = session_pg_id
                if parent_pg_id_for_new_group is None:
                    parent_pg_id_for_new_group = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
                local_logger.info(f"No explicit parent ID for new group, using root: {parent_pg_id_for_new_group}")
            else:
                if not await nifi_client.is_descendant(parent_pg_id_for_new_group, session_pg_id):
                    raise ToolError(f"Parent process group {parent_pg_id_for_new_group} is not a descendant of the current process group {session_pg_id}.")
            # Call create_nifi_process_group tool logic (or direct client call)
            pg_creation_result = await create_nifi_process_group(
                name=pg_name,
                position_x=pg_pos_x,
                position_y=pg_pos_y,
                parent_process_group_id=parent_pg_id_for_new_group
            )
            results.append(pg_creation_result)
            if pg_creation_result.get("status") == "error":
                raise ToolError(f"Failed to create process group: {pg_creation_result.get('message')}")
            
            target_pg_id = pg_creation_result.get("entity", {}).get("id")
            if not target_pg_id:
                 raise ToolError("Could not get ID of newly created process group.")
            local_logger.info(f"Successfully created process group '{pg_name}' with ID {target_pg_id}. Flow will be built inside.")
        
        elif target_pg_id is None:
            target_pg_id = session_pg_id
            if target_pg_id is None:
                target_pg_id = await nifi_client.get_root_process_group_id(user_request_id=user_request_id, action_id=action_id)
            local_logger.info(f"No process group specified, using root group: {target_pg_id}")
        else:
            local_logger.info(f"Using existing process group: {target_pg_id}")
        
        local_logger = local_logger.bind(target_process_group_id=target_pg_id)

        # 2. Create Processors
        local_logger.info(f"Processing {len(nifi_objects)} objects for processor creation...")
        for item in nifi_objects:
            if item.get("type") == "processor": # Check top-level type
                proc_def = item # Use the item directly
                proc_name = proc_def.get("name")
                # Get type from 'class' key, fallback to 'processor_type' or 'type'
                proc_type = proc_def.get("class") or proc_def.get("processor_type") or proc_def.get("type")
                # Get position dictionary
                position_dict = proc_def.get("position", {})
                pos_x = position_dict.get("x")
                pos_y = position_dict.get("y")
                # Get properties (might be nested or top-level depending on LLM mood)
                properties = proc_def.get("properties", {}) 

                if not proc_name:
                    results.append({"status": "error", "message": "Processor definition missing 'name'.", "definition": proc_def})
                    continue
                if proc_name in id_map:
                    results.append({"status": "error", "message": f"Duplicate processor name '{proc_name}' found. Names must be unique for connection mapping.", "definition": proc_def})
                    continue

                if not all([proc_type, pos_x is not None, pos_y is not None]):
                    results.append({"status": "error", "message": f"Processor '{proc_name}' definition missing required fields (class/processor_type/type, position.x, position.y).", "definition": proc_def})
                    continue

                local_logger.info(f"Attempting to create processor: Name='{proc_name}', Type='{proc_type}'")
                # Call create_nifi_processor tool logic
                proc_creation_result = await create_nifi_processor(
                    processor_type=proc_type,
                    name=proc_name,
                    position_x=pos_x,
                    position_y=pos_y,
                    process_group_id=target_pg_id,
                    properties=properties
                )
                # We also need to apply the properties if provided
                created_proc_id = None
                if proc_creation_result.get("status") != "error":
                    created_proc_id = proc_creation_result.get("entity", {}).get("id")
                proc_creation_result["name_used_for_mapping"] = proc_name
                results.append(proc_creation_result)

                if proc_creation_result.get("status") != "error" and created_proc_id:
                    id_map[proc_name] = created_proc_id # Map NAME to NiFi ID
                    local_logger.debug(f"Mapped name '{proc_name}' to ID '{created_proc_id}'")
                elif proc_creation_result.get("status") != "error" and not created_proc_id:
                    local_logger.error(f"Could not get NiFi ID for created processor with name '{proc_name}'")
                    proc_creation_result["status"] = "error"
                    proc_creation_result["message"] += " (Could not retrieve NiFi ID after creation)"
                else:
                    local_logger.error(f"Failed to create processor with name '{proc_name}': {proc_creation_result.get('message')}")

        # 3. Create Connections
        local_logger.info(f"Processing {len(nifi_objects)} objects for connection creation...")
        for item in nifi_objects:
            if item.get("type") == "connection": # Check top-level type
                conn_def = item # Use the item directly
                # Extract details using names
                source_name = conn_def.get("source") # Expecting name
                target_name = conn_def.get("dest") or conn_def.get("destination") # Allow variations
                relationships = conn_def.get("relationships")

                if not all([source_name, target_name, relationships]):
                    results.append({"status": "error", "message": "Connection definition missing required fields (source name, dest/destination name, relationships).", "definition": conn_def})
                    continue
                
                # Use names to lookup NiFi IDs from our map
                source_nifi_id = id_map.get(source_name)
                target_nifi_id = id_map.get(target_name)

                if not source_nifi_id:
                    results.append({"status": "error", "message": f"Source component with name '{source_name}' not found or failed to create.", "definition": conn_def})
                    continue
                if not target_nifi_id:
                    results.append({"status": "error", "message": f"Target component with name '{target_name}' not found or failed to create.", "definition": conn_def})
                    continue

                local_logger.info(f"Attempting to create connection: From='{source_name}' ({source_nifi_id}) To='{target_name}' ({target_nifi_id}) Rel='{relationships}'")
                # Call create_nifi_connection tool logic
                conn_creation_result = await create_nifi_connection(
                    source_id=source_nifi_id,
                    target_id=target_nifi_id,
                    relationships=relationships
                )
                conn_creation_result["definition"] = conn_def
                results.append(conn_creation_result)
                
                if conn_creation_result.get("status") == "error":
                     local_logger.error(f"Failed to create connection from '{source_name}' to '{target_name}': {conn_creation_result.get('message')}")
                 
        # 4. Identify and report any unprocessed items
        processed_indices = set()
        for i, item in enumerate(nifi_objects):
            # Check if item was processed as a processor or connection based on our loops
            if item.get("type") == "processor" or item.get("type") == "connection":
                 processed_indices.add(i)
            # Add checks here if we support other types later

        unprocessed_items = []
        for i, item in enumerate(nifi_objects):
            if i not in processed_indices:
                unprocessed_items.append({
                    "index": i,
                    "item": item, # Include the problematic item for context
                    "message": f"Input object at index {i} was ignored. Expected 'type' to be 'processor' or 'connection'."
                })

        if unprocessed_items:
            local_logger.warning(f"Found {len(unprocessed_items)} unprocessed items in the input list.")
            # Add a summary error or individual errors to the main results
            results.append({
                "status": "warning",
                "message": f"{len(unprocessed_items)} input object(s) were ignored due to unrecognized type.",
                "unprocessed_details": unprocessed_items # Provide details
            })

        local_logger.info("Finished processing all objects for flow creation.")
        return results

    except ToolError as e:
        local_logger.error(f"ToolError during flow creation: {e}", exc_info=False)
        # Append the final error to results if possible
        results.append({"status": "error", "message": f"Flow creation failed: {e}"})
        return results
    except Exception as e:
        local_logger.error(f"Unexpected error during flow creation: {e}", exc_info=True)
        results.append({"status": "error", "message": f"An unexpected error occurred during flow creation: {e}"})
        return results
