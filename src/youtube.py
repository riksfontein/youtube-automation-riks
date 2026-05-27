"""
youtube.py — YouTube Data API v3 upload module.
Uploads video as unlisted with metadata and thumbnail.
Uses per-channel refresh tokens and channel IDs from state.
"""

import os
import time
import json
import requests
from pathlib import Path
from typing import Optional

YOUTUBE_CLIENT_ID     = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]

TOKEN_URL    = "https://oauth2.googleapis.com/token"
YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE  = "https://www.googleapis.com/upload/youtube/v3"

CHANNEL_CATEGORY_IDS = {
    "AE":  "28",  # Science & Technology
    "GIA": "25",  # News & Politics
    "BF":  "27",  # Education
}

CHANNEL_YOUTUBE_IDS = {
    "AE":  "UCzazMPj4dWuXuLj74aVu9WQ",
    "GIA": "UCrNSYDPBcQRNzpJlA3hEXnA",
    "BF":  "UCvFKEzLIek3v05fqvAQbudA",
}

# Per-channel refresh token env var names
CHANNEL_TOKEN_SECRETS = {
    "AE":  "YOUTUBE_REFRESH_TOKEN_AE",
    "GIA": "YOUTUBE_REFRESH_TOKEN_GIA",
    "BF":  "YOUTUBE_REFRESH_TOKEN_BF",
}

# Token cache per channel
_token_cache = {}


def _get_refresh_token(channel: str) -> str:
    """Get the refresh token for a specific channel."""
    secret_name = CHANNEL_TOKEN_SECRETS.get(channel)
    token = os.environ.get(secret_name, "")
    if not token:
        # Fallback to main token
        token = os.environ.get("YOUTUBE_REFRESH_TOKEN_MAIN", "")
    if not token:
        raise RuntimeError(
            f"No refresh token found for channel {channel}. "
            f"Add {secret_name} to GitHub Secrets."
        )
    return token


