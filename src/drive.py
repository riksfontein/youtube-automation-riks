"""
drive.py — Google Drive API integration.
Handles: folder creation, file upload, file download, folder listing.
Uses OAuth refresh token for authentication.
"""

import os
import io
import json
import requests
from pathlib import Path
from typing import Optional

YOUTUBE_CLIENT_ID     = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

DRIVE_API_BASE   = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL        = "https://oauth2.googleapis.com/token"

_access_token_cache = {"token": None, "expires_at": 0}


def _get_access_token() -> str:
    """Get a valid access token, refreshing if needed."""
    import time
    now = time.time()
    if _access_token_cache["token"] and now < _access_token_cache["expires_at"] - 60:
        return _access_token_cache["token"]

    resp = requests.post(TOKEN_URL, data={
        "client_id":     YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": YOUTUBE_REFRESH_TOKEN,
        "grant_type":    "refresh_token"
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    _access_token_cache["token"]      = data["access_token"]
    _access_token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _access_token_cache["token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_access_token()}"}


def get_or_create_folder(name: str, parent_id: Optional[str] = None) -> str:
    """Get existing folder ID or create it. Returns folder ID."""
    # Search for existing folder
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    resp = requests.get(
        f"{DRIVE_API_BASE}/files",
        headers=_headers(),
        params={"q": query, "fields": "files(id,name)"},
        timeout=30
    )
    resp.raise_for_status()
    files = resp.json().get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    resp = requests.post(
        f"{DRIVE_API_BASE}/files",
        headers={**_headers(), "Content-Type": "application/json"},
        json=metadata,
        timeout=30
    )
    resp.raise_for_status()
    folder_id = resp.json()["id"]
    print(f"[Drive] Created folder '{name}': {folder_id}")
    return folder_id


def create_video_folder(channel: str, video_title: str, base_folder_id: str) -> dict:
    """
    Create the per-video folder structure in Google Drive.
    Returns dict with folder IDs for images/, videos/, output/.
    """
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = video_title[:50].replace("/", "-").replace("\\", "-")
    folder_name = f"{date_str}_{safe_title}"

    # Channel folder
    channel_folder_id = get_or_create_folder(channel, base_folder_id)

    # Video folder
    video_folder_id = get_or_create_folder(folder_name, channel_folder_id)

    # Subfolders
    images_folder_id = get_or_create_folder("images", video_folder_id)
    videos_folder_id = get_or_create_folder("videos", video_folder_id)
    output_folder_id = get_or_create_folder("output", video_folder_id)

    folder_url = f"https://drive.google.com/drive/folders/{video_folder_id}"

    print(f"[Drive] Video folder created: {folder_url}")

    return {
        "video_folder_id":  video_folder_id,
        "video_folder_url": folder_url,
        "video_folder_name": folder_name,
        "images_folder_id": images_folder_id,
        "videos_folder_id": videos_folder_id,
        "output_folder_id": output_folder_id
    }


def upload_file(file_path: str, folder_id: str, mime_type: Optional[str] = None) -> dict:
    """Upload a file to a Google Drive folder. Returns file metadata."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not mime_type:
        ext = file_path.suffix.lower()
        mime_map = {
            ".mp4":  "video/mp4",
            ".wav":  "audio/wav",
            ".mp3":  "audio/mpeg",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".srt":  "text/plain",
            ".json": "application/json"
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

    metadata = {
        "name":    file_path.name,
        "parents": [folder_id]
    }

    # Multipart upload
    from requests_toolbelt.multipart.encoder import MultipartEncoder  # type: ignore
    try:
        from requests_toolbelt.multipart.encoder import MultipartEncoder
        m = MultipartEncoder(fields={
            "metadata": (None, json.dumps(metadata), "application/json"),
            "file":     (file_path.name, open(file_path, "rb"), mime_type)
        })
        resp = requests.post(
            f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart",
            headers={**_headers(), "Content-Type": m.content_type},
            data=m,
            timeout=300
        )
    except ImportError:
        # Fallback without requests_toolbelt
        resp = requests.post(
            f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart",
            headers=_headers(),
            files={
                "metadata": (None, json.dumps(metadata), "application/json"),
                "file":     (file_path.name, open(file_path, "rb"), mime_type)
            },
            timeout=300
        )

    resp.raise_for_status()
    file_meta = resp.json()
    print(f"[Drive] Uploaded: {file_path.name} → {file_meta.get('id')}")
    return file_meta


def download_file(file_id: str, output_path: str) -> str:
    """Download a file from Google Drive by file ID."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(
        f"{DRIVE_API_BASE}/files/{file_id}?alt=media",
        headers=_headers(),
        stream=True,
        timeout=300
    )
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"[Drive] Downloaded: {output_path}")
    return str(output_path)


def list_folder_files(folder_id: str, name_pattern: Optional[str] = None) -> list[dict]:
    """List all files in a folder, optionally filtered by name pattern."""
    query = f"'{folder_id}' in parents and trashed=false"
    if name_pattern:
        query += f" and name contains '{name_pattern}'"

    all_files = []
    page_token = None

    while True:
        params = {
            "q":      query,
            "fields": "nextPageToken,files(id,name,mimeType,size)",
            "orderBy": "name"
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(
            f"{DRIVE_API_BASE}/files",
            headers=_headers(),
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        all_files.extend(data.get("files", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_files


def download_assets_folder(folder_id: str, local_dir: str,
                            asset_type: str = "images") -> list[str]:
    """
    Download all assets (images or videos) from a Drive folder.
    Returns sorted list of local file paths.
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Drive] Downloading {asset_type} from folder {folder_id}...")

    files = list_folder_files(folder_id)
    downloaded = []

    # Sort by name to maintain scene order
    files.sort(key=lambda x: x["name"])

    for f in files:
        name = f["name"]
        # Filter by asset type
        if asset_type == "images" and not any(
            name.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]
        ):
            continue
        if asset_type == "videos" and not any(
            name.lower().endswith(ext) for ext in [".mp4", ".mov", ".avi", ".webm"]
        ):
            continue

        local_path = local_dir / name
        download_file(f["id"], str(local_path))
        downloaded.append(str(local_path))

    downloaded.sort()
    print(f"[Drive] Downloaded {len(downloaded)} {asset_type} files")
    return downloaded


def get_folder_id_from_url(url: str) -> Optional[str]:
    """Extract folder ID from a Google Drive URL."""
    if "/folders/" in url:
        folder_id = url.split("/folders/")[1].split("?")[0].split("/")[0]
        return folder_id
    return None


def upload_final_video(video_path: str, output_folder_id: str) -> str:
    """Upload assembled final video to Drive output folder. Returns web URL."""
    meta = upload_file(video_path, output_folder_id, "video/mp4")
    file_id = meta.get("id", "")
    return f"https://drive.google.com/file/d/{file_id}/view"
