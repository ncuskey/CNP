"""Google Drive file access using OAuth 2.0."""

import io
import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
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
        self._service = build("drive", "v3", credentials=self._authenticate())

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
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(self._token_file, "w") as token:
                token.write(creds.to_json())

        return creds

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
