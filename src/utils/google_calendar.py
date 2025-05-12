import datetime
import os.path
import logging
from dateutil import parser, tz
import asyncio
import functools  # ADDED

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # Still needed for the explicit flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import config getters
from .config_loader import (
    get_google_client_id,
    get_google_client_secret,
    get_google_refresh_token,
    get_google_token_uri,
    get_google_calendar_config  # Get the whole dict for flow
)

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the refresh_token in config.yaml and re-authorize.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# --- NEW: Extracted Authorization Flow Function ---
async def run_google_auth_flow():
    """
    Runs the Google OAuth 2.0 installed application flow to obtain new credentials.
    Returns:
        google.oauth2.credentials.Credentials: The obtained credentials object,
                                                or None if the flow fails.
    """
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    google_config = get_google_calendar_config()

    logger.warning("Starting explicit Google authorization flow...")
    if not all([client_id, client_secret]):
        logger.critical("Cannot start authorization flow: client_id or client_secret missing in config.")
        return None
    if not google_config or 'redirect_uris' not in google_config:
        logger.critical("Cannot start authorization flow: 'google_calendar' section or 'redirect_uris' missing in config.")
        return None

    try:
        client_config_dict = {"installed": google_config}
        flow = InstalledAppFlow.from_client_config(client_config_dict, SCOPES)

        logger.info("Starting local server for authorization flow. Please follow the instructions in your browser.")
        # Run in executor as run_local_server is blocking
        loop = asyncio.get_running_loop()

        # Use functools.partial to pass keyword arguments like port=0
        partial_run_local_server = functools.partial(flow.run_local_server, port=0)
        creds = await loop.run_in_executor(None, partial_run_local_server)

        if creds and creds.refresh_token:
            logger.info("Authorization flow successful, new credentials obtained.")
            return creds
        else:
            logger.error("Authorization flow completed, but did not obtain a refresh token.")
            return None

    except Exception as e:
        logger.error(f"Error during explicit authorization flow: {e}", exc_info=True)
        return None


def get_calendar_service():
    """
    Initializes and returns the Google Calendar API service client
    using credentials (refresh_token) stored in config.yaml.
    Does NOT automatically trigger re-authorization on failure.
    """
    creds = None
    config_refresh_token = get_google_refresh_token()
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    token_uri = get_google_token_uri()

    if not config_refresh_token:
        logger.critical("Google refresh_token missing in configuration. Cannot initialize Calendar service.")
        logger.critical("Run the '!reauth_google' command (owner only) to get a new token.")
        return None

    # --- Load Credentials from Config Refresh Token ---
    logger.info("Attempting to load credentials using refresh token from config.")
    try:
        creds = Credentials.from_authorized_user_info(info={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": config_refresh_token,
            "token_uri": token_uri,
            "scopes": SCOPES
        }, scopes=SCOPES)

        if creds and creds.expired and creds.refresh_token:
            logger.info("Google credentials expired, refreshing...")
            try:
                creds.refresh(Request())
                logger.info("Google credentials refreshed successfully.")
            except Exception as e:
                # *** If refresh fails, log error and instruct user, DO NOT re-auth here ***
                if 'invalid_grant' in str(e).lower():
                    logger.error(f"Refresh token invalid or revoked ({e}).")
                    logger.critical("Run the '!reauth_google' command (owner only) to get a new token.")
                else:
                    logger.error(f"Failed to refresh Google credentials: {e}")
                return None  # Stop if refresh fails
        elif not creds:
            logger.error("Failed to create credentials object from config info.")
            return None

    except Exception as e:
        logger.error(f"Error creating credentials from config: {e}")
        if 'invalid_grant' in str(e).lower():
            logger.error("Credentials creation failed, likely invalid token.")
            logger.critical("Run the '!reauth_google' command (owner only) to get a new token.")
        return None

    # --- Build the Service ---
    if not creds or not creds.valid:
        logger.error("Failed to obtain valid Google Calendar credentials after refresh attempt.")
        # Added instruction here too for clarity
        logger.critical("Run the '!reauth_google' command (owner only) to get a new token.")
        return None

    try:
        service = build('calendar', 'v3', credentials=creds)
        logger.info("Google Calendar service built successfully.")
        return service
    except HttpError as error:
        logger.error(f'An error occurred building the Google Calendar service: {error}')
        return None
    except Exception as e:
        logger.error(f'An unexpected error occurred building the Google Calendar service: {e}')
        return None


# --- Other Calendar Utility Functions ---

