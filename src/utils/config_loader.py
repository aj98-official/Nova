import yaml
import logging
import os
from dateutil import tz
import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# --- Global variables to store loaded config ---
CONFIG = {}
BOT_TOKEN = None
LLM_COMMAND_CONFIGS = {}
USER_SETTINGS = {}
NOTIFY_CHANNEL_ID = None
DAILY_SUMMARY_TIME_STR = "08:00" # Default
DAILY_SUMMARY_TIME_OBJ = None
GOOGLE_CALENDAR_CONFIG = {} # ADDED: To store google config section

def load_config():
    """Loads configuration from environment variables and config.yaml."""
    global CONFIG, BOT_TOKEN, LLM_COMMAND_CONFIGS, USER_SETTINGS
    global NOTIFY_CHANNEL_ID, DAILY_SUMMARY_TIME_STR, DAILY_SUMMARY_TIME_OBJ
    global GOOGLE_CALENDAR_CONFIG # ADDED

    with open("config.yaml", "r") as file:
        CONFIG = yaml.safe_load(file)

    # Replace sensitive placeholders with values from environment variables
    for section, values in CONFIG.items():
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]  # Extract the environment variable name
                    CONFIG[section][key] = os.getenv(env_var, value)  # Replace with env value or keep placeholder

    BOT_TOKEN = CONFIG.get('discord', {}).get('bot_token')
    LLM_COMMAND_CONFIGS = CONFIG.get('llm', {}).get('commands', {})
    USER_SETTINGS = CONFIG.get('user_settings', {})
    GOOGLE_CALENDAR_CONFIG = CONFIG.get('google_calendar', {}) # ADDED: Load google section

    NOTIFY_CHANNEL_ID = USER_SETTINGS.get('notify_channel_id')
    DAILY_SUMMARY_TIME_STR = USER_SETTINGS.get('daily_summary_time', "08:00") # Use default if missing

    # --- Configuration Validation ---
    if not BOT_TOKEN:
        logger.critical(f"CRITICAL: discord.bot_token not found in environment variables. Bot cannot start.")
        exit()

    # ADDED: Check for essential Google Calendar config keys needed for auth flow
    required_google_keys = ['client_id', 'client_secret', 'auth_uri', 'token_uri', 'redirect_uris']
    missing_google_keys = [key for key in required_google_keys if key not in GOOGLE_CALENDAR_CONFIG or not GOOGLE_CALENDAR_CONFIG[key]]
    if missing_google_keys:
         logger.warning(f"Google Calendar config is incomplete. Missing or empty keys: {missing_google_keys}. Authorization might fail.")

    # Parse daily summary time
    try:
        time_parts = DAILY_SUMMARY_TIME_STR.split(':')
        DAILY_SUMMARY_TIME_OBJ = datetime.time(hour=int(time_parts[0]), minute=int(time_parts[1]), tzinfo=tz.tzlocal())
        logger.info(f"Daily summary time parsed as {DAILY_SUMMARY_TIME_OBJ.strftime('%H:%M %Z')}")
    except Exception as e:
        logger.error(f"Invalid daily_summary_time format '{DAILY_SUMMARY_TIME_STR}' in environment variables (expected HH:MM). Using default 08:00. Error: {e}")
        DAILY_SUMMARY_TIME_OBJ = datetime.time(hour=8, minute=0, tzinfo=tz.tzlocal()) # Fallback to default

def is_llm_command_configured(command_name: str) -> bool:
    """Checks if the LLM configuration for a specific command is complete."""
    command_config = LLM_COMMAND_CONFIGS.get(command_name, {})
    required_keys = ['api_key', 'api_url', 'model_name', 'system_prompt', 'provider_name']
    is_configured = all(key in command_config and command_config[key] for key in required_keys)
    if not is_configured:
        missing = [key for key in required_keys if not command_config.get(key)]
        logger.warning(f"LLM settings for command '{command_name}' incomplete. Missing or empty keys: {missing}. Command may be disabled.")
    return is_configured

# --- Expose loaded values ---
# These functions allow other modules to safely access the config values
# without needing direct access to the global variables.

def get_bot_token():
    """Returns the loaded Discord Bot Token."""
    return BOT_TOKEN

def get_llm_command_configs():
    """Returns the dictionary of LLM configurations for all commands."""
    return LLM_COMMAND_CONFIGS

def get_notify_channel_id():
    """Returns the ID for the notification channel."""
    return NOTIFY_CHANNEL_ID

def get_daily_summary_time_obj():
    """Returns the datetime.time object for the daily summary."""
    return DAILY_SUMMARY_TIME_OBJ

# --- ADDED: Getters for Google Calendar Config ---

def get_google_calendar_config():
    """Returns the entire google_calendar config dictionary."""
    # Use this when the whole structure is needed (like for InstalledAppFlow)
    return GOOGLE_CALENDAR_CONFIG

def get_google_client_id():
    """Returns the Google Client ID."""
    return GOOGLE_CALENDAR_CONFIG.get('client_id')

def get_google_client_secret():
    """Returns the Google Client Secret."""
    # Consider adding warning if retrieved directly due to sensitivity
    # logger.warning("Retrieving sensitive client_secret from config.")
    return GOOGLE_CALENDAR_CONFIG.get('client_secret')

def get_google_project_id():
    """Returns the Google Project ID."""
    return GOOGLE_CALENDAR_CONFIG.get('project_id')

def get_google_auth_uri():
    """Returns the Google Auth URI."""
    return GOOGLE_CALENDAR_CONFIG.get('auth_uri', "https://accounts.google.com/o/oauth2/auth") # Default

def get_google_token_uri():
    """Returns the Google Token URI."""
    return GOOGLE_CALENDAR_CONFIG.get('token_uri', "https://oauth2.googleapis.com/token") # Default

def get_google_redirect_uris():
    """Returns the list of Google Redirect URIs."""
    return GOOGLE_CALENDAR_CONFIG.get('redirect_uris', []) # Default to empty list

def get_google_refresh_token():
    """Returns the Google Refresh Token."""
    # Consider adding warning if retrieved directly due to sensitivity
    # logger.warning("Retrieving sensitive refresh_token from config.")
    return GOOGLE_CALENDAR_CONFIG.get('refresh_token')