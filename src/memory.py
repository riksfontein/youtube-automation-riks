"""
memory.py — Performance memory and learning system.

Tracks which competitor channels and video angles produce the best
performing remixed videos over time. Biases future research toward
proven sources and formats.

Data stored in state.json under state["memory"] per channel.
YouTube performance checked 48h and 7d after upload.
"""

import os
import json
import requests
import time
from pathlib import Path
from src.state import load_state, save_state

YOUTUBE_CLIENT_ID     = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")

TOKEN_URL = "https://oauth2.googleapis.com/token"

CHANNEL_TOKEN_SECRETS = {
    "AE":  "YOUTUBE_REFRESH_TOKEN_AE",
    "GIA": "YOUTUBE_REFRESH_TOKEN_GIA",
    "BF":  "YOUTUBE_REFRESH_TOKEN_BF",
}

_token_cache = {}


def _get_access_token(channel: str) -> str:
    now = time.time()
    cached = _token_cache.get(channel, {})
    if cached.get("token") and now < cached.get("expires_at", 0) - 60:
        return cached["token"]

    secret_name = CHANNEL_TOKEN_SECRETS.get(channel, "")
    refresh_token = os.environ.get(secret_name, "")
    if not refresh_token:
        return ""

    resp = requests.post(TOKEN_URL, data={
        "client_id":     YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token"
    }, timeout=30)

    if resp.status_code != 200:
        return ""

    data = resp.json()
    _token_cache[channel] = {
        "token":      data.get("access_token", ""),
        "expires_at": now + int(data.get("expires_in", 3600))
    }
    return _token_cache[channel]["token"]


# ─────────────────────────────────────────────────────────────
# Memory initialisation
# ─────────────────────────────────────────────────────────────

def _ensure_memory(state: dict, channel: str):
    """Ensure memory structure exists for a channel."""
    if "memory" not in state:
        state["memory"] = {}

    if channel not in state["memory"]:
        state["memory"][channel] = {
            "competitor_scores": {},
            "angle_scores":      {},
            "rotation_scores":   {},
            "produced_videos":   [],
            "pending_checks":    []
        }

    mem = state["memory"][channel]

    for key in ["competitor_scores", "angle_scores", "rotation_scores"]:
        if key not in mem:
            mem[key] = {}

    if "produced_videos" not in mem:
        mem["produced_videos"] = []

    if "pending_checks" not in mem:
        mem["pending_checks"] = []


# ─────────────────────────────────────────────────────────────
# Record a produced video for future performance tracking
# ─────────────────────────────────────────────────────────────

def record_produced_video(
    channel: str,
    youtube_video_id: str,
    competitor_channel_name: str,
    competitor_video_url: str,
    angle: str,
    format_type: str,
    rotation_name: str,
    title: str
):
    """
    Record a produced video so its performance can be checked later.
    Called at end of Stage 4 after YouTube upload.
    """
    from datetime import datetime, timezone

    state = load_state()
    _ensure_memory(state, channel)
    mem = state["memory"][channel]

    now_iso = datetime.now(timezone.utc).isoformat()

    record = {
        "youtube_video_id":       youtube_video_id,
        "title":                  title,
        "competitor_channel":     competitor_channel_name,
        "competitor_video_url":   competitor_video_url,
        "angle":                  angle,
        "format":                 format_type,
        "rotation":               rotation_name,
        "produced_at":            now_iso,
        "performance_48h":        None,
        "performance_7d":         None,
        "performance_30d":        None,
        "check_at_48h":           _add_hours(now_iso, 48),
        "check_at_7d":            _add_hours(now_iso, 168),
        "check_at_30d":           _add_hours(now_iso, 720),
        "checked_48h":            False,
        "checked_7d":             False,
        "checked_30d":            False,
    }

    mem["produced_videos"].append(record)
    mem["pending_checks"].append({
        "youtube_video_id": youtube_video_id,
        "check_at":         _add_hours(now_iso, 48),
        "stage":            "48h"
    })

    save_state(state)
    print(f"[Memory] Recorded video for tracking: {youtube_video_id}")


# ─────────────────────────────────────────────────────────────
# Check performance of pending videos
# ─────────────────────────────────────────────────────────────

def check_pending_performance(channel: str):
    """
    Called at the start of Stage 1. Checks YouTube performance
    for any videos that are due for a 48h, 7d, or 30d check.
    Updates memory and retrains competitor/angle scores.
    """
    from datetime import datetime, timezone

    state = load_state()
    _ensure_memory(state, channel)
    mem = state["memory"][channel]

    now = datetime.now(timezone.utc)
    updated = False

    for video in mem["produced_videos"]:
        vid_id = video.get("youtube_video_id", "")
        if not vid_id:
            continue

        for stage, check_key, checked_key, perf_key in [
            ("48h",  "check_at_48h", "checked_48h", "performance_48h"),
            ("7d",   "check_at_7d",  "checked_7d",  "performance_7d"),
            ("30d",  "check_at_30d", "checked_30d", "performance_30d"),
        ]:
            if video.get(checked_key):
                continue
            check_time = video.get(check_key)
            if not check_time:
                continue
            if _parse_iso(check_time) > now:
                continue

            # Due for check
            print(f"[Memory] Checking {stage} performance for {vid_id}...")
            stats = _fetch_video_stats(channel, vid_id)

            if stats:
                video[perf_key]  = stats
                video[checked_key] = True
                updated = True
                print(f"[Memory] {stage} stats: {stats.get('views', 0):,} views, "
                      f"{stats.get('views_per_hour', 0):.1f} VPH")

                # Update scores after 7d check (enough data)
                if stage == "7d":
                    _update_scores(mem, video, stats)

    if updated:
        save_state(state)
        print("[Memory] Performance data saved")