async def get_events_for_day(service, target_date):
    """Fetches and formats events for a specific date."""
    if not service:
        logger.error("get_events_for_day called with no service object.")
        return "Error: Calendar service not available.", []

    try:
        # Set timeMin and timeMax for the entire day in the local timezone
        local_tz = tz.tzlocal()
        start_of_day = datetime.datetime.combine(target_date, datetime.time.min).replace(tzinfo=local_tz)
        end_of_day = datetime.datetime.combine(target_date, datetime.time.max).replace(tzinfo=local_tz)

        time_min_iso = start_of_day.isoformat()
        time_max_iso = end_of_day.isoformat()

        logger.info(f"Fetching events from {time_min_iso} to {time_max_iso}")

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        event_details_list = []  # To store tuples for removal later
        if not events:
            logger.info(f"No events found for {target_date.strftime('%Y-%m-%d')}")
            return f"No events found for {target_date.strftime('%A, %B %d, %Y')}.", []
        else:
            summary_lines = [f"**Schedule for {target_date.strftime('%A, %B %d, %Y')}:**"]
            event_counter = 1
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))  # Get end time/date

                # Parse start time/date
                start_dt = parser.isoparse(start)

                # Format time string
                if 'dateTime' in event['start']:
                    # It's a timed event
                    start_time_local = start_dt.astimezone(local_tz)
                    time_str = start_time_local.strftime('%I:%M %p')  # e.g., 09:30 AM

                    # Add duration if end time is available
                    if 'dateTime' in event['end']:
                        end_dt = parser.isoparse(end).astimezone(local_tz)
                        duration = end_dt - start_time_local
                        duration_minutes = int(duration.total_seconds() / 60)
                        if duration_minutes > 0:
                            time_str += f" ({duration_minutes} min)"
                else:
                    # It's an all-day event
                    time_str = "All Day"

                event_summary = event.get('summary', 'No Title')
                summary_lines.append(f"`[{event_counter}]` {time_str}: {event_summary}")
                event_details_list.append((event['id'], time_str, event_summary))
                event_counter += 1

            logger.info(f"Found {len(events)} events for {target_date.strftime('%Y-%m-%d')}")
            return "\n".join(summary_lines), event_details_list

    except HttpError as error:
        logger.error(f'An HTTP error occurred fetching events: {error}')
        return f"Error: An HTTP error occurred while fetching the schedule: {error}", []
    except Exception as e:
        logger.error(f'An unexpected error occurred fetching events: {e}', exc_info=True)
        return f"An unexpected error occurred while fetching the schedule: {e}", []


async def add_calendar_event(service, summary, start_dt, end_dt):
    """Adds an event to the primary calendar."""
    if not service:
        logger.error("add_calendar_event called with no service object.")
        return "Error: Calendar service not available."

    try:
        local_tz_name = datetime.datetime.now(tz.tzlocal()).tzname()
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': local_tz_name,
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': local_tz_name,
            },
        }

        logger.info(f"Adding event: {summary} from {start_dt.isoformat()} to {end_dt.isoformat()}")
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        logger.info(f"Event created: {created_event.get('htmlLink')}")
        return f"✅ Event added: '{summary}' on {start_dt.strftime('%b %d at %I:%M %p')}. Link: <{created_event.get('htmlLink')}>"

    except HttpError as error:
        logger.error(f'An HTTP error occurred adding event: {error}')
        return f"Error: An HTTP error occurred while adding the event: {error}"
    except Exception as e:
        logger.error(f'An unexpected error occurred adding event: {e}', exc_info=True)
        return f"An unexpected error occurred while adding the event: {e}"


async def remove_calendar_event(service, event_id):
    """Removes an event from the primary calendar by its ID."""
    if not service:
        logger.error("remove_calendar_event called with no service object.")
        return "Error: Calendar service not available."

    try:
        logger.info(f"Attempting to delete event with ID: {event_id}")
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        logger.info(f"Successfully deleted event with ID: {event_id}")
        return f"🗑️ Event removed successfully."

    except HttpError as error:
        if error.resp.status == 404 or error.resp.status == 410:  # Not Found or Gone
            logger.warning(f"Event with ID {event_id} not found or already deleted.")
            return "⚠️ Event not found. It might have been already deleted."
        else:
            logger.error(f'An HTTP error occurred removing event {event_id}: {error}')
            return f"Error: An HTTP error occurred while removing the event: {error}"
    except Exception as e:
        logger.error(f'An unexpected error occurred removing event {event_id}: {e}', exc_info=True)
        return f"An unexpected error occurred while removing the event: {e}"


def parse_relative_date(day_str: str) -> datetime.date | None:
    """Parses a string like 'today', 'tomorrow', 'monday', 'April 25' into a date object."""
    today = datetime.date.today()
    day_str_lower = day_str.lower().strip()

    if day_str_lower == "today":
        return today
    elif day_str_lower == "tomorrow":
        return today + datetime.timedelta(days=1)
    elif day_str_lower == "yesterday":
        return today - datetime.timedelta(days=1)
    else:
        try:
            # Try direct parsing (e.g., "April 25", "2025-04-25")
            # Use default=today to provide context for relative terms like "next Friday"
            parsed_dt = parser.parse(day_str, default=datetime.datetime.combine(today, datetime.time(0)))
            return parsed_dt.date()
        except parser.ParserError:
            # Try parsing weekdays more robustly
            weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            try:
                target_weekday = weekdays.index(day_str_lower)
                days_ahead = (target_weekday - today.weekday() + 7) % 7
                if days_ahead == 0:  # If user says "monday" and it's Monday, assume next Monday
                    days_ahead = 7
                return today + datetime.timedelta(days=days_ahead)
            except ValueError:
                # Not a recognized weekday or format
                logger.warning(f"Could not parse date string: {day_str}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error parsing date string '{day_str}': {e}")
            return None
