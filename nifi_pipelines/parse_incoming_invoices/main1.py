#!/usr/bin/env python3
import requests,os
import base64, json
from datetime import datetime, timedelta
def main():
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
    CLIENT_ID = os.getenv('CLIENT_ID')
    CLIENT_SECRET = os.getenv('CLIENT_SECRET')
    token_url = 'https://api.example.com/token'
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
    config={}
    with open('config.json', 'r') as f:config=json.load(f)
    token=config.get('token',{}).get('access_token')
    last_execution=config.get('last_execution')
    token_expiry=config.get('token',{}).get('expires_in')
    if not last_execution:
        last_execution=datetime.now().strftime("%Y-%m-%d")+"T00:00:00Z"
    with open('config.json', 'w') as f:json.dump(config, f)

    if not token or token_expiry < datetime.now():
        # Make the request
        last_execution = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        response = requests.post(token_url, data=data)
        token = response.json()['access_token']
        token_expiry = datetime.now() + timedelta(seconds=response.json()['expires_in'])
        config['token']['access_token'] = token
        config['token']['expires_in'] = response.json()['expires_in']
        config['last_execution']=last_execution
        with open('config.json', 'w') as f:json.dump(config, f)
   #use graph api to get all messages from inbox that contain 1 or more pdf attachments
    endpoint =f"/me/messages?$filter=receivedDateTime ge {last_execution} and hasAttachments eq true"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    response = requests.get(endpoint, headers=headers)
    messages = response.json()['value']
    invoices = []
    for message in messages:
        message_id = message["id"]
        # Get attachments for the message using requests
        attachments_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"
        attachments_response = requests.get(attachments_url, headers=headers)
        attachments = attachments_response.json().get("value", [])

        for attachment in attachments:
            if attachment.get("contentType") == "application/pdf":
                attachment_id = attachment["id"]
                attachment_name = attachment["name"]
                # Download PDF content using requests
                content_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/{attachment_id}/$value"
                content_response = requests.get(content_url, headers=headers)
                content = content_response.content
                # get base64 encoded pdf data and add to template_json and append it to invoices
                templ=template_json.copy()
                templ['contents'][0]['parts'][0]['inline_data']['data'] = base64.b64encode(content).decode('utf-8')
                invoices.append(templ)
    print(invoices)
    return invoices
if __name__ == "__main__":
    print(main())