def _get_access_token(channel: str) -> str:
    """Get a valid access token for a channel, refreshing if needed."""
    now = time.time()
    cached = _token_cache.get(channel, {})

    if cached.get("token") and now < cached.get("expires_at", 0) - 60:
        return cached["token"]

    refresh_token = _get_refresh_token(channel)

    resp = requests.post(TOKEN_URL, data={
        "client_id":     YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token"
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        raise RuntimeError(
            f"Failed to get access token for {channel}: {data}"
        )

    _token_cache[channel] = {
        "token":      data["access_token"],
        "expires_at": now + int(data.get("expires_in", 3600))
    }
    print(f"[YouTube] Access token refreshed for {channel}")
    return _token_cache[channel]["token"]


def _auth_headers(channel: str) -> dict:
    return {"Authorization": f"Bearer {_get_access_token(channel)}"}


def verify_channel_access(channel: str) -> Optional[str]:
    """
    Verify the token can access the correct YouTube channel.
    Returns the channel title if correct, None if there is a mismatch.
    """
    expected_id = CHANNEL_YOUTUBE_IDS.get(channel)
    headers = {**_auth_headers(channel), "Content-Type": "application/json"}

    try:
        resp = requests.get(
            f"{YOUTUBE_BASE}/channels",
            headers=headers,
            params={"part": "snippet", "mine": "true"},
            timeout=30
        )
        resp.raise_for_status()
        channels = resp.json().get("items", [])

        for ch in channels:
            ch_id    = ch.get("id", "")
            ch_title = ch.get("snippet", {}).get("title", "")
            print(f"[YouTube] Token gives access to: {ch_title} ({ch_id})")
            if ch_id == expected_id:
                print(f"[YouTube] ✓ Channel match confirmed for {channel}")
                return ch_title

        print(f"[YouTube] WARNING: Expected channel ID {expected_id} not found in token's channels")
        print(f"[YouTube] Available channels: {[c.get('id') for c in channels]}")
        return None

    except Exception as e:
        print(f"[YouTube] Channel verification error: {e}")
        return None


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    channel: str,
    thumbnail_path: Optional[str] = None
) -> dict:
    """
    Upload video to YouTube as unlisted.
    Returns dict with video_id and studio_url.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size   = video_path.stat().st_size
    category_id = CHANNEL_CATEGORY_IDS.get(channel, "28")

    print(f"[YouTube] Channel: {channel} ({CHANNEL_YOUTUBE_IDS.get(channel)})")
    print(f"[YouTube] Uploading: {video_path.name}")
    print(f"[YouTube] Size: {file_size / (1024*1024):.1f} MB")
    print(f"[YouTube] Title: {title}")

    # Verify channel access first
    verified = verify_channel_access(channel)
    if not verified:
        print(f"[YouTube] WARNING: Could not verify channel access. Proceeding anyway.")

    metadata = {
        "snippet": {
            "title":       title[:100],
            "description": description[:5000],
            "tags":        tags[:15],
            "categoryId":  category_id
        },
        "status": {
            "privacyStatus":           "unlisted",
            "selfDeclaredMadeForKids": False
        }
    }

    # Initiate resumable upload
    init_headers = {
        "Authorization":           f"Bearer {_get_access_token(channel)}",
        "Content-Type":            "application/json",
        "X-Upload-Content-Type":   "video/mp4",
        "X-Upload-Content-Length": str(file_size)
    }

    init_resp = requests.post(
        f"{UPLOAD_BASE}/videos?uploadType=resumable&part=snippet,status",
        headers=init_headers,
        data=json.dumps(metadata),
        timeout=30
    )
    init_resp.raise_for_status()

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("[YouTube] No upload URL in response")

    print(f"[YouTube] Uploading video file...")

    # Upload file
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            data=f,
            headers={
                "Content-Type":   "video/mp4",
                "Content-Length": str(file_size)
            },
            timeout=600
        )
    upload_resp.raise_for_status()

    video_data = upload_resp.json()
    video_id   = video_data.get("id")

    if not video_id:
        raise RuntimeError(f"[YouTube] No video ID in response: {video_data}")

    print(f"[YouTube] Uploaded successfully: {video_id}")

    studio_url = f"https://studio.youtube.com/video/{video_id}/edit"
    watch_url  = f"https://www.youtube.com/watch?v={video_id}"

    # Upload Thumbnail A
    if thumbnail_path and Path(thumbnail_path).exists():
        upload_thumbnail(video_id, channel, thumbnail_path)

    return {
        "video_id":   video_id,
        "studio_url": studio_url,
        "watch_url":  watch_url,
        "title":      title
    }


def upload_thumbnail(video_id: str, channel: str, thumbnail_path: str) -> bool:
    """Upload Thumbnail A to the uploaded video."""
    thumbnail_path = Path(thumbnail_path)
    if not thumbnail_path.exists():
        print(f"[YouTube] Thumbnail not found: {thumbnail_path}")
        return False

    ext      = thumbnail_path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    mime     = mime_map.get(ext, "image/jpeg")

    print(f"[YouTube] Uploading Thumbnail A...")

    with open(thumbnail_path, "rb") as f:
        resp = requests.post(
            f"{UPLOAD_BASE}/thumbnails/set?videoId={video_id}&uploadType=media",
            headers={
                "Authorization": f"Bearer {_get_access_token(channel)}",
                "Content-Type":  mime
            },
            data=f,
            timeout=60
        )

    if resp.status_code == 200:
        print(f"[YouTube] Thumbnail A uploaded")
        return True
    else:
        print(f"[YouTube] Thumbnail upload failed: {resp.status_code} {resp.text[:200]}")
        return False


def download_thumbnail_from_url(url: str, output_path: str) -> Optional[str]:
    """Download a thumbnail image from a URL."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        Path(output_path).write_bytes(resp.content)
        return output_path
    except Exception as e:
        print(f"[YouTube] Thumbnail download failed: {e}")
        return None
