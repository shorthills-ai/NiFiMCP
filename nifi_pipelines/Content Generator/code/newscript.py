import requests
import socket
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import os
import sys
import csv


# Load environment variables
load_dotenv()

token= os.getenv("token")
CLIENT_ID = ""
CLIENT_SECRET = ""
TENANT_ID = ""

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
    print("Missing environment variables. Ensure CLIENT_ID, CLIENT_SECRET, and TENANT_ID are set in .env file.")
    sys.exit(1)

AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPES = ['offline_access', 'Files.ReadWrite.All']

# Excel file details
USER_EMAIL = "siddharth.anand@shorthills.ai"
ITEM_ID = ""
SHEET_NAME = "Sheet1"

# Helper: Find available port
def find_free_port(start=8000, end=8100):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available port")

redirect_port = find_free_port()
REDIRECT_URI = f'http://localhost:{redirect_port}/callback'

# Step 1: Build auth URL
params = {
    'client_id': CLIENT_ID,
    'response_type': 'code',
    'redirect_uri': REDIRECT_URI,
    'response_mode': 'query',
    'scope': ' '.join(SCOPES)
}
auth_url = f"{AUTHORITY}/oauth2/v2.0/authorize?{urlencode(params)}"

# Step 2: Temporary server for auth code
class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/callback':
            code = parse_qs(parsed.query).get('code')
            if code:
                self.server.auth_code = code[0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Auth successful! You can close this window.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b" Auth code not found.")
    def log_message(self, format, *args): return

# Step 3: Launch browser and start server
print(f"Login: {auth_url}")
# webbrowser.open(auth_url)
print(f"Waiting for auth on port {redirect_port}...")

access_token = os.getenv("token")

if not access_token:
    print("Token failure")
    print(access_token)
    sys.exit(1)

print("Access Token:")
print(access_token[:100] + "...")

# Step 5: Use Access Token to Read Excel Data
def get_excel_data(token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    graph_url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/drive/items/{ITEM_ID}/workbook/worksheets/{SHEET_NAME}/usedRange"
    response = requests.get(graph_url, headers=headers)

    if response.status_code == 200:
        print("📄 Excel Data:")
        rows = response.json().get("values", [])
        for row in rows:
            print(row)

        # Ensure output directory exists
        os.makedirs("output", exist_ok=True)

        # Save to CSV in output directory
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "output_excel_data.csv")
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        print(f"✅ Data saved to {output_file}")
    else:
        print(f"❌ Error fetching Excel data: {response.status_code}")
        print(response.text)

# Call it first time
excel_data = get_excel_data(access_token)

if access_token:
        get_excel_data(access_token)