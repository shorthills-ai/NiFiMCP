import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")

# Load environment variables if available
load_dotenv()

# Credentials - can be overridden by environment variables
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
TENANT_ID = os.getenv("TENANT_ID", "")
DYNAMICS_URL = "https://shorthills.crm.dynamics.com/api/data/v9.2"
SCOPE = "https://shorthills.crm.dynamics.com/.default"

# Default owner for marketing emails - can be overridden by environment variable
DEFAULT_OWNER_ID = os.getenv("DEFAULT_EMAIL_OWNER_ID", "")

def get_access_token():
    """Get access token from Microsoft identity platform"""
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': SCOPE
    }
    
    print("Requesting access token...")
    response = requests.post(token_url, data=token_data)
    
    if response.status_code == 200:
        token_response = response.json()
        token = token_response['access_token']
        print("Token successfully obtained!")
        return token
    else:
        print(f"Error getting token: {response.status_code}")
        print(response.text)
        return None

def create_marketing_email(access_token, title, subject, body, from_email):
    """Create a marketing email in Dynamics 365 Marketing using msdynmkt_email table"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0',
        'Accept': 'application/json'
    }
    
    # Prepare marketing email data for msdynmkt_email table
    email_data = {
        'msdynmkt_name': title,  # Name of the marketing email
        'msdynmkt_subject': subject,  # Email subject
        'msdynmkt_messagedesignation': 534120000,  # Commercial (534120000) or Transactional (534120001)
        'msdynmkt_description': f'Marketing email created via API - From: {from_email}',
        'msdynmkt_emailbody': body,  # Email body content
        'msdynmkt_designerhtml': body,  # Designer HTML (might be the field used by the UI)
        'msdynmkt_previewhtml': body,  # Preview HTML
        'msdynmkt_emailcontenttype': 534120000,  # Standard email content type (not double opt-in)
        'msdynmkt_emailcontentlanguage': 1033,  # English (US)
        'msdynmkt_fromemail': from_email,  # From email address
        'msdynmkt_fromname': 'AI Daily Scoop News',  # From name (display name)
        'ownerid@odata.bind': f'/systemusers({DEFAULT_OWNER_ID})',  # Set specific user as owner
        'statecode': 0,  # Active state
        'statuscode': 1  # Draft status
    }
    
    # Create the marketing email
    url = f"{DYNAMICS_URL}/msdynmkt_emails"
    
    print(f"Creating marketing email: {title}")
    print(f"Subject: {subject}")
    print(f"From: {from_email}")
    print(f"Owner: {DEFAULT_OWNER_ID}")
    print(f"Making POST request to: {url}")
    
    response = requests.post(url, headers=headers, data=json.dumps(email_data))
    
    if response.status_code == 204:
        # Get the created email ID from the response headers
        email_id = response.headers.get('OData-EntityId', '').split('(')[-1].split(')')[0]
        print(f"✅ Marketing email created successfully!")
        print(f"Email ID: {email_id}")
        return email_id
    else:
        print(f"❌ Error creating marketing email: {response.status_code}")
        print("Response:", response.text)
        return None

def update_marketing_email(access_token, email_id, title, subject, body, from_email):
    """Update an existing marketing email in Dynamics 365 Marketing"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0',
        'Accept': 'application/json'
    }
    
    # Prepare updated marketing email data
    email_data = {
        'msdynmkt_name': title,  # Name of the marketing email
        'msdynmkt_subject': subject,  # Email subject
        'msdynmkt_messagedesignation': 534120000,  # Commercial (534120000) or Transactional (534120001)
        'msdynmkt_description': f'Marketing email updated via API - From: {from_email}',
        'msdynmkt_emailbody': body,  # Email body content
        'msdynmkt_designerhtml': body,  # Designer HTML (might be the field used by the UI)
        'msdynmkt_previewhtml': body,  # Preview HTML
        'msdynmkt_emailcontenttype': 534120000,  # Standard email content type (not double opt-in)
        'msdynmkt_emailcontentlanguage': 1033,  # English (US)
        'msdynmkt_fromemail': from_email,  # From email address
        'msdynmkt_fromname': 'AI Daily Scoop News',  # From name (display name)
        'ownerid@odata.bind': f'/systemusers({DEFAULT_OWNER_ID})',  # Set specific user as owner
        'statecode': 0,  # Active state
        'statuscode': 1  # Draft status
    }
    
    # Update the marketing email using PATCH
    url = f"{DYNAMICS_URL}/msdynmkt_emails({email_id})"
    
    print(f"Updating marketing email ID: {email_id}")
    print(f"New Title: {title}")
    print(f"New Subject: {subject}")
    print(f"From: {from_email}")
    print(f"Owner: {DEFAULT_OWNER_ID}")
    print(f"Making PATCH request to: {url}")
    
    response = requests.patch(url, headers=headers, data=json.dumps(email_data))
    
    if response.status_code == 204:
        print(f"✅ Marketing email updated successfully!")
        print(f"Email ID: {email_id}")
        return email_id
    else:
        print(f"❌ Error updating marketing email: {response.status_code}")
        print("Response:", response.text)
        return None

