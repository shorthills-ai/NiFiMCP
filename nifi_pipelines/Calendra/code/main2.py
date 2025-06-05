import requests
import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
import csv
import os

token = os.getenv("token")
# Define IST timezone (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)
TOKEN_FILE = '/home/nifi/nifi2/users/priyanshu/Output/token/token.txt'
def get_token():
    """Read token from file"""
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, 'r') as f:
        return f.read().strip()
    
def clean_text(text):
    """
    Clean HTML content from the text, remove scripts/styles, control characters, and extra whitespace.
    """
    text = html.unescape(text)
    # Remove <script> and <style> blocks
    text = re.sub(r'<(script|style).*?>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all other HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Replace non-breaking spaces with normal spaces
    text = text.replace('\u00a0', ' ')
    # Remove control characters
    text = ''.join(c for c in text if unicodedata.category(c)[0] != 'C')
    # Normalize whitespace
    return re.sub(r'\s+', ' ', text).strip()

def to_ist(utc_dt_str):
    """
    Convert UTC datetime string (ISO format) to IST timezone string.
    """
    if not utc_dt_str:
        return ""
    try:
        utc_dt = datetime.fromisoformat(utc_dt_str.replace('Z', '+00:00'))
        ist_dt = utc_dt.astimezone(IST)
        return ist_dt.strftime('%Y-%m-%d %H:%M:%S IST')
    except Exception:
        return ""

def fetch_last_30_days_emails(access_token):
    """
    Fetch last 30 days emails from the user's inbox using Microsoft Graph API.
    Exclude meeting cancellations/updates from emails.
    """
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    url = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        f"?$filter=receivedDateTime ge {thirty_days_ago}"
        "&$orderby=receivedDateTime desc"
        "&$top=100"
    )
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    messages = response.json().get("value", [])
    cleaned_emails = []

    for msg in messages:
        subject = msg.get("subject", "")
        raw_body = msg.get("body", {}).get("content", "") or msg.get("bodyPreview", "")
        body = clean_text(raw_body)
        receivedatetime = msg.get("receivedDateTime", "")
        sender_email = msg.get("from", {}).get("emailAddress", {}).get("address", "")
        is_meeting = msg.get("meetingMessageType") is not None

        # Exclude meeting cancellations and updates from email list
        if is_meeting:
            meeting_type = msg.get("meetingMessageType", "").lower()
            if "cancel" in meeting_type or "update" in meeting_type:
                continue

        cleaned_emails.append({
            "type": "email",
            "subject": subject,
            "body": body,
            "receivedatetime": receivedatetime,
            "sender_email": sender_email,
            "meeting_invite": "yes" if is_meeting else "no",
            "meeting_start": "",
            "meeting_end": ""
        })

    return cleaned_emails

def fetch_last_30_days_meetings(access_token):
    """
    Fetch calendar meetings from the last 30 days using Microsoft Graph API.
    """
    start_datetime = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    end_datetime = datetime.utcnow().isoformat() + "Z"

    url = (
        "https://graph.microsoft.com/v1.0/me/calendarView"
        f"?startDateTime={start_datetime}"
        f"&endDateTime={end_datetime}"
        "&$orderby=start/dateTime"
        "&$top=100"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    events = response.json().get("value", [])

    meetings = []
    for event in events:
        subject = event.get("subject", "")
        body = clean_text(event.get("body", {}).get("content", ""))
        created_time = event.get("createdDateTime", "")
        organizer_email = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
        is_cancelled = event.get("showAs", "").lower() == "cancelled" or event.get("isCancelled", False)
        meeting_start_utc = event.get("start", {}).get("dateTime", "")
        meeting_end_utc = event.get("end", {}).get("dateTime", "")

        meeting_start = "" if is_cancelled else to_ist(meeting_start_utc)
        meeting_end = "" if is_cancelled else to_ist(meeting_end_utc)

        meetings.append({
            "type": "meeting",
            "subject": subject,
            "body": body,
            "receivedatetime": created_time,
            "sender_email": organizer_email,
            "meeting_invite": "yes",
            "meeting_start": meeting_start,
            "meeting_end": meeting_end
        })

    return meetings

def fetch_combined_data(access_token):
    """
    Combine emails and meetings, filtering out emails that duplicate meeting subjects.
    """
    emails = fetch_last_30_days_emails(access_token)
    meetings = fetch_last_30_days_meetings(access_token)

    meeting_subjects = set(m["subject"] for m in meetings if m["subject"])
    unique_emails = [e for e in emails if e["subject"] not in meeting_subjects]

    return unique_emails + meetings

def save_to_csv(data, filename="/home/nifi/nifi2/users/priyanshu/Output/output.csv"):
    """
    Save combined data to CSV file.
    """
    if not data:
        print("No data to save.")
        return

    keys = data[0].keys()
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

if __name__ == "__main__":
    ACCESS_TOKEN = token
    combined_data = fetch_combined_data(ACCESS_TOKEN)
    print(f"Fetched {len(combined_data)} records from the last 30 days.")
    save_to_csv(combined_data)
