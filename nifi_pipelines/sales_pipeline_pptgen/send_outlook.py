import sys
import os
import msal
import requests
from dotenv import load_dotenv
import argparse

load_dotenv()

# Read credentials from environment variables
CLIENT_ID = os.getenv("AZURE_CLIENT_ID2")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET2")
TENANT_ID = os.getenv("AZURE_TENANT_ID2")
USER_PRINCIPAL_NAME = os.getenv("ONEDRIVE_USER")  # e.g. "sales_demo_1_test@shorthills.ai"
FOLDER_NAME = os.getenv("FOLDER_NAME")

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, USER_PRINCIPAL_NAME]):
    print("Missing required environment variables.", file=sys.stderr)
    sys.exit(1)

# Parse command-line argument for file path
parser = argparse.ArgumentParser(description="Upload a file to OneDrive")
parser.add_argument("file_path", help="Path to the file to upload")
args = parser.parse_args()

file_path = args.file_path
if not os.path.exists(file_path):
    print(f"File not found: {file_path}", file=sys.stderr)
    sys.exit(1)

UPLOAD_FILENAME = os.path.basename(file_path)
with open(file_path, "rb") as f:
    pptx_bytes = f.read()

# Authenticate with MSAL
authority = f"https://login.microsoftonline.com/{TENANT_ID}"
scopes = ["https://graph.microsoft.com/.default"]
app = msal.ConfidentialClientApplication(
    client_id=CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=authority
)
result = app.acquire_token_for_client(scopes=scopes)
if "access_token" not in result:
    print("Error acquiring token:", result.get("error_description"), file=sys.stderr)
    sys.exit(1)
access_token = result["access_token"]

# Upload to OneDrive (user's root or specified folder) with the same filename
if FOLDER_NAME:
    print(f"Uploading to folder: {FOLDER_NAME}", file=sys.stderr)
    upload_url = f"https://graph.microsoft.com/v1.0/users/{USER_PRINCIPAL_NAME}/drive/root:/{FOLDER_NAME}/{UPLOAD_FILENAME}:/content"
else:
    print("Uploading to root folder", file=sys.stderr)
    upload_url = f"https://graph.microsoft.com/v1.0/users/{USER_PRINCIPAL_NAME}/drive/root:/{UPLOAD_FILENAME}:/content"

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/octet-stream"
}
response = requests.put(upload_url, headers=headers, data=pptx_bytes)

if response.status_code in [200, 201]:
    file_data = response.json()
    # Output the JSON response to stdout for NiFi or user
    sys.stdout.write(response.text)
    sys.stdout.flush()
else:
    print(f"Error uploading file: {response.status_code} - {response.text}", file=sys.stderr)
    sys.exit(1)
    