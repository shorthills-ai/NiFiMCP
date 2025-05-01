# Placeholder for configuration loading (API keys etc.)
import os
import yaml
from pathlib import Path
# Remove streamlit import
# import streamlit as st
# from dotenv import load_dotenv # Removed dotenv import

# Define project root assuming this file is in config/settings.py
PROJECT_ROOT = Path(__file__).parent.parent

# --- YAML Configuration Loading ---

DEFAULT_LOGGING_CONFIG = {
    'log_directory': 'logs',
    'interface_debug_enabled': False,
    'console': {'level': 'INFO'},
    'client_file': {'enabled': True, 'level': 'DEBUG'},
    'server_file': {'enabled': True, 'level': 'DEBUG'},
}

DEFAULT_APP_CONFIG = {
    'nifi': {
        'servers': [] # Default to empty list
    },
    'llm': {
        'google': {'api_key': None, 'models': ['gemini-1.5-pro-latest']},
        'openai': {'api_key': None, 'models': ['gpt-4-turbo-preview']}
    }
}

def _load_yaml_config(config_path: Path, default_config: dict) -> dict:
    """Loads configuration from a YAML file, falling back to defaults."""
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                print(f"Successfully loaded configuration from {config_path}")
                # Simple merge strategy: Update default with loaded data (won't handle deep merges)
                merged_config = default_config.copy()
                if config_data:
                     # Basic recursive update for nested dicts
                    def update_dict(d, u):
                        for k, v in u.items():
                            if isinstance(v, dict):
                                d[k] = update_dict(d.get(k, {}), v)
                            else:
                                d[k] = v
                        return d
                    merged_config = update_dict(merged_config, config_data)
                return merged_config
        except Exception as e:
            print(f"Warning: Error loading configuration from {config_path}: {e}. Using defaults.")
            return default_config
    else:
        print(f"Warning: Configuration file not found at {config_path}. Using defaults.")
        return default_config

# Load Logging Config
LOGGING_CONFIG = _load_yaml_config(PROJECT_ROOT / "logging_config.yaml", DEFAULT_LOGGING_CONFIG)

# Load Application Config
_APP_CONFIG = _load_yaml_config(PROJECT_ROOT / "config.yaml", DEFAULT_APP_CONFIG)

# --- Configuration Accessors ---

def get_logging_config() -> dict:
    """Returns the loaded logging configuration."""
    return LOGGING_CONFIG

def get_app_config() -> dict:
    """Returns the loaded application configuration."""
    return _APP_CONFIG

def get_nifi_servers() -> list[dict]:
    """Returns the list of configured NiFi servers."""
    return _APP_CONFIG.get('nifi', {}).get('servers', [])

def get_nifi_server_config(server_id: str) -> dict | None:
    """Finds and returns the configuration for a specific NiFi server by its ID."""
    for server in get_nifi_servers():
        if server.get('id') == server_id:
            return server
    print(f"Warning: NiFi server configuration not found for ID: {server_id}")
    return None

# --- Specific Config Values ---

# Load API keys using nested gets for safety
GOOGLE_API_KEY = _APP_CONFIG.get('llm', {}).get('google', {}).get('api_key')
OPENAI_API_KEY = _APP_CONFIG.get('llm', {}).get('openai', {}).get('api_key')

# Load model configurations with defaults from DEFAULT_APP_CONFIG if necessary
OPENAI_MODELS = _APP_CONFIG.get('llm', {}).get('openai', {}).get('models', DEFAULT_APP_CONFIG['llm']['openai']['models'])
GEMINI_MODELS = _APP_CONFIG.get('llm', {}).get('google', {}).get('models', DEFAULT_APP_CONFIG['llm']['google']['models'])

# Print loaded configuration (excluding sensitive values like full NiFi server details)
print("\nLoaded application configuration:")
# -----Azure OpenAI support ----
# Load Azure OpenAI API key
AZURE_OPENAI_API_KEY = load_api_key("AZURE_OPENAI_API_KEY")

# Load Azure OpenAI configuration values
AZURE_OPENAI_ENDPOINT = load_config_value("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-03-01-preview")

# -----Azure OpenAI support ----
AZURE_OPENAI_DEPLOYMENTS = {
    # deployment-name :  api-version   , token-parameter
    "gpt-4o":   {"api_version": "2024-03-01-preview", "token_param": "max_tokens"},
    "o1":       {"api_version": "2024-12-01-preview", "token_param": "max_completion_tokens"},
    "o3-mini":  {"api_version": "2024-12-01-preview", "token_param": "max_completion_tokens"},
}

AZURE_OPENAI_DEPLOYMENT = load_config_value("AZURE_OPENAI_DEPLOYMENT", "")

# Load Azure OpenAI models if needed (optional now, but setting it up)
AZURE_OPENAI_MODELS_STR = load_config_value("AZURE_OPENAI_MODELS", "gpt-4o-mini")
AZURE_OPENAI_MODELS = [model.strip() for model in AZURE_OPENAI_MODELS_STR.split(',') if model.strip()]


# Print loaded configuration (excluding sensitive values)
print("\nLoaded environment/model configuration:")
print(f"OPENAI_MODELS: {OPENAI_MODELS}")
print(f"GEMINI_MODELS: {GEMINI_MODELS}")
print(f"GOOGLE_API_KEY configured: {'Yes' if GOOGLE_API_KEY else 'No'}")
print(f"OPENAI_API_KEY configured: {'Yes' if OPENAI_API_KEY else 'No'}")
nifi_server_summary = [(s.get('id', 'N/A'), s.get('name', 'N/A')) for s in get_nifi_servers()]
print(f"NiFi Servers configured: {len(nifi_server_summary)} {nifi_server_summary if nifi_server_summary else '(None)'}")
print(f"AZURE_OPENAI_MODELS: {AZURE_OPENAI_MODELS}")
print(f"AZURE_OPENAI_API_KEY configured: {'Yes' if AZURE_OPENAI_API_KEY else 'No'}")

# Optionally print logging config status
print(f"Logging config loaded: {'Yes' if LOGGING_CONFIG != DEFAULT_LOGGING_CONFIG else 'No (Using Defaults)'}")

# --- Deprecated Functions (Keep temporarily for reference/smooth transition if needed, but remove eventually) ---

# def load_api_key(key_name: str) -> str | None:
#     """DEPRECATED: Loads an API key from environment variables."""
#     print(f"Warning: Deprecated function load_api_key called for {key_name}")
#     return os.getenv(key_name)

# def load_config_value(key_name: str, default_value: str) -> str:
#     """DEPRECATED: Loads a configuration value from environment variables with a default fallback."""
#     print(f"Warning: Deprecated function load_config_value called for {key_name}")
#     return os.getenv(key_name, default_value)

# --- End of File ---
