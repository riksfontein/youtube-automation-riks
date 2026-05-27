"""
state.py — Read and write state.json for the YouTube automation system.
Tracks channel rotations, video counts, used competitor IDs, and job data.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "state.json"


def load_state() -> dict:
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state: dict):
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_channel_state(channel: str) -> dict:
    state = load_state()
    if channel not in state:
        raise ValueError(f"Unknown channel: {channel}. Must be AE, GIA, or BF.")
    return state[channel]


def check_and_advance_rotation(channel: str) -> tuple[bool, str]:
    """
    Check if a rotation switch is needed.
    Returns (switched, new_rotation_name).
    """
    state = load_state()
    ch = state[channel]

    if ch["videos_in_rotation"] >= ch["rotation_threshold"]:
        # Advance to next rotation
        current = ch["current_rotation"]
        max_rotation = len(ch["rotations"])
        next_rotation = (current % max_rotation) + 1

        ch["current_rotation"] = next_rotation
        ch["rotation_name"] = ch["rotations"][str(next_rotation)]
        ch["videos_in_rotation"] = 0

        save_state(state)
        return True, ch["rotation_name"]

    return False, ch["rotation_name"]


def create_job(channel: str, stage: int, data: dict) -> str:
    """Create a new job entry in state and return job_id."""
    state = load_state()
    job_id = str(uuid.uuid4())[:8].upper()

    state["pending_jobs"][job_id] = {
        "channel": channel,
        "stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data
    }

    save_state(state)
    return job_id


def get_job(job_id: str) -> dict:
    """Retrieve a pending job by ID."""
    state = load_state()
    if job_id not in state["pending_jobs"]:
        raise ValueError(f"Job {job_id} not found in state.")
    return state["pending_jobs"][job_id]


def update_job(job_id: str, updates: dict):
    """Update a job's data field."""
    state = load_state()
    if job_id not in state["pending_jobs"]:
        raise ValueError(f"Job {job_id} not found.")
    state["pending_jobs"][job_id]["data"].update(updates)
    state["pending_jobs"][job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def complete_job(job_id: str, channel: str):
    """Mark a job complete and update video counters."""
    state = load_state()

    # Update counters
    state[channel]["videos_in_rotation"] += 1
    state[channel]["total_videos_published"] += 1

    # Archive the job
    if job_id in state["pending_jobs"]:
        job_data = state["pending_jobs"].pop(job_id)
        # Add used competitor video ID to prevent reuse
        if "competitor_video_id" in job_data.get("data", {}):
            vid_id = job_data["data"]["competitor_video_id"]
            if vid_id not in state[channel]["used_competitor_video_ids"]:
                state[channel]["used_competitor_video_ids"].append(vid_id)

    save_state(state)


def add_reference_image(channel: str, ref_id: str, drive_url: str):
    """Add or update a reference image URL in the library."""
    state = load_state()
    state[channel]["reference_library"][ref_id] = drive_url
    save_state(state)


def get_reference_url(channel: str, ref_id: str) -> str:
    """Get the Google Drive URL for a reference image."""
    state = load_state()
    return state[channel]["reference_library"].get(ref_id, "")


def is_video_used(channel: str, video_id: str) -> bool:
    """Check if a competitor video has already been used."""
    state = load_state()
    return video_id in state[channel]["used_competitor_video_ids"]


def get_rotation_keywords(channel: str) -> list[str]:
    """Get keywords for the current rotation."""
    state = load_state()
    ch = state[channel]
    rotation_num = str(ch["current_rotation"])
    return ch["keywords_by_rotation"].get(rotation_num, [])


def get_rotation_status(channel: str) -> dict:
    """Get full rotation status for email display."""
    ch = get_channel_state(channel)
    remaining = ch["rotation_threshold"] - ch["videos_in_rotation"]
    max_rot = len(ch["rotations"])
    next_rot_num = (ch["current_rotation"] % max_rot) + 1
    return {
        "channel_name": ch["channel_name"],
        "current_rotation": ch["current_rotation"],
        "rotation_name": ch["rotation_name"],
        "videos_in_rotation": ch["videos_in_rotation"],
        "rotation_threshold": ch["rotation_threshold"],
        "remaining_in_rotation": remaining,
        "total_videos_published": ch["total_videos_published"],
        "next_rotation_name": ch["rotations"][str(next_rot_num)],
    }
