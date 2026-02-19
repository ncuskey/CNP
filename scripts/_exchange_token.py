"""Exchange the OAuth redirect URL for a token and save it (step 2 of 2)."""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from urllib.parse import parse_qs, urlparse
from google_auth_oauthlib.flow import Flow

REDIRECT_URL = sys.argv[1]

flow = Flow.from_client_secrets_file(
    os.path.join(ROOT, "credentials.json"),
    scopes=["https://www.googleapis.com/auth/drive"],
    redirect_uri="http://localhost",
)

parsed = urlparse(REDIRECT_URL)
code = parse_qs(parsed.query)["code"][0]
import requests as req_lib
session = req_lib.Session()
session.verify = False
flow.fetch_token(code=code, session=session)

token_path = os.path.join(ROOT, "token.json")
with open(token_path, "w") as f:
    f.write(flow.credentials.to_json())

print(f"Token saved to {token_path}")
