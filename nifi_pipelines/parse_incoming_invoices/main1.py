#!/usr/bin/env python3
import requests,os
import base64, json
from copy import deepcopy
#from dot#env import load_dotenv
from datetime import datetime, timedelta
def helper(tmp,val):
    #deepcopy is used to create a new instance of the template_json
    tmp = deepcopy(tmp) 
    tmp['contents'][0]['parts'][0]['inline_data']['data'] = val
    return tmp
def main():
    #load_dotenv()
    template_json={
    "contents": [{
        "parts":[{"inline_data":
        {"mime_type": "application/pdf", "data":"BASE64_ENCODED_PDF_DATA"}},
        {"text": "Find the invoice number, total amount, Vendor GSTIN, Vendor addresss,Full Vendor name, GST Amount. Only respond in JSON, with these values"}
      ],}],
    "generationConfig": {
    "responseMimeType": "application/json",
    "responseSchema": {
      "type": "OBJECT",
      "properties": {
        "VendorName": { "type": "STRING" },
        "InvoiceAmt": { "type": "NUMBER" },
        "Date": { "type": "STRING" },
        "GSTIN": { "type": "STRING" },
        "VendorAddress": { "type": "STRING" },
        "GST": { "type": "NUMBER" },
        "TotalAmt": { "type": "NUMBER" }
      },
      "propertyOrdering": [
        "VendorName",
        "InvoiceAmt",
        "Date",
        "GSTIN",
        "VendorAddress",
        "GST",
        "TotalAmt"
      ]
    }
  }
}   
    GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
    CLIENT_ID = os.getenv('CLIENT_ID')
    CLIENT_SECRET = os.getenv('CLIENT_SECRET')
    tenant_id = os.getenv("TENANT_ID")
    refresh_token = os.getenv("refresh")
    # Define the token URL
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    SCOPES = ['User.Read', 'Mail.Read', 'offline_access','Files.ReadWrite.All']
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'scope': ' '.join(SCOPES)  # Replace SCOPES with your required scopes
    }
    config = {}
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
      with open('config.json', 'w') as f:json.dump(config, f)
        
    token=config.get('token',{}).get('access_token')
    last_execution=config.get('last_execution')
    token_expiry=config.get('token',{}).get('expires_in',0)
    if not last_execution: 
      today = datetime.now()
      if today.day >= 15:
          # Use current month and year
          target_date = datetime(today.year, today.month, 15)
      else:
          # Use previous month and year
          # Subtracting 15 days ensures we land in the previous month
          target_date = today - timedelta(days=15)
          target_date = datetime(target_date.year, target_date.month, 15)
      last_execution=target_date.timestamp()
      with open('config.json', 'w') as f:json.dump(config, f)

    if token_expiry and token_expiry < datetime.now().timestamp():
        response = requests.post(token_url, data=data)
        token = response.json()['access_token']
        token_expiry = datetime.now().timestamp() + response.json()['expires_in']
        config['token']={'access_token': token,'expires_in':token_expiry}
        config['last_execution']=last_execution
        with open('config.json', 'w') as f:json.dump(config, f)
   #use graph api to get all messages from inbox that contain 1 or more pdf attachments
    from urllib.parse import quote

    filter_datetime = datetime.fromtimestamp(last_execution).strftime('%Y-%m-%dT%H:%M:%SZ')
    endpoint = f"{GRAPH_API_URL}/me/messages?$filter=receivedDateTime gt {filter_datetime} and hasAttachments eq true&$select=id,receivedDateTime,hasAttachments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    response = requests.get(endpoint, headers=headers)
    messages = response.json().get('value', [])
    invoices = []
    messages = [message for message in messages if message.get('hasAttachments') == True]
   # print(messages)
    # Check if there are any messages
    if not messages:
        return
    last_execution = datetime.strptime(messages[0]['receivedDateTime'], "%Y-%m-%dT%H:%M:%SZ").timestamp()
    config['last_execution']=last_execution
    with open('config.json', 'w') as f:json.dump(config, f)
    for message in messages:
        message_id = message["id"]
        # Get attachments for the message using requests
        attachments_url = f"https://graph.microsoft.com/beta/me/messages/{message_id}?$expand=attachments"
        attachments_response = requests.get(attachments_url, headers=headers)
        #print(attachments_response.json())
        attachments = attachments_response.json().get('attachments', [])
        invoices += [helper(template_json, attachment['contentBytes']) for attachment in attachments if attachment['contentType'] == 'application/pdf']
    #format this list of dictionaries to a json
    print(json.dumps(invoices)) if invoices else print("")
if __name__ == "__main__":
    main()