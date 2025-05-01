# Placeholder for configuration loading (API keys etc.)
import os
import yaml  # Added
from pathlib import Path  # Added
# Remove streamlit import
# import streamlit as st 
from dotenv import load_dotenv # Import dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Define project root assuming this file is in config/settings.py
PROJECT_ROOT = Path(__file__).parent.parent

# --- Logging Configuration Loading ---

DEFAULT_LOGGING_CONFIG = {
    'log_directory': 'logs',
    'interface_debug_enabled': False,
    'console': {'level': 'INFO'},
    'client_file': {'enabled': True, 'level': 'DEBUG'},
    'server_file': {'enabled': True, 'level': 'DEBUG'},
    # Add defaults for interface files if needed, or rely on setup function
}

def load_logging_config(config_path: Path = PROJECT_ROOT / "logging_config.yaml") -> dict:
    """Loads logging configuration from a YAML file."""
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                print(f"Successfully loaded logging configuration from {config_path}")
                return config_data if config_data else DEFAULT_LOGGING_CONFIG
        except Exception as e:
            print(f"Warning: Error loading logging configuration from {config_path}: {e}. Using defaults.")
            return DEFAULT_LOGGING_CONFIG
    else:
        print(f"Warning: Logging configuration file not found at {config_path}. Using defaults.")
        return DEFAULT_LOGGING_CONFIG

LOGGING_CONFIG = load_logging_config()

# --- Existing Configuration Loading ---

def load_api_key(key_name: str) -> str | None:
    """Loads an API key from environment variables."""
    # Simplify to only use os.getenv
    return os.getenv(key_name)
    # secret_value = None
    # try:
    #     # Attempt to access the secret. This might fail if secrets.toml doesn't exist.
    #     if key_name in st.secrets:
    #         secret_value = st.secrets[key_name]
    # except FileNotFoundError:
    #     # This is expected if secrets.toml is not used, ignore and proceed.
    #     pass
    # except Exception as e:
    #     # Log other potential unexpected errors during secret access
    #     # Use st.warning or print, depending on where this config runs
    #     print(f"Warning: Error checking Streamlit secrets for {key_name}: {e}")

    # if secret_value:
    #     return secret_value
    # else:
    #     # Fallback to environment variable if not found in secrets (or secrets file missing)
    #     return os.getenv(key_name)

def load_config_value(key_name: str, default_value: str) -> str:
    """Loads a configuration value from environment variables with a default fallback."""
    return os.getenv(key_name, default_value)

# Load API keys
GOOGLE_API_KEY = load_api_key("GOOGLE_API_KEY")
OPENAI_API_KEY = load_api_key("OPENAI_API_KEY")

# Load model configurations with defaults
OPENAI_MODELS_STR = load_config_value("OPENAI_MODELS", "gpt-4-turbo-preview")
GEMINI_MODELS_STR = load_config_value("GEMINI_MODELS", "gemini-1.5-pro-latest")

# Parse the comma-separated strings into lists, removing empty strings
OPENAI_MODELS = [model.strip() for model in OPENAI_MODELS_STR.split(',') if model.strip()]
GEMINI_MODELS = [model.strip() for model in GEMINI_MODELS_STR.split(',') if model.strip()]

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
print(f"AZURE_OPENAI_MODELS: {AZURE_OPENAI_MODELS}")
print(f"AZURE_OPENAI_API_KEY configured: {'Yes' if AZURE_OPENAI_API_KEY else 'No'}")

# Optionally print logging config status
print(f"Logging config loaded: {'Yes' if LOGGING_CONFIG != DEFAULT_LOGGING_CONFIG else 'No (Using Defaults)'}")
