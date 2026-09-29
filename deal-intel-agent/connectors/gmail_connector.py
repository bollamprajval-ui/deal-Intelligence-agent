"""
Real Gmail connector via the Gmail API. This is what actually connects to
a live inbox — the MailConnector in mail_connector.py reads local files
and is meant for offline testing / non-Gmail mail sources.

REQUIRED SETUP (one-time, per user):
  1. Go to Google Cloud Console -> create a project -> enable the Gmail API.
  2. Create OAuth 2.0 credentials (type: Desktop app). Download the JSON —
     this is your `credentials.json`, containing client_id + client_secret.
     This is NOT a simple API key; Gmail requires OAuth2 user consent.
  3. First run triggers a browser consent screen; approving it writes a
     `token.json` locally with a refresh token, so consent only happens once.
  4. Keep both files out of version control (.gitignore). They stay local,
     consistent with the local-first design — no credentials ever leave
     the device.

pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""
from pathlib import Path
from .base import BaseConnector, RawItem

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailConnector(BaseConnector):
    source_name = "mail"

    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if Path(self.token_path).exists():
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(self.token_path).write_text(creds.to_json())
        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def fetch_new(self, deal_id: str, query: str = None) -> list[RawItem]:
        """query: a Gmail search filter (e.g. 'from:client@acme.com newer_than:1d').
        The caller (matcher/main.py) doesn't need to know which deal a
        message belongs to in advance — pass a broad query and let the
        matcher's sender-email resolution figure it out."""
        service = self._get_service()
        results = service.users().messages().list(userId="me", q=query or "is:unread").execute()
        items = []
        for msg_ref in results.get("messages", []):
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
            items.append(self._to_raw_item(msg))
        return items

    def _to_raw_item(self, msg: dict) -> RawItem:
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = self._extract_body(msg["payload"])
        return RawItem(
            source=self.source_name,
            content=body,
            occurred_at=headers.get("Date", ""),
            message_id=headers.get("Message-ID"),
            in_reply_to=headers.get("In-Reply-To"),
            sender_email=self._parse_email(headers.get("From", "")),
            raw_ref=msg["id"],
        )

    def _extract_body(self, payload: dict) -> str:
        import base64
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
        return ""

    def _parse_email(self, from_header: str) -> str:
        if "<" in from_header:
            return from_header.split("<")[1].rstrip(">").strip()
        return from_header.strip()
