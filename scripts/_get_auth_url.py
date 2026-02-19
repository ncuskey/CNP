"""Print the OAuth authorization URL (step 1 of 2)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from google_auth_oauthlib.flow import Flow

flow = Flow.from_client_secrets_file(
    os.path.join(ROOT, "credentials.json"),
    scopes=["https://www.googleapis.com/auth/drive"],
    redirect_uri="http://localhost",
)
url, _ = flow.authorization_url(access_type="offline", prompt="consent")
print(url)
