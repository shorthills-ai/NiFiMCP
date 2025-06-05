

import datetime
from dateutil import parser
import requests
import os
import csv
from datetime import timedelta, time, timezone
import pytz

# Configuration
CONFIG = {
    'TOKEN_FILE': '/home/nifi/nifi2/users/priyanshu/Output/token/token.txt',
    'SUMMARY_CSV': '/home/nifi/nifi2/users/priyanshu/Output/Sumarize.csv',
    'SENT_MAIL_CSV': '/home/nifi/nifi2/users/priyanshu/Output/send_mail.csv',
    'WORKING_HOURS': {
        'start': time(9, 0),    # 9 AM
        'end': time(19, 0),     # 7 PM
    },
    'MEETING_DURATION': 30,     # minutes
    'TIMEZONE': 'Asia/Kolkata', # Update to your timezone
    'LOOKAHEAD_DAYS': 4,        # Number of days to look ahead for availability
    'MIN_SCHEDULE_NOTICE': 1    # Minimum hours notice required for scheduling
}

class MeetingScheduler:
    def __init__(self):
        self.headers = {
            'Authorization': f'Bearer {self.get_token()}',
            'Content-Type': 'application/json',
            'Prefer': 'outlook.timezone="Asia/Kolkata"'
        }
        self.timezone = pytz.timezone(CONFIG['TIMEZONE'])
        self.now = datetime.datetime.now(datetime.timezone.utc)

    def get_token(self):
        token = os.getenv('token')
        return token

    def get_calendar_events(self, start_date=None, end_date=None):
        """Get calendar events with properly formatted dates"""
        if not start_date:
            # Get current time in UTC without microseconds
            start_date = datetime.datetime.now(timezone.utc).replace(microsecond=0)
            # Format as ISO with 'Z' suffix
            start_date = start_date.isoformat().replace('+00:00', 'Z')
    
        if not end_date:
            end_date = datetime.datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=CONFIG['LOOKAHEAD_DAYS'])
            end_date = end_date.isoformat().replace('+00:00', 'Z')

        url = f'https://graph.microsoft.com/v1.0/me/calendarView?startDateTime={start_date}&endDateTime={end_date}'
        print(f"Refresh URL: {url}")  # Debug output
    
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            events = response.json().get('value', [])
            print(f"Successfully refreshed calendar. Found {len(events)} events.")
            return events
        except requests.exceptions.HTTPError as e:
            print(f"Calendar refresh failed. Status: {e.response.status_code}")
            print(f"Error details: {e.response.text}")
            return []
        except Exception as e:
            print(f"Unexpected error during refresh: {str(e)}")
            return []

    def get_pending_invites(self):
        start_time = self.now.isoformat()
        end_time = (self.now + timedelta(days=CONFIG['LOOKAHEAD_DAYS'])).isoformat()
        url = f'https://graph.microsoft.com/v1.0/me/calendarView?startDateTime={start_time}&endDateTime={end_time}'
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return [
            e for e in response.json().get('value', [])
            if e['responseStatus']['response'] == 'notResponded'
        ]

    def is_conflicting(self, new_event, all_events):
        new_start = parser.isoparse(new_event['start']['dateTime'])
        new_end = parser.isoparse(new_event['end']['dateTime'])

        for event in all_events:
            if event['id'] == new_event['id']:
                continue
            start = parser.isoparse(event['start']['dateTime'])
            end = parser.isoparse(event['end']['dateTime'])

            if max(start, new_start) < min(end, new_end):
                return True
        return False

    def respond_to_invite(self, event_id, response_type, comment=None):
        url = f'https://graph.microsoft.com/v1.0/me/events/{event_id}/{response_type}'
        payload = {}
        if comment:
            payload['comment'] = comment

        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code == 202:
            print(f"{response_type.capitalize()}ed event: {event_id}")
        else:
            print(f"Failed to {response_type} event {event_id}. Error: {response.text}")

    def get_follow_up_required_emails(self):
        follow_ups = []
        try:
            with open(CONFIG['SUMMARY_CSV'], mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                for row in csv_reader:
                    if (row.get('follow_up_required', '').lower() == 'yes' and 
                        row.get('invite_send', '').lower() == 'no' and 
                        row.get('sender_email')):
                        follow_ups.append({
                            'email': row['sender_email'],
                            'subject': row.get('subject', 'Follow-up Discussion'),
                            'context': row.get('body', ''),
                            'row_data': row  # Store the entire row for later update
                        })
            return follow_ups
        except Exception as e:
            print(f"Error reading CSV file: {e}")
            return []

    def update_csv_row(self, original_row, field_to_update, new_value):
        try:
            # Read all rows
            rows = []
            with open(CONFIG['SUMMARY_CSV'], mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                fieldnames = csv_reader.fieldnames
                for row in csv_reader:
                    # Check if this is the row we need to update
                    if all(row[k] == original_row[k] for k in original_row if k in row):
                        row[field_to_update] = new_value
                    rows.append(row)
            
            # Write all rows back
            with open(CONFIG['SUMMARY_CSV'], mode='w', newline='') as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
                
        except Exception as e:
            print(f"Error updating CSV file: {e}")

    def is_working_day(self, date):
        return date.weekday() < 5

    def is_valid_slot(self, slot_start):
        # Ensure slot_start is timezone-aware
        if slot_start.tzinfo is None:
            slot_start = slot_start.replace(tzinfo=timezone.utc)

        if slot_start < self.now + timedelta(hours=CONFIG['MIN_SCHEDULE_NOTICE']):
            return False

        return True

    def find_available_slots(self, attendee_email):
        start_date = self.now
        end_date = self.now + timedelta(days=CONFIG['LOOKAHEAD_DAYS'])
        timeslots = self.get_working_time_slots(start_date, end_date)
    
        print(f"\nChecking availability for {attendee_email}")
        for slot in timeslots:
            # Convert time format to match working version
            clean_slot = {
                "start": {
                    "dateTime": slot['start']['dateTime'].replace('+05:30', ''),
                    "timeZone": slot['start']['timeZone']
                },
                "end": {
                    "dateTime": slot['end']['dateTime'].replace('+05:30', ''),
                    "timeZone": slot['end']['timeZone']
                }
            }
            print(f"slot {slot['start']['dateTime']} to {slot['end']['dateTime']}")
        
            payload = {
                "attendees": [{
                    "emailAddress": {
                        "address": attendee_email,
                        "name": attendee_email.split('@')[0]
                    },
                    "type": "required"
                }],
                "timeConstraint": {
                    "activityDomain": "work",
                    "timeslots": [clean_slot]
                },
                "meetingDuration": f"PT{CONFIG['MEETING_DURATION']}M",
                "minimumAttendeePercentage": 100,
                "isOrganizerOptional": False
            }
        
            try:
                response = requests.post(
                    "https://graph.microsoft.com/v1.0/me/findMeetingTimes",
                    headers=self.headers,
                    json=payload    
                )
                print(f"Response: {response.status_code} {response.text}")  # Debug output
                if response.status_code == 200:
                    suggestions = response.json().get('meetingTimeSuggestions', [])
                    if suggestions:
                        return [{
                            'start': slot['start']['dateTime'],  # Return original format
                            'end': slot['end']['dateTime'],
                            'confidence': suggestions[0].get('confidence', 0)
                        }]
        
            except Exception as e:
                print(f"Error checking slot: {str(e)}")
                continue
    
        return []

    def get_working_time_slots(self, start_date, end_date):
        slots = []
        tz = pytz.timezone(CONFIG['TIMEZONE'])

        # Convert input dates to the configured timezone
        start_date = start_date.astimezone(tz)
        end_date = end_date.astimezone(tz)

        current_date = start_date.date()
        end_date = end_date.date()

        while current_date <= end_date:
            if self.is_working_day(current_date):
                # Create timezone-aware datetime objects for the full working day
                day_start = tz.localize(datetime.datetime.combine(current_date, CONFIG['WORKING_HOURS']['start']))
                day_end = tz.localize(datetime.datetime.combine(current_date, CONFIG['WORKING_HOURS']['end']))

                slot_start = day_start
                while slot_start + timedelta(minutes=CONFIG['MEETING_DURATION']) <= day_end:
                    slot_end = slot_start + timedelta(minutes=CONFIG['MEETING_DURATION'])
                    if self.is_valid_slot(slot_start):
                        slots.append({
                            'start': {
                                'dateTime': slot_start.isoformat(),
                                'timeZone': CONFIG['TIMEZONE']
                            },
                            'end': {
                                'dateTime': slot_end.isoformat(),
                                'timeZone': CONFIG['TIMEZONE']
                            }
                        })
                    slot_start += timedelta(minutes=15)
            current_date += timedelta(days=1)

        return slots

    def schedule_meeting(self, attendee_email, start_time, end_time, subject, body=None):
        meeting_payload = {
            "subject": subject,
            "start": {
                "dateTime": start_time,
                "timeZone": CONFIG['TIMEZONE']
            },
            "end": {
                "dateTime": end_time,
                "timeZone": CONFIG['TIMEZONE']
            },
            "attendees": [{
                "emailAddress": {"address": attendee_email},
                "type": "required"
            }],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness"
        }

        if body:
            meeting_payload["body"] = {
                "contentType": "text",
                "content": body
            }

        url = "https://graph.microsoft.com/v1.0/me/events"
        response = requests.post(url, headers=self.headers, json=meeting_payload)

        if response.status_code == 201:
            print(f"✅ Meeting scheduled with {attendee_email} from {start_time} to {end_time}")
            return True
        else:
            print(f"❌ Failed to schedule meeting. Error: {response.text}")
            return False

    def is_mail_already_sent(self, sender_email, subject, body):
        """Check if the same email combination already exists in the sent mail CSV"""
        if not os.path.exists(CONFIG['SENT_MAIL_CSV']):
            return False
            
        try:
            with open(CONFIG['SENT_MAIL_CSV'], mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                for row in csv_reader:
                    if (row['sender_email'] == sender_email and 
                        row['subject'] == subject and 
                        row['body'] == body):
                        return True
            return False
        except Exception as e:
            print(f"Error checking sent mail CSV: {e}")
            return False

    def record_sent_mail(self, sender_email, subject, body):
        """Record the sent mail details in the CSV"""
        file_exists = os.path.exists(CONFIG['SENT_MAIL_CSV'])
        
        try:
            with open(CONFIG['SENT_MAIL_CSV'], mode='a', newline='') as csv_file:
                fieldnames = ['timestamp', 'sender_email', 'subject', 'body']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                    
                writer.writerow({
                    'timestamp': datetime.datetime.now().isoformat(),
                    'sender_email': sender_email,
                    'subject': subject,
                    'body': body
                })
        except Exception as e:
            print(f"Error recording sent mail: {e}")

    def process_pending_invites(self):
        all_events = self.get_calendar_events()
        pending_invites = self.get_pending_invites()

        for invite in pending_invites:
            if self.is_conflicting(invite, all_events):
                self.respond_to_invite(invite['id'], 'decline')
            else:
                self.respond_to_invite(invite['id'], 'accept')

    def process_follow_ups(self):
        follow_ups = self.get_follow_up_required_emails()
    
        for follow_up in follow_ups:
            try:
                sender_email = follow_up['email']
                subject = follow_up['subject']
                body = follow_up['context']
                
                print(f"\nProcessing follow-up with {sender_email}")
                
                # Check if this mail was already sent
                if self.is_mail_already_sent(sender_email, subject, body):
                    print("ℹ️ Meeting invite already sent for this email/subject/body combination. Skipping.")
                    continue
                    
                if sender_email.endswith('@shorthills.ai'):
                    available_slots = self.find_available_slots(sender_email)
                    
                    if not available_slots:
                        print("❌ No suitable slots available.")
                        continue
                    
                    # Schedule meeting
                    success = self.schedule_meeting(
                        attendee_email=sender_email,
                        start_time=available_slots[0]['start'],
                        end_time=available_slots[0]['end'],
                        subject=subject,
                        body=body
                    )
                    
                    if success:
                        # Record the sent mail in the CSV
                        self.record_sent_mail(sender_email, subject, body)
                        print("✅ Recorded sent mail in send_mail.csv")
                        
                        # Update the CSV to mark invite_send as 'yes'
                        self.update_csv_row(follow_up['row_data'], 'invite_send', 'yes')
                        print("✅ Updated Sumarize.csv to mark invite as sent")
                        
                        print("🔄 Refreshing calendar events...")
                        updated_events = self.get_calendar_events()
                        print(f"Found {len(updated_events)} events after refresh")
            
            except Exception as e:
                print(f"Error processing {sender_email}: {str(e)}")
                continue


if __name__ == "__main__":
    scheduler = MeetingScheduler()
    # print("🕒 Processing pending invites...")
    # scheduler.process_pending_invites()
    print("\n📅 Scheduling follow-ups...")
    scheduler.process_follow_ups()