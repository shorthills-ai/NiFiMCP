import os
# import logging # Remove standard logging
from loguru import logger # Import Loguru logger
import httpx
# from dotenv import load_dotenv # Removed dotenv
import uuid # Import uuid for client ID generation
from typing import Optional, Dict, Any, Union, List, Literal # Add Union and List
from mcp.server.fastmcp.exceptions import ToolError # Import ToolError
from functools import lru_cache
# Load environment variables from .env file - REMOVED
# load_dotenv()

# Set up logging - REMOVED standard logging setup
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

class NiFiAuthenticationError(Exception):
    """Raised when there is an error authenticating with NiFi."""
    pass

class NiFiClient:
    """A simple asynchronous client for the NiFi REST API."""

    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None, tls_verify: bool = True):
        """Initializes the NiFiClient.

        Args:
            base_url: The base URL of the NiFi API (e.g., "https://localhost:8443/nifi-api"). Required.
            username: The username for NiFi authentication. Required if password is provided.
            password: The password for NiFi authentication. Required if username is provided.
            tls_verify: Whether to verify the server's TLS certificate. Defaults to True.
        """
        if not base_url:
            raise ValueError("base_url is required for NiFiClient")
        self.base_url = base_url
        self.username = username
        self.password = password
        self.tls_verify = tls_verify
        self._client = None
        self._token = None
        # Generate a unique client ID for this instance, used for revisions
        self._client_id = str(uuid.uuid4())
        self.pg_id= "root"
        logger.info(f"NiFiClient initialized for {self.base_url} with client ID: {self._client_id}")

    @property
    def is_authenticated(self) -> bool:
        """Checks if the client currently holds an authentication token."""
        return self._token is not None

    async def _get_client(self):
        """Returns an httpx client instance, configuring auth if token exists."""
        # Always create a new client instance to ensure headers are fresh,
        # especially after authentication. If performance becomes an issue,
        # we could optimize, but this ensures correctness.
        if self._client:
             await self._client.aclose() # Ensure old connection is closed if recreating
             self._client = None

        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
            # NiFi often requires client ID for state changes, let's check if we need it here
            # Might need to parse initial response or call another endpoint if needed.

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            verify=self.tls_verify,
            headers=headers,
            timeout=30.0 # Keep timeout
        )
        return self._client

    async def authenticate(self):
        """Authenticates with NiFi and stores the token."""
        # Use a temporary client for the auth request itself, as it doesn't need the token header
        async with httpx.AsyncClient(base_url=self.base_url, verify=self.tls_verify) as auth_client:
            endpoint = "/access/token"
            try:
                logger.info(f"Authenticating with NiFi at {self.base_url}{endpoint}")
                response = await auth_client.post(
                    endpoint,
                    data={"username": self.username, "password": self.password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"} # Correct header for form data
                )
                response.raise_for_status()
                self._token = response.text # Store the token
                logger.info("Authentication successful.")

                # Force recreation of the main client with the token on next call to _get_client
                if self._client:
                    await self._client.aclose()
                self._client = None

            except httpx.HTTPStatusError as e:
                logger.error(f"Authentication failed: {e.response.status_code} - {e.response.text}")
                raise NiFiAuthenticationError(f"Authentication failed: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"An error occurred during authentication: {e}")
                raise NiFiAuthenticationError(f"An error occurred during authentication: {e}") from e
            except Exception as e:
                logger.error(f"An unexpected error occurred during authentication: {e}", exc_info=True)
                raise NiFiAuthenticationError(f"An unexpected error occurred during authentication: {e}")

    async def close(self):
        """Closes the underlying httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("NiFi client connection closed.")

    # --- Placeholder for other API methods ---
    async def list_process_groups(self, process_group_id: str = "-", action_id: str = "-",user_request_id: str = "-") -> list[dict]:
        """Lists all process groups in the NiFi instance."""
        local_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)
        if not self._token:
            local_logger.error("Authentication required before listing process groups.")
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/process-groups"
        try:
            local_logger.info(f"Fetching process groups from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = [x["id"] for x in response.json()["processGroups"]]
            local_logger.info(f"Found {len(data)} process groups.")
            return data
        except httpx.HTTPStatusError as e:
            local_logger.error(f"Failed to list process groups: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to list process groups: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            local_logger.error(f"Error listing process groups: {e}")
            raise ConnectionError(f"Error listing process groups: {e}") from e
        except Exception as e:
            local_logger.error(f"An unexpected error occurred listing process groups: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred listing process groups: {e}") from e
    # async def get_process_group_id(self, user_request_id: str = "-", action_id: str = "-") -> str:
    #     """Gets the ID of the process group."""
    #     local_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)
    #     if not self._token:
    #         local_logger.error("Authentication required before getting process group ID.")
    #         raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

    #     client = await self._get_client()
    #     endpoint = "/flow/process-groups/root"
    #     try:
    #         local_logger.info(f"Fetching process group ID from {self.base_url}{endpoint}")
    #         response = await client.get(endpoint)
    #         response.raise_for_status()
    #         data = response.json()
    #         process_group_id = data.get('id')
    #         if not process_group_id:
    #             local_logger.error(f"Process group ID not found in response structure: {data}") # Log structure on error
    #             raise ConnectionError("Could not extract process group ID from response.")
    #         local_logger.info(f"Retrieved process group ID: {process_group_id}")
    #         return process_group_id
    #     except httpx.HTTPStatusError as e:
    #         local_logger.error(f"Failed to get process group ID: {e.response.status_code} - {e.response.text}")
    #         raise ConnectionError(f"Failed to get process group ID: {e.response.status_code}") from e
    #     except (httpx.RequestError, ValueError) as e:
    #         local_logger.error(f"Error getting process group ID: {e}")
    #         raise ConnectionError(f"Error getting process group ID: {e}") from e
    #     except Exception as e:
    #         local_logger.error(f"An unexpected error occurred getting process group ID: {e}", exc_info=True)
    #         raise ConnectionError(f"An unexpected error occurred getting process group ID: {e}") from e
    async def get_root_process_group_id(self, user_request_id: str = "-", action_id: str = "-") -> str:
        """Gets the ID of the root process group."""
        local_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)
        if not self._token:
            local_logger.error("Authentication required before getting root process group ID.")
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = "/flow/process-groups/root"
        try:
            local_logger.info(f"Fetching root process group ID from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            # Check both top-level ID and nested ID within processGroupFlow
            root_id = data.get('id')
            if not root_id and 'processGroupFlow' in data and isinstance(data['processGroupFlow'], dict):
                root_id = data['processGroupFlow'].get('id')
                
            if not root_id:
                 local_logger.error(f"Root process group ID not found in response structure: {data}") # Log structure on error
                 raise ConnectionError("Could not extract root process group ID from response.")
            local_logger.info(f"Retrieved root process group ID: {root_id}")
            return root_id
        except httpx.HTTPStatusError as e:
            local_logger.error(f"Failed to get root process group ID: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to get root process group ID: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            local_logger.error(f"Error getting root process group ID: {e}")
            raise ConnectionError(f"Error getting root process group ID: {e}") from e
        except Exception as e:
            local_logger.error(f"An unexpected error occurred getting root process group ID: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting root process group ID: {e}") from e

    async def list_processors(self, process_group_id: str, user_request_id: str = "-", action_id: str = "-") -> list[dict]:
        """Lists processors within a specified process group."""
        local_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)
        
        if not self._token:
            local_logger.error("Authentication required before listing processors.")
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/processors"
        try:
            local_logger.info(f"Fetching processors for group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            # The response is typically a ProcessorsEntity which has a 'processors' key containing a list
            processors = data.get("processors", [])
            local_logger.info(f"Found {len(processors)} processors in group {process_group_id}.")
            return processors

        except httpx.HTTPStatusError as e:
            local_logger.error(f"Failed to list processors for group {process_group_id}: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to list processors: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            local_logger.error(f"Error listing processors for group {process_group_id}: {e}")
            raise ConnectionError(f"Error listing processors: {e}") from e
        except Exception as e:
            local_logger.error(f"An unexpected error occurred listing processors: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred listing processors: {e}") from e

    async def create_processor(
        self,
        process_group_id: str,
        processor_type: str,
        name: str,
        position: Dict[str, float],
        config: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Creates a new processor in the specified process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/processors"

        # Construct the request body (ProcessorEntity)
        request_body = {
            "revision": {
                "clientId": self._client_id,
                "version": 0
            },
            "component": {
                "type": processor_type,
                "name": name,
                "position": position,
            }
        }
        # Add config if provided (simplified - real config might need more structure)
        if config:
            request_body["component"]["config"] = {"properties": config}

        try:
            logger.info(f"Creating processor '{name}' ({processor_type}) in group {process_group_id} at {position}")
            response = await client.post(endpoint, json=request_body)
            response.raise_for_status() # Checks for 4xx/5xx errors
            created_processor_data = response.json()
            logger.info(f"Successfully created processor '{name}' with ID: {created_processor_data.get('id')}")
            return created_processor_data # Return the full response body

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create processor '{name}': {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to create processor: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error creating processor '{name}': {e}")
            raise ConnectionError(f"Error creating processor: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred creating processor '{name}': {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred creating processor: {e}") from e

    async def create_connection(
        self,
        process_group_id: str,
        source_id: str,
        target_id: str,
        relationships: list[str],
        source_type: str = "PROCESSOR", # Usually PROCESSOR
        target_type: str = "PROCESSOR", # Usually PROCESSOR
        name: Optional[str] = None
    ) -> dict:
        """Creates a connection between two components in a process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/connections"

        # Construct the request body (ConnectionEntity)
        request_body = {
            "revision": {
                "clientId": self._client_id,
                "version": 0
            },
            "component": {
                "name": name or "", # Optional connection name
                "source": {
                    "id": source_id,
                    "groupId": process_group_id,
                    "type": source_type.upper()
                },
                "destination": {
                    "id": target_id,
                    "groupId": process_group_id,
                    "type": target_type.upper()
                },
                "selectedRelationships": relationships
                # Can add other config like flowfileExpiration, backPressureObjectThreshold etc. if needed
            }
        }

        try:
            logger.info(f"Creating connection from {source_id} ({relationships}) to {target_id} in group {process_group_id}")
            response = await client.post(endpoint, json=request_body)
            response.raise_for_status()
            created_connection_data = response.json()
            logger.info(f"Successfully created connection with ID: {created_connection_data.get('id')}")
            return created_connection_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create connection: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to create connection: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error creating connection: {e}")
            raise ConnectionError(f"Error creating connection: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred creating connection: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred creating connection: {e}") from e

    async def get_processor_details(self, processor_id: str) -> dict:
        """Fetches the details and configuration of a specific processor."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/processors/{processor_id}"
        try:
            logger.info(f"Fetching details for processor {processor_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            processor_details = response.json()
            logger.info(f"Successfully fetched details for processor {processor_id}")
            return processor_details

        except httpx.HTTPStatusError as e:
            # Handle 404 Not Found specifically
            if e.response.status_code == 404:
                logger.warning(f"Processor with ID {processor_id} not found.")
                raise ValueError(f"Processor with ID {processor_id} not found.") from e # Raise ValueError for not found
            else:
                logger.error(f"Failed to get details for processor {processor_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get processor details: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting details for processor {processor_id}: {e}")
            raise ConnectionError(f"Error getting processor details: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting processor details for {processor_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting processor details: {e}") from e

    async def delete_processor(self, processor_id: str, version: int) -> bool:
        """Deletes a processor given its ID and current revision version."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        # The version must be passed as a query parameter, along with the client ID
        endpoint = f"/processors/{processor_id}?version={version}&clientId={self._client_id}"

        try:
            logger.info(f"Attempting to delete processor {processor_id} (version {version}) using {self.base_url}{endpoint}")
            response = await client.delete(endpoint)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx

            # Check if deletion was successful (usually returns 200 OK with the entity deleted)
            if response.status_code == 200:
                 logger.info(f"Successfully deleted processor {processor_id}.")
                 # We could return the response JSON, but a boolean might suffice
                 return True
            else:
                 # This case might not be reachable if raise_for_status is effective
                 logger.warning(f"Processor deletion for {processor_id} returned status {response.status_code}, but expected 200.")
                 return False

        except httpx.HTTPStatusError as e:
            # Handle specific errors like 404 (Not Found) or 409 (Conflict - likely wrong version)
            if e.response.status_code == 404:
                 logger.warning(f"Processor {processor_id} not found for deletion.")
                 # Consider if this should be True (it's already gone) or False/raise error
                 return False # Treat as failure to delete *now*
            elif e.response.status_code == 409:
                 logger.error(f"Conflict deleting processor {processor_id}. Check revision version ({version}). Response: {e.response.text}")
                 raise ValueError(f"Conflict deleting processor {processor_id}. Ensure correct version ({version}) is used.") from e
            else:
                 logger.error(f"Failed to delete processor {processor_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete processor: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting processor {processor_id}: {e}")
            raise ConnectionError(f"Error deleting processor: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting processor {processor_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting processor: {e}") from e

    async def get_connection(self, connection_id: str) -> dict:
        """Fetches the details of a specific connection."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/connections/{connection_id}"
        try:
            logger.info(f"Fetching details for connection {connection_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            connection_details = response.json()
            logger.info(f"Successfully fetched details for connection {connection_id}")
            return connection_details

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Connection with ID {connection_id} not found.")
                raise ValueError(f"Connection with ID {connection_id} not found.") from e
            else:
                logger.error(f"Failed to get details for connection {connection_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get connection details: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting details for connection {connection_id}: {e}")
            raise ConnectionError(f"Error getting connection details: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting connection details for {connection_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting connection details: {e}") from e

    async def list_connections(self, process_group_id: str, user_request_id: str = "-", action_id: str = "-") -> list[dict]:
        """Lists connections within a specified process group."""
        local_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)
        if not self._token:
            local_logger.error("Authentication required before listing connections.")
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/connections"
        try:
            local_logger.info(f"Fetching connections for group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            connections = data.get("connections", [])
            local_logger.info(f"Found {len(connections)} connections in group {process_group_id}.")
            return connections

        except httpx.HTTPStatusError as e:
            local_logger.error(f"Failed to list connections for group {process_group_id}: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to list connections: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            local_logger.error(f"Error listing connections for group {process_group_id}: {e}")
            raise ConnectionError(f"Error listing connections: {e}") from e
        except Exception as e:
            local_logger.error(f"An unexpected error occurred listing connections: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred listing connections: {e}") from e

    async def delete_connection(self, connection_id: str, version_number: int) -> bool:
        """Deletes a connection given its ID and current revision version number."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        # Use the integer version number in the query parameter
        endpoint = f"/connections/{connection_id}?version={version_number}&clientId={self._client_id}"

        try:
            logger.info(f"Attempting to delete connection {connection_id} (version {version_number}) using {self.base_url}{endpoint}")
            response = await client.delete(endpoint)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx

            if response.status_code == 200:
                 logger.info(f"Successfully deleted connection {connection_id}.")
                 return True
            else:
                 logger.warning(f"Connection deletion for {connection_id} returned status {response.status_code}, but expected 200.")
                 return False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logger.warning(f"Connection {connection_id} not found for deletion.")
                 return False
            elif e.response.status_code == 409:
                 logger.error(f"Conflict deleting connection {connection_id}. Check revision version ({version_number}). Response: {e.response.text}")
                 raise ValueError(f"Conflict deleting connection {connection_id}. Ensure correct version ({version_number}) is used.") from e
            else:
                 logger.error(f"Failed to delete connection {connection_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete connection: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting connection {connection_id}: {e}")
            raise ConnectionError(f"Error deleting connection: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting connection {connection_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting connection: {e}") from e

    async def update_connection(self, connection_id: str, update_payload: Dict[str, Any]) -> Dict:
        """Updates a specific connection using the provided payload (including revision and component)."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/connections/{connection_id}"
        revision = update_payload.get("revision", {})
        version = revision.get("version", "UNKNOWN")

        try:
            logger.info(f"Updating connection {connection_id} (Version: {version}).")
            # Log selected relationships being set
            selected_relationships = update_payload.get("component", {}).get("selectedRelationships")
            if selected_relationships is not None:
                logger.debug(f"Setting selectedRelationships to: {selected_relationships}")
                
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json()
            logger.info(f"Successfully updated connection {connection_id}. New revision: {updated_entity.get('revision', {}).get('version')}")
            return updated_entity

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Connection {connection_id} not found for update.")
                raise ValueError(f"Connection with ID {connection_id} not found.") from e
            elif e.response.status_code == 409:
                logger.error(f"Conflict updating connection {connection_id}. Revision ({version}) likely stale. Response: {e.response.text}")
                raise ValueError(f"Conflict updating connection {connection_id}. Revision mismatch.") from e
            else:
                logger.error(f"Failed to update connection {connection_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to update connection: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error updating connection {connection_id}: {e}")
            raise ConnectionError(f"Error updating connection: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred updating connection {connection_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred updating connection: {e}") from e

    async def update_processor_config(
        self,
        processor_id: str,
        update_type: str,
        update_data: Union[Dict[str, Any], List[str]]
    ) -> dict:
        """Updates specific parts of a processor's component configuration (properties or auto-terminated relationships)."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        # Validate update_type
        valid_update_types = ["properties", "auto-terminatedrelationships"]
        if update_type not in valid_update_types:
            raise ValueError(f"Invalid update_type '{update_type}'. Must be one of {valid_update_types}")

        # 1. Get current processor entity to obtain the latest revision
        logger.info(f"Fetching current details for processor {processor_id} before update.")
        try:
            current_entity = await self.get_processor_details(processor_id)
            current_revision = current_entity["revision"]
            current_component = current_entity["component"]
        except (ValueError, ConnectionError) as e:
            logger.error(f"Failed to fetch processor {processor_id} for update: {e}")
            raise

        # 2. Prepare the update payload
        # Start with essential component details
        update_component = {
            "id": current_component["id"],
            # Keep existing name, position etc. unless explicitly changed later
            "name": current_component.get("name"),
            "position": current_component.get("position"),
            # Copy existing config first, then overwrite specific part
            "config": current_component.get("config", {}).copy(),
        }

        # Apply the specific update based on update_type
        log_message_part = "unknown configuration part"
        if update_type == "properties":
            if not isinstance(update_data, dict):
                raise TypeError("update_data must be a dictionary when update_type is 'properties'.")
            # Ensure config key exists
            if "config" not in update_component:
                 update_component["config"] = {}
            update_component["config"]["properties"] = update_data
            log_message_part = f"properties: {update_data}"

        elif update_type == "auto-terminatedrelationships":
            # Expect a list of strings (relationship names)
            if not isinstance(update_data, list) or not all(isinstance(item, str) for item in update_data):
                 raise TypeError("update_data must be a list of strings (relationship names) when update_type is 'auto-terminatedrelationships'.")
            
            # Ensure config key exists
            if "config" not in update_component:
                 update_component["config"] = {}
                 
            # Assign to component.config.autoTerminatedRelationships based on UI capture
            update_component["config"]["autoTerminatedRelationships"] = update_data
            log_message_part = f"config.autoTerminatedRelationships: {update_data}"

        # Construct final payload
        update_payload = {
            "revision": current_revision,
            "component": update_component
        }

        # 3. Make the PUT request
        client = await self._get_client()
        endpoint = f"/processors/{processor_id}"
        try:
            logger.info(f"Updating processor {processor_id} (Version: {current_revision.get('version')}). Updating {log_message_part}")
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json()
            logger.info(f"Successfully updated processor {processor_id}. New revision: {updated_entity.get('revision', {}).get('version')}")
            return updated_entity

        except httpx.HTTPStatusError as e:
            # Handle 409 Conflict (likely stale revision)
            if e.response.status_code == 409:
                logger.error(f"Conflict updating processor {processor_id}. Revision ({current_revision.get('version')}) likely stale. Response: {e.response.text}")
                raise ValueError(f"Conflict updating processor {processor_id}. Revision mismatch.") from e
            else:
                logger.error(f"Failed to update processor {processor_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to update processor: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error updating processor {processor_id}: {e}")
            raise ConnectionError(f"Error updating processor: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred updating processor {processor_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred updating processor: {e}") from e

    async def update_processor_state(self, processor_id: str, state: str) -> dict:
        """Starts or stops a specific processor."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        normalized_state = state.upper()
        if normalized_state not in ["RUNNING", "STOPPED"]:
            raise ValueError("Invalid state specified. Must be 'RUNNING' or 'STOPPED'.")

        # 1. Get current processor entity to obtain the latest revision
        # We need the revision even just to change the state.
        logger.info(f"Fetching current revision for processor {processor_id} before changing state to {normalized_state}.")
        try:
            # Use get_processor_details as it already handles fetching the entity
            current_entity = await self.get_processor_details(processor_id)
            current_revision = current_entity["revision"]
        except (ValueError, ConnectionError) as e:
            logger.error(f"Failed to fetch processor {processor_id} to update state: {e}")
            raise

        # 2. Prepare the update payload for the run-status endpoint
        update_payload = {
            "revision": current_revision,
            "state": normalized_state,
            "disconnectedNodeAcknowledged": False # Usually required, defaults to false
        }

        # 3. Make the PUT request to the run-status endpoint
        client = await self._get_client()
        endpoint = f"/processors/{processor_id}/run-status"
        try:
            logger.info(f"Setting processor {processor_id} state to {normalized_state} (Version: {current_revision.get('version')}).")
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json() # The response contains the processor entity with updated status
            logger.info(f"Successfully set processor {processor_id} state to {updated_entity.get('component',{}).get('state', 'UNKNOWN')}. New revision: {updated_entity.get('revision', {}).get('version')}")
            return updated_entity

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.error(f"Conflict changing state for processor {processor_id}. Revision ({current_revision.get('version')}) likely stale. Response: {e.response.text}")
                raise ValueError(f"Conflict changing processor state for {processor_id}. Revision mismatch.") from e
            else:
                logger.error(f"Failed to change state for processor {processor_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to change processor state: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error changing state for processor {processor_id}: {e}")
            raise ConnectionError(f"Error changing processor state: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred changing state for processor {processor_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred changing processor state: {e}") from e

    async def get_process_group_status_snapshot(self, process_group_id: str) -> dict:
        """Fetches the status snapshot for a specific process group, including component states and queue sizes.

        Args:
            process_group_id: The ID of the target process group.

        Returns:
            A dictionary containing the process group status snapshot, typically under the 'processGroupStatus' key.
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/flow/process-groups/{process_group_id}/status"
        try:
            logger.info(f"Fetching status snapshot for process group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            status_data = response.json()
            # The core data is usually within processGroupStatus
            logger.info(f"Successfully fetched status snapshot for process group {process_group_id}")
            return status_data.get("processGroupStatus", {}) # Return the main status part

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Process group {process_group_id} not found when fetching status snapshot.")
                raise ValueError(f"Process group with ID {process_group_id} not found.") from e
            else:
                logger.error(f"Failed to get status snapshot for process group {process_group_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get process group status snapshot: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting status snapshot for process group {process_group_id}: {e}")
            raise ConnectionError(f"Error getting process group status snapshot: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting status snapshot for {process_group_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting process group status snapshot: {e}") from e

    async def get_bulletin_board(self, group_id: Optional[str] = None, source_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Fetches bulletins from the NiFi bulletin board, optionally filtered.

        Args:
            group_id: The ID of the process group to filter bulletins by.
            source_id: The ID of the source component to filter bulletins by.
            limit: The maximum number of bulletins to return.

        Returns:
            A list of bulletin dictionaries.
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = "/flow/bulletin-board"
        params = {"limit": limit}
        if group_id:
            params["groupId"] = group_id
        if source_id:
            params["sourceId"] = source_id

        try:
            logger.info(f"Fetching bulletins from {self.base_url}{endpoint} with params: {params}")
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            bulletins = response.json().get("bulletins", [])
            logger.info(f"Successfully fetched {len(bulletins)} bulletins.")
            return bulletins

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get bulletins: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to get bulletins: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting bulletins: {e}")
            raise ConnectionError(f"Error getting bulletins: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting bulletins: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting bulletins: {e}") from e

    async def get_parameter_context(self, process_group_id: str, user_request_id: str = "-", action_id: str = "-") -> list:
        """Retrieves the parameter context associated with a process group."""
        local_logger = logger.bind(user_request_id=user_request_id, action_id=action_id)
        local_logger.info(f"Fetching process group {process_group_id} to get parameter context")
        try:
            # First, get the process group details to find the parameter context ID
            pg_details = await self.get_process_group_details(process_group_id, user_request_id=user_request_id, action_id=action_id) # Pass IDs down
            param_context_id = pg_details.get("component", {}).get("parameterContext", {}).get("id")

            if not param_context_id:
                local_logger.info(f"No parameter context found for process group {process_group_id}")
                return []

            # Now fetch the parameter context details using its ID
            client = await self._get_client()
            endpoint = f"/parameter-contexts/{param_context_id}?includeInheritedParameters=true"
            local_logger.info(f"Fetching parameter context {param_context_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            parameters = data.get("component", {}).get("parameters", [])
            local_logger.info(f"Found {len(parameters)} parameters in context {param_context_id} for group {process_group_id}.")
            # Extract only parameter name and value if needed, or return full structure
            # simplified_params = [{p['parameter']['name']: p['parameter'].get('value')} for p in parameters]
            return parameters # Return full parameter entity list

        except NiFiAuthenticationError as e:
             local_logger.error(f"Authentication error fetching parameter context for PG {process_group_id}: {e}", exc_info=False)
             raise ToolError(f"Authentication error accessing parameter context for PG {process_group_id}.") from e
        except httpx.HTTPStatusError as e:
            local_logger.error(f"Failed to get parameter context for PG {process_group_id}: {e.response.status_code} - {e.response.text}")
            raise ToolError(f"Failed to get parameter context: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError, ConnectionError) as e:
            local_logger.error(f"Error getting parameter context for PG {process_group_id}: {e}")
            raise ToolError(f"Error getting parameter context: {e}") from e
        except Exception as e:
            local_logger.error(f"An unexpected error occurred getting parameter context for PG {process_group_id}: {e}", exc_info=True)
            raise ToolError(f"An unexpected error occurred getting parameter context: {e}") from e

    async def get_input_ports(self, process_group_id: str) -> list[dict]:
        """Lists input ports within a specified process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/input-ports"
        try:
            logger.info(f"Fetching input ports for group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            # Response is InputPortsEntity with 'inputPorts' key
            ports = data.get("inputPorts", [])
            logger.info(f"Found {len(ports)} input ports in group {process_group_id}.")
            return ports
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to list input ports for group {process_group_id}: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to list input ports: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error listing input ports for group {process_group_id}: {e}")
            raise ConnectionError(f"Error listing input ports: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred listing input ports: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred listing input ports: {e}") from e

    async def get_output_ports(self, process_group_id: str) -> list[dict]:
        """Lists output ports within a specified process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/output-ports"
        try:
            logger.info(f"Fetching output ports for group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            # Response is OutputPortsEntity with 'outputPorts' key
            ports = data.get("outputPorts", [])
            logger.info(f"Found {len(ports)} output ports in group {process_group_id}.")
            return ports
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to list output ports for group {process_group_id}: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to list output ports: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error listing output ports for group {process_group_id}: {e}")
            raise ConnectionError(f"Error listing output ports: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred listing output ports: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred listing output ports: {e}") from e

    async def get_process_groups(self, process_group_id: str) -> list[dict]:
        """Lists immediate child process groups within a specified process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}/process-groups"
        try:
            logger.info(f"Fetching child process groups for group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            # Response is ProcessGroupsEntity with 'processGroups' key
            groups = data.get("processGroups", [])
            logger.info(f"Found {len(groups)} child process groups in group {process_group_id}.")
            return [{'id': x['id'], 'name': x['component']['name']} for x in groups]
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to list process groups for group {process_group_id}: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to list process groups: {e.response.status_code}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error listing process groups for group {process_group_id}: {e}")
            raise ConnectionError(f"Error listing process groups: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred listing process groups: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred listing process groups: {e}") from e
    @lru_cache
    async def is_descendant(self,process_group_id: str, parent_process_group_id:str)->bool:
        """Recursively gets details of process group to check if a process group is a descendant of another."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        try:
            if not process_group_id or not parent_process_group_id:
                return False
            if process_group_id == parent_process_group_id:
                return True
            logger.info(f"Checking if {process_group_id} is a descendant of {parent_process_group_id}")
            data = await self.get_process_group_details(process_group_id)
            # Check the parent process group ID and check recursively
            parent_pg_id = data.get('component', {}).get('parentGroupId')
            if not parent_pg_id:
                return False
            return await self.is_descendant(parent_pg_id, parent_process_group_id)

        except Exception as e:
            logger.error(f"An unexpected error occurred checking descendant status: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred checking descendant status: {e}") from e
    async def get_process_group_details(self, process_group_id: str) -> dict:
        """Fetches the flow details for a specific process group, often including counts."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{process_group_id}"
        try:
            logger.info(f"Fetching details for process group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            flow_details = response.json()
            logger.info(f"Successfully fetched flow details for process group {process_group_id}")
            return flow_details
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Process group flow with ID {process_group_id} not found.")
                raise ValueError(f"Process group flow with ID {process_group_id} not found.") from e
            else:
                logger.error(f"Failed to get flow details for process group {process_group_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get process group flow details: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting flow details for process group {process_group_id}: {e}")
            raise ConnectionError(f"Error getting process group flow details: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting process group flow details for {process_group_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting process group flow details: {e}") from e
    async def get_process_group_flow(self, process_group_id: str) -> dict:
        """Fetches the flow details for a specific process group, often including counts."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/flow/process-groups/{process_group_id}"
        try:
            logger.info(f"Fetching flow details for process group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            flow_details = response.json()
            logger.info(f"Successfully fetched flow details for process group {process_group_id}")
            return flow_details

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Process group flow with ID {process_group_id} not found.")
                raise ValueError(f"Process group flow with ID {process_group_id} not found.") from e
            else:
                logger.error(f"Failed to get flow details for process group {process_group_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get process group flow details: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting flow details for process group {process_group_id}: {e}")
            raise ConnectionError(f"Error getting process group flow details: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting process group flow details for {process_group_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting process group flow details: {e}") from e

    async def get_input_port_details(self, port_id: str) -> dict:
        """Fetches the details of a specific input port."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/input-ports/{port_id}"
        try:
            logger.info(f"Fetching details for input port {port_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            port_details = response.json()
            logger.info(f"Successfully fetched details for input port {port_id}")
            return port_details

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Input port with ID {port_id} not found.")
                raise ValueError(f"Input port with ID {port_id} not found.") from e
            else:
                logger.error(f"Failed to get details for input port {port_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get input port details: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting details for input port {port_id}: {e}")
            raise ConnectionError(f"Error getting input port details: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting input port details for {port_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting input port details: {e}") from e

    async def get_output_port_details(self, port_id: str) -> dict:
        """Fetches the details of a specific output port."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/output-ports/{port_id}"
        try:
            logger.info(f"Fetching details for output port {port_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            port_details = response.json()
            logger.info(f"Successfully fetched details for output port {port_id}")
            return port_details

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Output port with ID {port_id} not found.")
                raise ValueError(f"Output port with ID {port_id} not found.") from e
            else:
                logger.error(f"Failed to get details for output port {port_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get output port details: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting details for output port {port_id}: {e}")
            raise ConnectionError(f"Error getting output port details: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting output port details for {port_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting output port details: {e}") from e

    async def delete_input_port(self, port_id: str, version: int) -> bool:
        """Deletes an input port given its ID and current revision version."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/input-ports/{port_id}?version={version}&clientId={self._client_id}"

        try:
            logger.info(f"Attempting to delete input port {port_id} (version {version}) using {self.base_url}{endpoint}")
            response = await client.delete(endpoint)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx

            if response.status_code == 200:
                 logger.info(f"Successfully deleted input port {port_id}.")
                 return True
            else:
                 logger.warning(f"Input port deletion for {port_id} returned status {response.status_code}, expected 200.")
                 return False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logger.warning(f"Input port {port_id} not found for deletion.")
                 return False
            elif e.response.status_code == 409:
                 logger.error(f"Conflict deleting input port {port_id}. Check revision version ({version}) or ensure port is stopped/disconnected. Response: {e.response.text}")
                 raise ValueError(f"Conflict deleting input port {port_id}. Ensure correct version ({version}) and state.") from e
            else:
                 logger.error(f"Failed to delete input port {port_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete input port: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting input port {port_id}: {e}")
            raise ConnectionError(f"Error deleting input port: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting input port {port_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting input port: {e}") from e

    async def delete_output_port(self, port_id: str, version: int) -> bool:
        """Deletes an output port given its ID and current revision version."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/output-ports/{port_id}?version={version}&clientId={self._client_id}"

        try:
            logger.info(f"Attempting to delete output port {port_id} (version {version}) using {self.base_url}{endpoint}")
            response = await client.delete(endpoint)
            response.raise_for_status()

            if response.status_code == 200:
                 logger.info(f"Successfully deleted output port {port_id}.")
                 return True
            else:
                 logger.warning(f"Output port deletion for {port_id} returned status {response.status_code}, expected 200.")
                 return False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logger.warning(f"Output port {port_id} not found for deletion.")
                 return False
            elif e.response.status_code == 409:
                 logger.error(f"Conflict deleting output port {port_id}. Check revision version ({version}) or ensure port is stopped/disconnected. Response: {e.response.text}")
                 raise ValueError(f"Conflict deleting output port {port_id}. Ensure correct version ({version}) and state.") from e
            else:
                 logger.error(f"Failed to delete output port {port_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete output port: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting output port {port_id}: {e}")
            raise ConnectionError(f"Error deleting output port: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting output port {port_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting output port: {e}") from e

    async def delete_process_group(self, pg_id: str, version: int) -> bool:
        """Deletes a process group given its ID and current revision version. Fails if not empty."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        # Recursive deletion isn't standard; this deletes only if empty
        endpoint = f"/process-groups/{pg_id}?version={version}&clientId={self._client_id}"

        try:
            logger.info(f"Attempting to delete process group {pg_id} (version {version}) using {self.base_url}{endpoint}")
            response = await client.delete(endpoint)
            response.raise_for_status()

            if response.status_code == 200:
                 logger.info(f"Successfully deleted process group {pg_id}.")
                 return True
            else:
                 logger.warning(f"Process group deletion for {pg_id} returned status {response.status_code}, expected 200.")
                 return False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logger.warning(f"Process group {pg_id} not found for deletion.")
                 return False
            elif e.response.status_code == 409:
                 # This is common if the group is not empty or stopped
                 logger.error(f"Conflict deleting process group {pg_id}. Check revision version ({version}) or ensure group is empty and stopped. Response: {e.response.text}")
                 raise ValueError(f"Conflict deleting process group {pg_id}. Ensure correct version ({version}) and that it is empty and stopped.") from e
            else:
                 logger.error(f"Failed to delete process group {pg_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete process group: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting process group {pg_id}: {e}")
            raise ConnectionError(f"Error deleting process group: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting process group {pg_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting process group: {e}") from e

    async def update_input_port_state(self, port_id: str, state: str) -> dict:
        """Starts or stops a specific input port."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        normalized_state = state.upper()
        if normalized_state not in ["RUNNING", "STOPPED", "DISABLED"]:
            raise ValueError("Invalid state specified. Must be 'RUNNING' or 'STOPPED' or 'DISABLED'.")

        # 1. Get current details for revision
        logger.info(f"Fetching current revision for input port {port_id} before changing state to {normalized_state}.")
        try:
            current_entity = await self.get_input_port_details(port_id)
            current_revision = current_entity["revision"]
        except (ValueError, ConnectionError) as e:
            logger.error(f"Failed to fetch input port {port_id} to update state: {e}")
            raise

        # 2. Prepare payload
        update_payload = {
            "revision": current_revision,
            "state": normalized_state,
            "disconnectedNodeAcknowledged": False
        }

        # 3. Make PUT request
        client = await self._get_client()
        endpoint = f"/input-ports/{port_id}/run-status"
        try:
            logger.info(f"Setting input port {port_id} state to {normalized_state} (Version: {current_revision.get('version')}).")
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json()
            logger.info(f"Successfully set input port {port_id} state to {updated_entity.get('component',{}).get('state', 'UNKNOWN')}.")
            return updated_entity
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.error(f"Conflict changing state for input port {port_id}. Revision ({current_revision.get('version')}) likely stale or state invalid. Response: {e.response.text}")
                raise ValueError(f"Conflict changing input port state for {port_id}. Revision mismatch or invalid state.") from e
            else:
                logger.error(f"Failed to change state for input port {port_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to change input port state: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error changing state for input port {port_id}: {e}")
            raise ConnectionError(f"Error changing input port state: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred changing state for input port {port_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred changing input port state: {e}") from e

    async def update_output_port_state(self, port_id: str, state: str) -> dict:
        """Starts or stops a specific output port."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        normalized_state = state.upper()
        if normalized_state not in ["RUNNING", "STOPPED", "DISABLED"]:
            raise ValueError("Invalid state specified. Must be 'RUNNING' or 'STOPPED' or 'DISABLED'.")

        # 1. Get current details for revision
        logger.info(f"Fetching current revision for output port {port_id} before changing state to {normalized_state}.")
        try:
            current_entity = await self.get_output_port_details(port_id)
            current_revision = current_entity["revision"]
        except (ValueError, ConnectionError) as e:
            logger.error(f"Failed to fetch output port {port_id} to update state: {e}")
            raise

        # 2. Prepare payload
        update_payload = {
            "revision": current_revision,
            "state": normalized_state,
            "disconnectedNodeAcknowledged": False
        }

        # 3. Make PUT request
        client = await self._get_client()
        endpoint = f"/output-ports/{port_id}/run-status"
        try:
            logger.info(f"Setting output port {port_id} state to {normalized_state} (Version: {current_revision.get('version')}).")
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json()
            logger.info(f"Successfully set output port {port_id} state to {updated_entity.get('component',{}).get('state', 'UNKNOWN')}.")
            return updated_entity
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.error(f"Conflict changing state for output port {port_id}. Revision ({current_revision.get('version')}) likely stale or state invalid. Response: {e.response.text}")
                raise ValueError(f"Conflict changing output port state for {port_id}. Revision mismatch or invalid state.") from e
            else:
                logger.error(f"Failed to change state for output port {port_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to change output port state: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error changing state for output port {port_id}: {e}")
            raise ConnectionError(f"Error changing output port state: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred changing state for output port {port_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred changing output port state: {e}") from e

    async def create_input_port(self, pg_id: str, name: str, position: Dict[str, float]) -> dict:
        """Creates a new input port in the specified process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{pg_id}/input-ports"

        request_body = {
            "revision": {"clientId": self._client_id, "version": 0},
            "component": {
                "name": name,
                "position": position,
                # Add other defaults if needed, e.g., comments: "", state: "STOPPED"
            }
        }

        try:
            logger.info(f"Creating input port '{name}' in group {pg_id} at {position}")
            response = await client.post(endpoint, json=request_body)
            response.raise_for_status()
            created_port_data = response.json()
            logger.info(f"Successfully created input port '{name}' with ID: {created_port_data.get('id')}")
            return created_port_data
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create input port '{name}': {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to create input port: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error creating input port '{name}': {e}")
            raise ConnectionError(f"Error creating input port: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred creating input port '{name}': {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred creating input port: {e}") from e

    async def create_output_port(self, pg_id: str, name: str, position: Dict[str, float]) -> dict:
        """Creates a new output port in the specified process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{pg_id}/output-ports"

        request_body = {
            "revision": {"clientId": self._client_id, "version": 0},
            "component": {
                "name": name,
                "position": position,
            }
        }

        try:
            logger.info(f"Creating output port '{name}' in group {pg_id} at {position}")
            response = await client.post(endpoint, json=request_body)
            response.raise_for_status()
            created_port_data = response.json()
            logger.info(f"Successfully created output port '{name}' with ID: {created_port_data.get('id')}")
            return created_port_data
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create output port '{name}': {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to create output port: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error creating output port '{name}': {e}")
            raise ConnectionError(f"Error creating output port: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred creating output port '{name}': {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred creating output port: {e}") from e

    async def create_process_group(self, parent_pg_id: str, name: str, position: Dict[str, float]) -> dict:
        """Creates a new process group within the specified parent process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/process-groups/{parent_pg_id}/process-groups"

        request_body = {
            "revision": {"clientId": self._client_id, "version": 0},
            "component": {
                "name": name,
                "position": position,
                # Add other defaults if needed, e.g., comments: ""
            }
        }

        try:
            logger.info(f"Creating process group '{name}' in parent group {parent_pg_id} at {position}")
            response = await client.post(endpoint, json=request_body)
            response.raise_for_status()
            created_pg_data = response.json()
            logger.info(f"Successfully created process group '{name}' with ID: {created_pg_data.get('id')}")
            return created_pg_data
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create process group '{name}': {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to create process group: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error creating process group '{name}': {e}")
            raise ConnectionError(f"Error creating process group: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred creating process group '{name}': {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred creating process group: {e}") from e

    async def get_processor_types(self) -> List[Dict]:
        """Fetches the list of available processor types from the NiFi instance."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = "/flow/processor-types"

        try:
            logger.info(f"Fetching available processor types from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
            # The response is ProcessorTypesEntity, containing 'processorTypes' list
            processor_types = data.get("processorTypes", [])
            logger.info(f"Successfully fetched {len(processor_types)} available processor types.")
            return processor_types

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get processor types: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to get processor types: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting processor types: {e}")
            raise ConnectionError(f"Error getting processor types: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting processor types: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting processor types: {e}") from e

    async def search_flow(self, query: str) -> Dict:
        """Performs a global search across the NiFi flow using the provided query string."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = "/flow/search-results"
        params = {"q": query}

        try:
            logger.info(f"Performing global flow search with query '{query}' using {self.base_url}{endpoint}")
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            search_results = response.json()
            logger.info(f"Successfully performed global flow search for query '{query}'.")
            # The response structure usually includes a top-level key like 'searchResultsDTO'
            # Example: { "searchResultsDTO": { "processorResults": [...], ... } }
            return search_results

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to perform flow search for query '{query}': {e.response.status_code} - {e.response.text}")
            # Don't raise ValueError for 404, search simply might not find anything or endpoint might differ
            raise ConnectionError(f"Failed to perform flow search: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e: # Include ValueError for potential JSON parsing issues
            logger.error(f"Error performing flow search for query '{query}': {e}")
            raise ConnectionError(f"Error performing flow search: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred performing flow search for query '{query}': {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred performing flow search: {e}") from e

    async def update_process_group_state(self, pg_id: str, state: str) -> dict:
        """Starts or stops all eligible components within a specific process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        normalized_state = state.upper()
        if normalized_state not in ["RUNNING", "STOPPED"]:
            raise ValueError("Invalid state specified. Must be 'RUNNING' or 'STOPPED'.")

        client = await self._get_client()
        endpoint = f"/flow/process-groups/{pg_id}"

        # The payload is simple for the bulk operation
        update_payload = {
            "id": pg_id,
            "state": normalized_state,
            # No revision needed for this bulk endpoint
        }

        try:
            logger.info(f"Setting state of all components in process group {pg_id} to {normalized_state} via {self.base_url}{endpoint}")
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json() # Response contains PG entity with potentially updated component counts/states
            logger.info(f"Successfully initiated state change for process group {pg_id} to {normalized_state}.")
            # Note: This action is asynchronous on the NiFi side. The response indicates submission success.
            # The actual state of individual components might take time to update.
            return updated_entity

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Process group {pg_id} not found for state update.")
                raise ValueError(f"Process group with ID {pg_id} not found.") from e
            elif e.response.status_code == 409:
                 # 409 could mean various things here, maybe permissions or invalid state transition request
                 logger.error(f"Conflict updating state for process group {pg_id}. Response: {e.response.text}")
                 raise ValueError(f"Conflict updating state for process group {pg_id}: {e.response.text}") from e
            else:
                logger.error(f"Failed to update state for process group {pg_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to update process group state: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error updating state for process group {pg_id}: {e}")
            raise ConnectionError(f"Error updating process group state: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred updating state for process group {pg_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred updating process group state: {e}") from e

    async def get_process_group_status_snapshot(self, process_group_id: str) -> dict:
        """Fetches the status snapshot for a specific process group, including component states and queue sizes.

        Args:
            process_group_id: The ID of the target process group.

        Returns:
            A dictionary containing the process group status snapshot, typically under the 'processGroupStatus' key.
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/flow/process-groups/{process_group_id}/status"
        try:
            logger.info(f"Fetching status snapshot for process group {process_group_id} from {self.base_url}{endpoint}")
            response = await client.get(endpoint)
            response.raise_for_status()
            status_data = response.json()
            # The core data is usually within processGroupStatus
            logger.info(f"Successfully fetched status snapshot for process group {process_group_id}")
            return status_data.get("processGroupStatus", {}) # Return the main status part

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Process group {process_group_id} not found when fetching status snapshot.")
                raise ValueError(f"Process group with ID {process_group_id} not found.") from e
            else:
                logger.error(f"Failed to get status snapshot for process group {process_group_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get process group status snapshot: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting status snapshot for process group {process_group_id}: {e}")
            raise ConnectionError(f"Error getting process group status snapshot: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting status snapshot for {process_group_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting process group status snapshot: {e}") from e

    async def get_bulletin_board(self, group_id: Optional[str] = None, source_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Fetches bulletins from the NiFi bulletin board, optionally filtered.

        Args:
            group_id: Optional process group ID to filter bulletins by.
            source_id: Optional component ID (processor, port, etc.) to filter bulletins by.
            limit: Maximum number of bulletins to return.

        Returns:
            A list of bulletin dictionaries.
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = "/flow/bulletin-board"
        params = {"limit": limit}
        log_filters = []
        if group_id:
            params["groupId"] = group_id
            log_filters.append(f"group_id={group_id}")
        if source_id:
            params["sourceId"] = source_id
            log_filters.append(f"source_id={source_id}")

        filter_str = " and ".join(log_filters) if log_filters else "no filters"

        try:
            logger.info(f"Fetching bulletins from {self.base_url}{endpoint} with limit {limit} ({filter_str})")
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            bulletins = data.get("bulletinBoard", {}).get("bulletins", [])
            logger.info(f"Successfully fetched {len(bulletins)} bulletins.")
            return bulletins

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get bulletins: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to get bulletins: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting bulletins: {e}")
            raise ConnectionError(f"Error getting bulletins: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting bulletins: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting bulletins: {e}") from e

    def __repr__(self):
        return f"<{type(self).__name__} base_url={self.base_url} authenticated={self.is_authenticated}>"

    # --- FlowFile Queue Listing Methods ---

    async def create_flowfile_listing_request(self, connection_id: str) -> dict:
        """Submits a request to list FlowFiles in a connection's queue."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/flowfile-queues/{connection_id}/listing-requests"
        # Payload is empty for listing request creation
        try:
            logger.info(f"Submitting FlowFile listing request for connection {connection_id}")
            response = await client.post(endpoint, json={}) # POST with empty JSON body
            response.raise_for_status()
            request_data = response.json()
            # Returns the listing request entity, including its ID
            logger.info(f"Successfully submitted listing request {request_data.get('listingRequest',{}).get('id')} for connection {connection_id}")
            return request_data.get("listingRequest", {}) # Return just the request part

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Connection {connection_id} not found for FlowFile listing request.")
                raise ValueError(f"Connection with ID {connection_id} not found.") from e
            else:
                logger.error(f"Failed to create FlowFile listing request for connection {connection_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to create FlowFile listing request: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error creating FlowFile listing request for connection {connection_id}: {e}")
            raise ConnectionError(f"Error creating FlowFile listing request: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred creating FlowFile listing request for {connection_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred creating FlowFile listing request: {e}") from e

    async def get_flowfile_listing_request(self, connection_id: str, request_id: str) -> dict:
        """Retrieves the status and results of a specific FlowFile listing request."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/flowfile-queues/{connection_id}/listing-requests/{request_id}"
        try:
            logger.debug(f"Fetching status for FlowFile listing request {request_id} on connection {connection_id}")
            response = await client.get(endpoint)
            response.raise_for_status()
            request_data = response.json()
            logger.debug(f"Successfully fetched status for listing request {request_id}. Finished: {request_data.get('listingRequest',{}).get('finished')}")
            return request_data.get("listingRequest", {}) # Return just the request part

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"FlowFile listing request {request_id} or connection {connection_id} not found.")
                raise ValueError(f"FlowFile listing request {request_id} or connection {connection_id} not found.") from e
            else:
                logger.error(f"Failed to get FlowFile listing request {request_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get FlowFile listing request: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting FlowFile listing request {request_id}: {e}")
            raise ConnectionError(f"Error getting FlowFile listing request: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting FlowFile listing request {request_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting FlowFile listing request: {e}") from e

    async def delete_flowfile_listing_request(self, connection_id: str, request_id: str) -> bool:
        """Deletes a completed FlowFile listing request."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/flowfile-queues/{connection_id}/listing-requests/{request_id}"
        try:
            logger.info(f"Deleting FlowFile listing request {request_id} on connection {connection_id}")
            response = await client.delete(endpoint)
            response.raise_for_status() # Should return 200 OK
            # The response body is the deleted request entity, we just need confirmation
            logger.info(f"Successfully deleted listing request {request_id}.")
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 # If it's already gone, consider it success for cleanup purposes
                 logger.warning(f"FlowFile listing request {request_id} not found for deletion (already deleted?).")
                 return True
            else:
                 logger.error(f"Failed to delete FlowFile listing request {request_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete FlowFile listing request: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting FlowFile listing request {request_id}: {e}")
            raise ConnectionError(f"Error deleting FlowFile listing request: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting FlowFile listing request {request_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting FlowFile listing request: {e}") from e

    # --- Provenance Methods ---

    async def update_process_group_state(self, pg_id: str, state: str) -> dict:
        """Starts or stops all eligible components within a specific process group."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        normalized_state = state.upper()
        if normalized_state not in ["RUNNING", "STOPPED"]:
            raise ValueError("Invalid state specified. Must be 'RUNNING' or 'STOPPED'.")

        client = await self._get_client()
        endpoint = f"/flow/process-groups/{pg_id}"

        # The payload is simple for the bulk operation
        update_payload = {
            "id": pg_id,
            "state": normalized_state,
            # No revision needed for this bulk endpoint
        }

        try:
            logger.info(f"Setting state of all components in process group {pg_id} to {normalized_state} via {self.base_url}{endpoint}")
            response = await client.put(endpoint, json=update_payload)
            response.raise_for_status()
            updated_entity = response.json() # Response contains PG entity with potentially updated component counts/states
            logger.info(f"Successfully initiated state change for process group {pg_id} to {normalized_state}.")
            # Note: This action is asynchronous on the NiFi side. The response indicates submission success.
            # The actual state of individual components might take time to update.
            return updated_entity

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Process group {pg_id} not found for state update.")
                raise ValueError(f"Process group with ID {pg_id} not found.") from e
            elif e.response.status_code == 409:
                 # 409 could mean various things here, maybe permissions or invalid state transition request
                 logger.error(f"Conflict updating state for process group {pg_id}. Response: {e.response.text}")
                 raise ValueError(f"Conflict updating state for process group {pg_id}: {e.response.text}") from e
            else:
                logger.error(f"Failed to update state for process group {pg_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to update process group state: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error updating state for process group {pg_id}: {e}")
            raise ConnectionError(f"Error updating process group state: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred updating state for process group {pg_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred updating process group state: {e}") from e

    async def submit_provenance_query(self, query_payload: Dict[str, Any]) -> dict:
        """Submits a new provenance query.

        Args:
            query_payload: The dictionary representing the ProvenanceRequestDTO.
                           Example: {"searchTerms": {"flowFileUuid": "..."}, "maxResults": 100}

        Returns:
            The dictionary representing the submitted ProvenanceQueryDTO, including the query ID.
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = "/provenance"
        try:
            # logger.info(f"Submitting provenance query: {query_payload}") # Moved logging
            
            # --- Restructure payload to match browser --- 
            original_search_terms = query_payload.get("searchTerms", {})
            formatted_search_terms = {}
            for key, value in original_search_terms.items():
                # Map known keys to NiFi's expected format
                nifi_key = None
                if key == "componentId":
                    nifi_key = "ProcessorID" # Based on browser example for component
                elif key == "flowFileUuid":
                    nifi_key = "FlowFileUUID"
                # Add other potential mappings here (e.g., eventType -> EventType?)
                
                if nifi_key:
                    formatted_search_terms[nifi_key] = {"value": value, "inverse": False}
                else:
                    # Handle unknown keys - log warning and try a simple capitalization
                    logger.warning(f"Unknown provenance search term key '{key}'. Attempting capitalization.")
                    formatted_search_terms[key.capitalize()] = {"value": value, "inverse": False}
            
            # Build the final request payload structure
            final_request_structure = {
                "maxResults": query_payload.get("maxResults", 1000), # Re-added: Seems required by NiFi API
                "summarize": query_payload.get("summarize", True), # Default like browser
                "incrementalResults": query_payload.get("incrementalResults", False), # Default like browser
                "searchTerms": formatted_search_terms,
                # Add sorting to get most recent first
                "sortColumn": "eventTime",
                "sortOrder": "DESC",
                # Add other optional fields from ProvenanceRequestDTO if needed (startDate, endDate etc.)
            }
            
            # Wrap in the outer "provenance" -> "request" keys
            final_payload_to_send = {"provenance": {"request": final_request_structure}}
            # --------------------------------------------
            
            # --- Log the payload ACTUALLY being sent --- 
            logger.info(f"Submitting restructured provenance query payload: {final_payload_to_send}")
            # -------------------------------------------

            # Use the restructured payload
            response = await client.post(endpoint, json=final_payload_to_send)
            response.raise_for_status()
            query_data = response.json()
            # Returns ProvenanceDTO which contains the query details
            logger.info(f"Successfully submitted provenance query {query_data.get('provenance',{}).get('id')}")
            return query_data.get("provenance", {}) # Return the provenance query part

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to submit provenance query: {e.response.status_code} - {e.response.text}")
            raise ConnectionError(f"Failed to submit provenance query: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error submitting provenance query: {e}")
            raise ConnectionError(f"Error submitting provenance query: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred submitting provenance query: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred submitting provenance query: {e}") from e

    async def get_provenance_query(self, query_id: str) -> dict:
        """Retrieves the status of a specific provenance query."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/provenance/{query_id}"
        try:
            logger.debug(f"Fetching status for provenance query {query_id}")
            response = await client.get(endpoint)
            response.raise_for_status()
            query_data = response.json()
            logger.debug(f"Successfully fetched status for provenance query {query_id}. Finished: {query_data.get('provenance',{}).get('query', {}).get('finished')}")
            return query_data.get("provenance", {}) # Return the provenance query part

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Provenance query {query_id} not found.")
                raise ValueError(f"Provenance query {query_id} not found.") from e
            else:
                logger.error(f"Failed to get provenance query {query_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get provenance query: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting provenance query {query_id}: {e}")
            raise ConnectionError(f"Error getting provenance query: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting provenance query {query_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting provenance query: {e}") from e

    async def get_provenance_results(self, query_id: str) -> List[Dict]:
        """Retrieves the results (events) of a completed provenance query."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        # First, get the query status to ensure it's finished and get results info
        query_info = await self.get_provenance_query(query_id)
        if not query_info.get("finished"): # Correct check directly on query_info
            raise ValueError(f"Provenance query {query_id} is not finished yet.") 
        
        results = query_info.get("results", {})
        provenance_events = results.get("provenanceEvents", [])
        logger.info(f"Retrieved {len(provenance_events)} events from completed provenance query {query_id}")
        return provenance_events # Return the list of events

    async def delete_provenance_query(self, query_id: str) -> bool:
        """Deletes a completed provenance query."""
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/provenance/{query_id}"
        try:
            logger.info(f"Deleting provenance query {query_id}")
            response = await client.delete(endpoint)
            response.raise_for_status() # Should return 200 OK
            logger.info(f"Successfully deleted provenance query {query_id}.")
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logger.warning(f"Provenance query {query_id} not found for deletion (already deleted?).")
                 return True # Consider successful cleanup
            else:
                 logger.error(f"Failed to delete provenance query {query_id}: {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to delete provenance query: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error deleting provenance query {query_id}: {e}")
            raise ConnectionError(f"Error deleting provenance query: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred deleting provenance query {query_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred deleting provenance query: {e}") from e

    async def get_provenance_event_content(self, event_id: int, direction: Literal["input", "output"]) -> httpx.Response:
        """Retrieves the content associated with a provenance event.

        Args:
            event_id: The numeric ID of the provenance event.
            direction: 'input' or 'output' to specify which content claim to retrieve.

        Returns:
            The httpx.Response object. The caller is responsible for handling the content stream.
            Example: `response.read()` or `response.aiter_bytes()`
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        if direction not in ["input", "output"]:
            raise ValueError("Direction must be either 'input' or 'output'.")

        client = await self._get_client()
        # --- Corrected Endpoint Path ---
        # endpoint = f"/provenance/events/{event_id}/content/{direction}" # Old incorrect path
        endpoint = f"/provenance-events/{event_id}/content/{direction}" # Correct path
        # -----------------------------
        try:
            logger.info(f"Fetching {direction} content for provenance event {event_id}")
            # Use stream=True to allow caller to handle large content
            response = await client.get(endpoint, timeout=120.0) # Longer timeout for potential content download
            response.raise_for_status()
            logger.info(f"Successfully initiated content fetch for event {event_id} ({direction}). Status: {response.status_code}")
            return response # Return the raw response for streaming

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logger.warning(f"Provenance event {event_id} or its {direction} content not found.")
                 raise ValueError(f"Provenance event {event_id} or its {direction} content not found.") from e
            else:
                 logger.error(f"Failed to get content for provenance event {event_id} ({direction}): {e.response.status_code} - {e.response.text}")
                 raise ConnectionError(f"Failed to get provenance event content: {e.response.status_code}, {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Error getting content for provenance event {event_id} ({direction}): {e}")
            raise ConnectionError(f"Error getting provenance event content: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting content for provenance event {event_id} ({direction}): {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting provenance event content: {e}") from e

    async def get_provenance_event(self, event_id: int) -> Dict:
        """Retrieves the details of a specific provenance event by its ID.

        Args:
            event_id: The numeric ID of the provenance event.

        Returns:
            A dictionary containing the provenance event details.
        """
        if not self._token:
            raise NiFiAuthenticationError("Client is not authenticated. Call authenticate() first.")

        client = await self._get_client()
        endpoint = f"/provenance-events/{event_id}"
        try:
            logger.info(f"Fetching details for provenance event {event_id}")
            response = await client.get(endpoint)
            response.raise_for_status()
            event_data = response.json()
            # The relevant data is usually within the 'provenanceEvent' key
            logger.info(f"Successfully fetched details for event {event_id}")
            return event_data.get("provenanceEvent", {}) # Return the inner event details

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Provenance event {event_id} not found.")
                raise ValueError(f"Provenance event {event_id} not found.") from e
            else:
                logger.error(f"Failed to get provenance event {event_id}: {e.response.status_code} - {e.response.text}")
                raise ConnectionError(f"Failed to get provenance event: {e.response.status_code}, {e.response.text}") from e
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error getting provenance event {event_id}: {e}")
            raise ConnectionError(f"Error getting provenance event: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred getting provenance event {event_id}: {e}", exc_info=True)
            raise ConnectionError(f"An unexpected error occurred getting provenance event: {e}") from e

# Example usage (for testing or direct script execution)
async def main():
    # REMOVED direct os.getenv usage here - configuration should be loaded from config.yaml
    # and passed to the client constructor externally.
    logger.warning("Running main() requires manual configuration of NiFiClient parameters.")
    # Example: Replace with actual config loading
    # from config.settings import get_nifi_server_config
    # server_conf = get_nifi_server_config("nifi-local") # Use an ID from your config.yaml
    # if not server_conf:
    #     logger.error("NiFi server config not found.")
    #     return
    # client = NiFiClient(
    #     base_url=server_conf.get('url'),
    #     username=server_conf.get('username'),
    #     password=server_conf.get('password'),
    #     tls_verify=server_conf.get('tls_verify', True)
    # )
    # ... rest of main function ...

    # Dummy client for demonstration if needed, replace with actual configured client
    client = NiFiClient(base_url="http://localhost:8443/nifi-api") # Minimal example

    try:
        await client.authenticate()
        print(f"Authentication successful: {client.is_authenticated}")
        root_id = await client.get_root_process_group_id()
        print(f"Root Process Group ID: {root_id}")

        # Example: List processors in root
        processors = await client.list_processors(root_id)
        processgroups= await client.list_process_groups(process_group_id=root_id)
        print(f"Processors in root ({root_id}): {len(processors)}")
        print(f"Process Groups in root : {len(processgroups)}")
        # for proc in processors:
        #     print(f"  - {proc.get('component', {}).get('name')} (ID: {proc.get('id')})")

    except NiFiAuthenticationError as e:
        print(f"Authentication Error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await client.close()

# Note: Running this directly requires NIFI_API_URL, NIFI_USERNAME, NIFI_PASSWORD
# or manually providing the details in the main function.
# Ensure NIFI_TLS_VERIFY=false is set in .env if using self-signed certs.
# REMOVED references to .env as config is now centralized in config.yaml

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