def _fetch_video_stats(channel: str, video_id: str) -> dict:
    """Fetch current YouTube stats for a video."""
    access_token = _get_access_token(channel)
    if not access_token:
        return {}

    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "part": "statistics",
                "id":   video_id
            },
            timeout=30
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return {}

        stats = items[0].get("statistics", {})
        views    = int(stats.get("viewCount", 0))
        likes    = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        return {
            "views":          views,
            "likes":          likes,
            "comments":       comments,
            "views_per_hour": 0,  # calculated separately if needed
            "like_ratio":     round(likes / max(views, 1) * 100, 3)
        }
    except Exception as e:
        print(f"[Memory] Stats fetch error for {video_id}: {e}")
        return {}


def _update_scores(mem: dict, video: dict, stats: dict):
    """
    Update competitor and angle scores based on video performance.
    Uses a weighted rolling average so recent performance matters more.
    """
    views        = stats.get("views", 0)
    like_ratio   = stats.get("like_ratio", 0)
    perf_score   = views * 0.7 + like_ratio * 1000 * 0.3

    competitor = video.get("competitor_channel", "")
    angle      = video.get("angle", "")
    rotation   = video.get("rotation", "")

    # Update competitor score (rolling average, weight 0.7 new / 0.3 old)
    if competitor:
        old = mem["competitor_scores"].get(competitor, {})
        old_score = old.get("score", perf_score)
        old_count = old.get("count", 0)
        new_score = perf_score * 0.7 + old_score * 0.3
        mem["competitor_scores"][competitor] = {
            "score":       round(new_score, 2),
            "count":       old_count + 1,
            "best_views":  max(views, old.get("best_views", 0)),
            "last_updated": _now_iso()
        }
        print(f"[Memory] Updated competitor score: {competitor} → {new_score:.0f}")

    # Update angle score
    if angle:
        old = mem["angle_scores"].get(angle, {})
        old_score = old.get("score", perf_score)
        old_count = old.get("count", 0)
        new_score = perf_score * 0.7 + old_score * 0.3
        mem["angle_scores"][angle] = {
            "score": round(new_score, 2),
            "count": old_count + 1,
            "last_updated": _now_iso()
        }

    # Update rotation score
    if rotation:
        old = mem["rotation_scores"].get(rotation, {})
        old_score = old.get("avg_views", views)
        new_avg   = (old_score * old.get("count", 0) + views) / (old.get("count", 0) + 1)
        mem["rotation_scores"][rotation] = {
            "avg_views":  round(new_avg, 0),
            "count":      old.get("count", 0) + 1,
            "best_views": max(views, old.get("best_views", 0)),
            "last_updated": _now_iso()
        }


# ─────────────────────────────────────────────────────────────
# Get memory-based bonuses for research scoring
# ─────────────────────────────────────────────────────────────

def get_competitor_bonus(channel: str, competitor_channel_name: str) -> float:
    """
    Return a score bonus (0.0 to 5.0) for a competitor channel
    based on historical performance of videos sourced from it.
    """
    state = load_state()
    _ensure_memory(state, channel)
    mem = state["memory"][channel]

    scores = mem.get("competitor_scores", {})
    if not scores or competitor_channel_name not in scores:
        return 0.0

    comp_data = scores[competitor_channel_name]
    count     = comp_data.get("count", 0)
    score     = comp_data.get("score", 0)

    if count == 0:
        return 0.0

    # Normalize to 0-5 bonus
    # A score of 100,000+ views gets max bonus
    max_expected = 500_000
    normalized   = min(score / max_expected, 1.0) * 5.0

    # Reduce bonus if only 1 data point (not enough evidence)
    if count == 1:
        normalized *= 0.5

    return round(normalized, 2)


def get_angle_bonus(channel: str, angle: str) -> float:
    """Return a score bonus for a proven angle format."""
    state = load_state()
    _ensure_memory(state, channel)
    mem = state["memory"][channel]

    scores = mem.get("angle_scores", {})
    if not angle or angle not in scores:
        return 0.0

    score = scores[angle].get("score", 0)
    count = scores[angle].get("count", 0)

    if count == 0:
        return 0.0

    normalized = min(score / 500_000, 1.0) * 3.0
    if count == 1:
        normalized *= 0.5

    return round(normalized, 2)


def get_memory_summary(channel: str) -> dict:
    """Return a human-readable memory summary for the channel."""
    state = load_state()
    _ensure_memory(state, channel)
    mem = state["memory"][channel]

    # Top 3 competitors by score
    comp_scores = mem.get("competitor_scores", {})
    top_comps = sorted(
        comp_scores.items(),
        key=lambda x: x[1].get("score", 0),
        reverse=True
    )[:3]

    # Top 3 angles
    angle_scores = mem.get("angle_scores", {})
    top_angles = sorted(
        angle_scores.items(),
        key=lambda x: x[1].get("score", 0),
        reverse=True
    )[:3]

    total_videos = len(mem.get("produced_videos", []))

    return {
        "total_videos_tracked": total_videos,
        "top_competitor_channels": [
            {
                "name":       name,
                "score":      data.get("score", 0),
                "videos_used": data.get("count", 0),
                "best_views": data.get("best_views", 0)
            }
            for name, data in top_comps
        ],
        "top_angles": [
            {
                "angle":      name,
                "score":      data.get("score", 0),
                "times_used": data.get("count", 0)
            }
            for name, data in top_angles
        ]
    }


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _add_hours(iso_str: str, hours: int) -> str:
    from datetime import datetime, timezone, timedelta
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return (dt + timedelta(hours=hours)).isoformat()


def _parse_iso(iso_str: str):
    from datetime import datetime
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
