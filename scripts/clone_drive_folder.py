"""Clone a Google Drive folder into the local repository.

Usage:
    python scripts/clone_drive_folder.py

Requires credentials.json in the repo root (OAuth 2.0 client secrets
downloaded from the Google Cloud Console). On first run a browser window
will open for authorization; the token is cached in token.json afterward.
"""

import os
import sys

# Ensure the repo root is on the path so `src` is importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.google_drive import GoogleDriveClient  # noqa: E402

FOLDER_ID = "1HQyXJBn_9Gjx_TFB6mjmNTtEnFFwL5k_"
DEST = os.path.join(ROOT, "data", "drive")

if __name__ == "__main__":
    print(f"Cloning Drive folder {FOLDER_ID} → {DEST}")
    client = GoogleDriveClient(
        credentials_file=os.path.join(ROOT, "credentials.json"),
        token_file=os.path.join(ROOT, "token.json"),
    )
    client.clone_folder(folder_id=FOLDER_ID, dest=DEST)
    print("Done.")
