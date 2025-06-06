import requests
import socket
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
 
# -------------------------
# Configuration
# -------------------------
 
CLIENT_ID = ""
CLIENT_SECRET = ""
TENANT_ID = ""
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPES = ['Files.ReadWrite.All', 'offline_access']
TOKEN_FILE = ''  # Will contain ONLY the most recent token
 
# -------------------------
# Token Management
# -------------------------
def save_token(token):
    """Overwrite token file with the new token"""
    # with open(TOKEN_FILE, 'w') as f:
    #     print("token==",token)
    #     f.write(token)
    print(token)
 
# -------------------------
# Step 1: Find free localhost port
# -------------------------
def find_free_port(start=8000, end=8100):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available port found")
 
redirect_port = find_free_port()
REDIRECT_URI = f'http://localhost:{redirect_port}/callback'
 
# -------------------------
# Step 2: Build Auth URL
# -------------------------
params = {
    'client_id': CLIENT_ID,
    'response_type': 'code',
    'redirect_uri': REDIRECT_URI,
    'response_mode': 'query',
    'scope': ' '.join(SCOPES)
}
auth_url = f"{AUTHORITY}/oauth2/v2.0/authorize?{urlencode(params)}"
 
# -------------------------
# Step 3: Setup redirect server to catch auth code
# -------------------------
class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/callback':
            code = parse_qs(parsed.query).get('code')
            if code:
                self.server.auth_code = code[0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write('✅ Authorization successful! You may close this window.'.encode('utf-8'))
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write('❌ Authorization code not found.'.encode('utf-8'))
 
    def log_message(self, format, *args):
        return  # Suppress console logs
 
# -------------------------
# Step 4: Open browser for login
# -------------------------
print(f"\n🔓 Opening browser for login. If it doesn't open, manually visit:\n{auth_url}\n")
try:
    webbrowser.open(auth_url)
except Exception:
    print("⚠️ Could not open browser. Please open this URL manually:\n", auth_url)
 
# -------------------------
# Step 5: Wait for the redirect with auth code
# -------------------------
print(f"⏳ Waiting for authentication callback on port {redirect_port}...")
server = HTTPServer(('localhost', redirect_port), RedirectHandler)
server.handle_request()
 
auth_code = getattr(server, 'auth_code', None)
if not auth_code:
    print("❌ Failed to retrieve auth code.")
    exit(1)
 
print("✅ Authorization code received!")
 
# -------------------------
# Step 6: Exchange auth code for access token
# -------------------------
token_url = f"{AUTHORITY}/oauth2/v2.0/token"
data = {
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'grant_type': 'authorization_code',
    'code': auth_code,
    'redirect_uri': REDIRECT_URI,
    'scope': ' '.join(SCOPES)
}
 
response = requests.post(token_url, data=data)
token_data = response.json()
 
# -------------------------
# Step 7: Save and Display Token
# -------------------------
access_token = token_data.get('access_token')
if access_token:
    save_token(access_token)  # Overwrites previous token
else:
    print("\n❌ Failed to retrieve access token.")
    print("Error details:")
    print(token_data)