def verify_email_content(access_token, email_id):
    """Retrieve and verify the created marketing email content"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0'
    }
    
    url = f"{DYNAMICS_URL}/msdynmkt_emails({email_id})"
    
    print(f"Verifying email content for ID: {email_id}")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        email_data = response.json()
        print(f"✅ Email retrieved successfully!")
        print(f"📧 Name: {email_data.get('msdynmkt_name', 'N/A')}")
        print(f"📝 Subject: {email_data.get('msdynmkt_subject', 'N/A')}")
        print(f"📧 From Email: {email_data.get('msdynmkt_fromemail', 'N/A')}")
        print(f"👤 From Name: {email_data.get('msdynmkt_fromname', 'N/A')}")
        print(f"👤 Owner ID: {email_data.get('_ownerid_value', 'N/A')}")
        
        # Check various possible body field names
        body_content = (
            email_data.get('msdynmkt_emailbody') or 
            email_data.get('body') or 
            email_data.get('msdynmkt_body') or 
            email_data.get('description') or
            email_data.get('msdynmkt_description')
        )
        
        if body_content:
            print(f"📄 Body Content: Found ({len(body_content)} characters)")
            print(f"📄 Body Preview: {body_content[:100]}...")
        else:
            print("❌ No body content found in any expected field")
        
        print("\n🔍 All available fields in the email record:")
        for key, value in sorted(email_data.items()):
            if value is not None and str(value).strip():
                print(f"  - {key}: {str(value)[:100]}...")
            else:
                print(f"  - {key}: (empty/null)")
        
        return email_data
    else:
        print(f"❌ Error retrieving email: {response.status_code}")
        print("Response:", response.text)
        return None

def get_email_status(access_token, email_id):
    """Get current email status and state"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0'
    }
    
    url = f"{DYNAMICS_URL}/msdynmkt_emails({email_id})?$select=statecode,statuscode,msdynmkt_name,msdynmkt_subject"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        email_data = response.json()
        return {
            'statecode': email_data.get('statecode'),
            'statuscode': email_data.get('statuscode'),
            'name': email_data.get('msdynmkt_name'),
            'subject': email_data.get('msdynmkt_subject')
        }
    else:
        print(f"❌ Error getting email status: {response.status_code}")
        print("Response:", response.text)
        return None

def set_email_ready_to_send(access_token, email_id):
    """Set email status to Ready to Send"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0',
        'Accept': 'application/json'
    }
    
    # Update status to Ready to Send
    status_data = {
        'statecode': 0,  # Active
        'statuscode': 2  # Ready to Send
    }
    
    url = f"{DYNAMICS_URL}/msdynmkt_emails({email_id})"
    
    print(f"🔄 Setting email to 'Ready to Send' status...")
    response = requests.patch(url, headers=headers, data=json.dumps(status_data))
    
    if response.status_code == 204:
        print(f"✅ Email status updated to 'Ready to Send'!")
        return True
    else:
        print(f"❌ Error updating email status: {response.status_code}")
        print("Response:", response.text)
        return False

def search_existing_emails(access_token, search_term=None):
    """Search for existing marketing emails"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0'
    }
    
    # Search for emails
    if search_term:
        url = f"{DYNAMICS_URL}/msdynmkt_emails?$select=msdynmkt_emailid,msdynmkt_name,msdynmkt_subject,statecode,statuscode&$filter=contains(msdynmkt_name,'{search_term}') or contains(msdynmkt_subject,'{search_term}')"
    else:
        url = f"{DYNAMICS_URL}/msdynmkt_emails?$select=msdynmkt_emailid,msdynmkt_name,msdynmkt_subject,statecode,statuscode&$top=20"
    
    print(f"🔍 Searching for existing emails...")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        emails = response.json().get('value', [])
        print(f"📋 Found {len(emails)} emails:")
        
        for email in emails:
            email_name = email.get('msdynmkt_name', 'Unknown')
            email_subject = email.get('msdynmkt_subject', 'No subject')
            email_id = email.get('msdynmkt_emailid', 'Unknown')
            state = email.get('statecode', 'Unknown')
            status = email.get('statuscode', 'Unknown')
            print(f"  - {email_name}")
            print(f"    Subject: {email_subject}")
            print(f"    ID: {email_id}")
            print(f"    Status: State={state}, Code={status}")
            print()
        
        return emails
    else:
        print(f"❌ Error searching for emails: {response.status_code}")
        print("Response:", response.text)
        return []

