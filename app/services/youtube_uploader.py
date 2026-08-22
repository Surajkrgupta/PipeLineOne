"""Handles YouTube OAuth2 auth (one-time browser consent, then cached refresh
token) and video upload via the YouTube Data API v3.

SETUP (one-time, manual):
1. Go to Google Cloud Console -> create a project -> enable "YouTube Data API v3".
2. Create OAuth2 credentials (type: Desktop app) -> download as client_secret.json.
3. Place it at the path set in YT_CLIENT_SECRETS_FILE (./secrets/client_secret.json).
4. Run `python -m app.services.youtube_uploader` once locally -- it will open
   a browser for you to grant access, then cache a refresh token so future
   runs (including on a headless server) don't need browser interaction again.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploadError(Exception):
    pass


def _get_credentials() -> Credentials:
    creds = None
    token_path = settings.yt_token_file

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # first-time setup -- requires a browser, run this once locally/interactively
            flow = InstalledAppFlow.from_client_secrets_file(settings.yt_client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "27",  # 27 = Education
    privacy_status: str | None = None,
    thumbnail_path: str | None = None,
) -> str:
    """Uploads the video and returns the resulting YouTube video ID.
    If thumbnail_path is provided, also sets it as the custom thumbnail
    (otherwise YouTube auto-grabs a random frame, which looks unprofessional)."""
    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit
                "description": description[:5000],
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status or settings.yt_upload_privacy,
                "selfDeclaredMadeForKids": False,
                # Required disclosure for AI-generated/synthetic voiceover + visuals.
                # Skipping this risks YouTube's 3-strike inauthentic-content enforcement.
                "containsSyntheticMedia": True,
            },
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response["id"]

        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
                ).execute()
            except Exception as e:
                # Don't fail the whole upload over a thumbnail issue -- the video
                # is already live, just log it so it can be set manually if needed.
                print(f"Warning: thumbnail upload failed for video {video_id}: {e}")

        return video_id

    except Exception as e:
        raise YouTubeUploadError(f"YouTube upload failed: {e}") from e


if __name__ == "__main__":
    # Run this once to complete the OAuth2 consent flow interactively.
    _get_credentials()
    print("YouTube auth token cached successfully.")
