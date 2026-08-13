import logging
import uuid
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Authenticate and return the Google Calendar service."""
    creds = service_account.Credentials.from_service_account_file(
        settings.GSPREAD_CREDENTIALS_FILE, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def generate_meeting_link(company_name: str) -> str:
    """
    Creates a placeholder event on the service account calendar
    and returns a unique Google Meet video link.
    """
    try:
        service = get_calendar_service()
        
        # Create a placeholder event 7 days in the future
        now = datetime.datetime.utcnow()
        start_time = now + datetime.timedelta(days=7)
        end_time = start_time + datetime.timedelta(minutes=15)
        
        event = {
            'summary': f'Intro Chat: Vantrade Services & {company_name}',
            'description': 'Placeholder event for generated meeting link.',
            'start': {
                'dateTime': start_time.isoformat() + 'Z',
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat() + 'Z',
                'timeZone': 'UTC',
            },
            'conferenceData': {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {
                        'type': 'hangoutsMeet'
                    }
                }
            }
        }

        # create the event on the primary calendar of the service account
        # conferenceDataVersion=1 is REQUIRED to generate the Meet link
        event = service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1
        ).execute()

        meet_link = event.get('hangoutLink')
        if not meet_link:
            logger.error("Google Calendar API did not return a hangoutLink.")
            return "https://meet.google.com/new"  # fallback
            
        logger.info(f"Generated Meet link for {company_name}: {meet_link}")
        return meet_link

    except Exception as exc:
        logger.error(f"Error generating meeting link: {exc}")
        return "https://meet.google.com/new"  # generic fallback if API fails