def main():
    """Main function to create or update a marketing email"""
    print("=== Marketing Email Creator/Updater ===")
    
    # Get access token
    access_token = get_access_token()
    if not access_token:
        print("Failed to get access token. Exiting.")
        return
    
    # Search for existing AI Digest emails
    print("\n🔍 Searching for existing AI Digest emails...")
    existing_ai_digest_emails = search_existing_emails(access_token, "AI Digest - Your Daily AI News Newsletter")
    
    # Marketing email details
    title = "AI Digest - "+today
    subject = "The Latest in AI: What You Need to Know"
    from_email = "ainews@getshorthills.com"
    
    # AI Digest newsletter HTML template
    with open('/home/nifi/nifi2/ainews/ai_news_system/output3/ndtv_news.html') as f:x=f.read()
    body = x
    if 1==2:
        print(f"\n✅ Found existing AI Digest email with ID: {existing_ai_digest_emails[0].get('msdynmkt_emailid')}")
        email_id = existing_ai_digest_emails[0].get('msdynmkt_emailid')
        
        # Update the existing marketing email
        print(f"\n🔄 Updating existing email template...")
        updated_email_id = update_marketing_email(access_token, email_id, title, subject, body, from_email)
        
        if updated_email_id:
            print(f"\n🎉 Marketing email '{title}' has been updated successfully!")
            print(f"📧 From: {from_email} (AI Daily Scoop News)")
            print(f"📝 Subject: {subject}")
            print(f"🆔 Email ID: {email_id}")
            print(f"📄 Body: HTML content with styling")
            print(f"🏷️  Message Type: Commercial Marketing Email")
            
            # Verify the email content and final status
            print(f"\n🔍 Verifying updated email content and status...")
            verify_email_content(access_token, email_id)
            
            # Check final status
            final_status = get_email_status(access_token, email_id)
            if final_status:
                status_names = {
                    1: "Draft",
                    2: "Ready to Send", 
                    3: "Error",
                    4: "Stopped",
                    5: "Sending",
                    6: "Sent"
                }
                status_name = status_names.get(final_status['statuscode'], f"Unknown ({final_status['statuscode']})")
                print(f"\n📊 Final Email Status: {status_name}")
            
            print(f"\n💡 NEXT STEPS:")
            print(f"   1. ✅ Email has been updated with new content")
            print(f"   2. Email is ready to use in marketing journeys")
            print(f"   3. Monitor email performance and engagement")
            
            print(f"\nThe existing marketing email template has been updated in your Dynamics 365 Marketing system.")
        else:
            print("\n❌ Failed to update marketing email.")
    else:
        print("\n❌ No existing AI Digest email found. Creating a new one...")
        
        # Create a new marketing email
        print(f"\n🔄 Creating new marketing email...")
        new_email_id = create_marketing_email(access_token, title, subject, body, from_email)
        
        if new_email_id:
            print(f"\n🎉 New marketing email '{title}' has been created successfully!")
            print(f"📧 From: {from_email} (AI Daily Scoop News)")
            print(f"📝 Subject: {subject}")
            print(f"🆔 Email ID: {new_email_id}")
            print(f"📄 Body: HTML content with styling")
            print(f"🏷️  Message Type: Commercial Marketing Email")
            
            # Verify the email content and final status
            print(f"\n🔍 Verifying new email content and status...")
            verify_email_content(access_token, new_email_id)
            
            # Check final status
            final_status = get_email_status(access_token, new_email_id)
            if final_status:
                status_names = {
                    1: "Draft",
                    2: "Ready to Send",
                    3: "Error",
                    4: "Stopped",
                    5: "Sending",
                    6: "Sent"
                }
                status_name = status_names.get(final_status['statuscode'], f"Unknown ({final_status['statuscode']})")
                print(f"\n📊 Final Email Status: {status_name}")
            
            print(f"\n💡 NEXT STEPS:")
            print(f"   1. ✅ Email has been created with new content")
            print(f"   2. Email is ready to use in marketing journeys")
            print(f"   3. Monitor email performance and engagement")
            
            print(f"\nThe new marketing email template has been created in your Dynamics 365 Marketing system.")
        else:
            print("\n❌ Failed to create marketing email.")

if __name__ == "__main__":
    main() 
