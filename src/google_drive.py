"""Google Drive file access using OAuth 2.0."""

import io
import os
from typing import Optional

# Google Workspace MIME types cannot be downloaded directly; they must be
# exported to a portable format. This map defines the export target and the
# file extension to append to the downloaded file.
WORKSPACE_EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
    "application/vnd.google-apps.script": ("application/vnd.google-apps.script+json", ".json"),
}

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# Scopes required for listing, reading, and uploading files.
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Default paths for OAuth credentials and cached token.
DEFAULT_CREDENTIALS_FILE = "credentials.json"
DEFAULT_TOKEN_FILE = "token.json"


class GoogleDriveClient:
    """Client for interacting with Google Drive via the Drive API v3.

    Handles OAuth 2.0 authentication and provides methods to list,
    download, and upload files.

    Usage:
        client = GoogleDriveClient()
        files = client.list_files()
        content = client.download_file(file_id="<id>")
        client.upload_file(local_path="report.pdf", name="report.pdf")
        client.clone_folder(folder_id="<id>", dest="local/path")
    """

    def __init__(
        self,
        credentials_file: str = DEFAULT_CREDENTIALS_FILE,
        token_file: str = DEFAULT_TOKEN_FILE,
    ) -> None:
        """Initialize the client and authenticate.

        Args:
            credentials_file: Path to the OAuth 2.0 client secrets JSON
                file downloaded from the Google Cloud Console.
            token_file: Path where the cached user token is stored after
                the first successful OAuth flow.
        """
        self._credentials_file = credentials_file
        self._token_file = token_file
        creds = self._authenticate()
        # Use an httplib2 transport with SSL verification disabled to support
        # proxied/sandboxed environments that present self-signed certificates.
        http = AuthorizedHttp(creds, http=httplib2.Http(disable_ssl_certificate_validation=True))
        self._service = build("drive", "v3", http=http)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> Credentials:
        """Return valid OAuth 2.0 credentials, refreshing or re-authorizing as needed."""
        creds: Optional[Credentials] = None

        if os.path.exists(self._token_file):
            creds = Credentials.from_authorized_user_file(self._token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                import requests
                session = requests.Session()
                session.verify = False
                creds.refresh(Request(session=session))
            else:
                creds = self._run_auth_flow()
            with open(self._token_file, "w") as token:
                token.write(creds.to_json())

        return creds

    def _run_auth_flow(self) -> Credentials:
        """Interactive OAuth flow suitable for headless/remote environments.

        Prints an authorization URL, waits for the user to visit it and
        authorize, then asks them to paste back the redirect URL (which
        looks like ``http://localhost/?code=4/0A...&scope=...``).
        The authorization code is extracted from that URL and exchanged
        for credentials.
        """
        from urllib.parse import parse_qs, urlparse

        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            self._credentials_file,
            scopes=SCOPES,
            redirect_uri="http://localhost",
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        print("\n" + "=" * 60)
        print("Authorize this app by visiting:\n")
        print(f"  {auth_url}")
        print(
            "\nAfter authorizing, your browser will redirect to a URL that\n"
            "starts with http://localhost/?code=... and may show an error\n"
            "page — that is expected.\n"
            "Copy the full URL from your browser's address bar and paste it below."
        )
        print("=" * 60 + "\n")

        redirect_response = input("Paste the full redirect URL here: ").strip()
        parsed = urlparse(redirect_response)
        code = parse_qs(parsed.query).get("code", [None])[0]
        if not code:
            raise ValueError(
                f"Could not extract authorization code from URL: {redirect_response!r}"
            )

        import requests
        session = requests.Session()
        session.verify = False
        flow.fetch_token(code=code, session=session)
        return flow.credentials

    # ------------------------------------------------------------------
    # List files
    # ------------------------------------------------------------------

    def list_files(
        self,
        query: Optional[str] = None,
        page_size: int = 100,
        fields: str = "files(id, name, mimeType, size, modifiedTime)",
    ) -> list[dict]:
        """List files in the authenticated user's Google Drive.

        Args:
            query: Optional Drive query string (e.g. ``"name contains 'report'"``).
                See https://developers.google.com/drive/api/guides/search-files
                for the full query syntax.
            page_size: Maximum number of files to return per page (1–1000).
            fields: Comma-separated Drive API fields to include in the response.

        Returns:
            A list of file metadata dicts with the requested fields.
        """
        results = []
        page_token: Optional[str] = None

        while True:
            kwargs: dict = {
                "pageSize": page_size,
                "fields": f"nextPageToken, {fields}",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if query:
                kwargs["q"] = query
            if page_token:
                kwargs["pageToken"] = page_token

            response = self._service.files().list(**kwargs).execute()
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results

    # ------------------------------------------------------------------
    # Download / read
    # ------------------------------------------------------------------

    def download_file(self, file_id: str) -> bytes:
        """Download a file's binary content from Google Drive.

        For Google Workspace documents (Docs, Sheets, Slides) use
        ``export_file`` instead, which converts them to a portable format.

        Args:
            file_id: The Drive file ID.

        Returns:
            The raw file content as bytes.
        """
        request = self._service.files().get_media(
            fileId=file_id, supportsAllDrives=True
        )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def export_file(self, file_id: str, mime_type: str = "text/plain") -> bytes:
        """Export a Google Workspace document to the specified MIME type.

        Use this for Google Docs, Sheets, or Slides files, which cannot be
        downloaded with ``download_file``.

        Args:
            file_id: The Drive file ID.
            mime_type: Target export MIME type (e.g. ``"application/pdf"``,
                ``"text/csv"``, ``"text/plain"``).

        Returns:
            The exported file content as bytes.
        """
        request = self._service.files().export_media(
            fileId=file_id, mimeType=mime_type
        )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Upload / write
    # ------------------------------------------------------------------

    def upload_file(
        self,
        local_path: str,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
        parent_folder_id: Optional[str] = None,
    ) -> dict:
        """Upload a local file to Google Drive.

        Args:
            local_path: Path to the local file to upload.
            name: Name to give the file in Drive. Defaults to the local
                filename if not provided.
            mime_type: MIME type of the file. Auto-detected by the API
                when omitted.
            parent_folder_id: ID of the Drive folder to upload into.
                Uploads to the root of My Drive if omitted.

        Returns:
            File metadata dict containing at minimum ``id`` and ``name``.
        """
        file_name = name or os.path.basename(local_path)
        metadata: dict = {"name": file_name}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]

        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        file = (
            self._service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute()
        )
        return file

    def update_file(
        self,
        file_id: str,
        local_path: str,
        mime_type: Optional[str] = None,
    ) -> dict:
        """Replace the content of an existing Drive file.

        Args:
            file_id: The Drive file ID to update.
            local_path: Path to the local file whose content will replace
                the existing Drive file content.
            mime_type: MIME type of the replacement content.

        Returns:
            Updated file metadata dict containing at minimum ``id`` and ``name``.
        """
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        file = (
            self._service.files()
            .update(
                fileId=file_id,
                media_body=media,
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute()
        )
        return file

    # ------------------------------------------------------------------
    # Clone folder
    # ------------------------------------------------------------------

    def clone_folder(self, folder_id: str, dest: str) -> None:
        """Recursively download a Google Drive folder into a local directory.

        The local directory tree mirrors the Drive folder structure exactly.
        Google Workspace files (Docs, Sheets, Slides, etc.) are exported to
        their Office-compatible equivalents and saved with an appropriate
        extension. Files that cannot be exported are skipped with a warning.

        Args:
            folder_id: The Drive ID of the folder to clone.
            dest: Local directory path where the folder contents will be
                written. Created if it does not exist.
        """
        os.makedirs(dest, exist_ok=True)
        self._clone_folder_recursive(folder_id, dest)

    def _clone_folder_recursive(self, folder_id: str, local_dir: str) -> None:
        """Walk a Drive folder and write its contents into *local_dir*."""
        items = self._list_folder_children(folder_id)
        for item in items:
            mime = item["mimeType"]
            name = item["name"]
            item_id = item["id"]

            if mime == FOLDER_MIME_TYPE:
                sub_dir = os.path.join(local_dir, name)
                os.makedirs(sub_dir, exist_ok=True)
                self._clone_folder_recursive(item_id, sub_dir)
            else:
                self._save_file(item_id, name, mime, local_dir)

    def _list_folder_children(self, folder_id: str) -> list[dict]:
        """Return all direct children of a Drive folder, auto-paginating."""
        results = []
        page_token: Optional[str] = None
        query = f"'{folder_id}' in parents and trashed = false"

        while True:
            kwargs: dict = {
                "q": query,
                "pageSize": 100,
                "fields": "nextPageToken, files(id, name, mimeType)",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            response = self._service.files().list(**kwargs).execute()
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results

    def _save_file(
        self, file_id: str, name: str, mime: str, local_dir: str
    ) -> None:
        """Download or export a single Drive file into *local_dir*."""
        if mime in WORKSPACE_EXPORT_FORMATS:
            export_mime, ext = WORKSPACE_EXPORT_FORMATS[mime]
            local_name = name if name.endswith(ext) else name + ext
            local_path = os.path.join(local_dir, local_name)
            try:
                content = self.export_file(file_id, export_mime)
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: could not export '{name}' ({mime}): {exc}")
                return
        elif mime.startswith("application/vnd.google-apps."):
            # Unknown Workspace type with no export mapping — skip.
            print(f"Warning: skipping unsupported Workspace file '{name}' ({mime})")
            return
        else:
            local_path = os.path.join(local_dir, name)
            try:
                content = self.download_file(file_id)
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: could not download '{name}': {exc}")
                return

        with open(local_path, "wb") as fh:
            fh.write(content)
        print(f"  {local_path}")
