from contextvars import ContextVar
from typing import Optional

# Import types carefully to avoid circular dependencies if types are complex
# For now, assume basic types or forward references if needed
from nifi_mcp_server.nifi_client import NiFiClient
from loguru._logger import Logger # Correct import for type hint

# Context variables to hold request-specific instances
current_nifi_client: ContextVar[Optional[NiFiClient]] = ContextVar("current_nifi_client", default=None)
current_request_logger: ContextVar[Optional[Logger]] = ContextVar("current_request_logger", default=None)
current_user_request_id: ContextVar[Optional[str]] = ContextVar("current_user_request_id", default=None)
current_action_id: ContextVar[Optional[str]] = ContextVar("current_action_id", default=None)
current_process_group : ContextVar[Optional[str]] = ContextVar("current_process_group", default=None)
# Usage example (in tool functions):
# from .request_context import current_nifi_client, current_request_logger, current_user_request_id, current_action_id
#
# nifi_client = current_nifi_client.get()
# logger = current_request_logger.get()
# user_request_id = current_user_request_id.get() or "-"
# action_id = current_action_id.get() or "-"
# if not nifi_client or not logger:
#     raise ToolError("Required context (client or logger) is not set.")
# # ... use nifi_client and logger ...
# # ... pass user_request_id, action_id to specific client methods if needed ...

# Usage example (in server.py):
# from .request_context import current_nifi_client, current_request_logger, current_user_request_id, current_action_id
#
# client_token = current_nifi_client.set(nifi_client_instance)
# logger_token = current_request_logger.set(bound_logger_instance)
# user_id_token = current_user_request_id.set(user_request_id_from_header)
# action_id_token = current_action_id.set(action_id_from_header)
# try:
#     # ... call mcp.execute_tool ...
# finally:
#     current_nifi_client.reset(client_token)
#     current_request_logger.reset(logger_token)
#     current_user_request_id.reset(user_id_token)
#     current_action_id.reset(action_id_token) 