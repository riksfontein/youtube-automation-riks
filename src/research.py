"""
research.py — Three-layer competitor research.
Layer 1: vidIQ (outlier videos via Claude API with MCP)
Layer 2: NexLev (breakout channels via Claude API with MCP)
Layer 3: Subscribr Intel API (angle, format, topic, goals per video)
Minimum outlier score: 3.5x
"""

import os
import json
import requests
from typing import Optional
from src.state import get_rotation_keywords, get_channel_state, is_video_used

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SUBSCRIBR_API_KEY = os.environ["SUBSCRIBR_API_KEY"]
VIDIQ_API_KEY     = os.environ.get("VIDIQ_API_KEY", "")

SUBSCRIBR_BASE = "https://subscribr.ai/api/v1"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"

MIN_OUTLIER_SCORE  = 3.5
MIN_VIEWS          = 100_000
MAX_SUBSCRIBERS    = 100_000
TOP_N              = 5


# ─────────────────────────────────────────────────────────────
# Layer 1 + 2 via Claude API with vidIQ and NexLev MCP servers
# ─────────────────────────────────────────────────────────────

def _claude_research(channel: str, rotation_name: str, keywords: list[str]) -> list[dict]:
    """
    Call Claude API with vidIQ and NexLev MCP servers to find outlier videos.
    Returns list of raw video candidates.
    """

    prompt = f"""You are researching competitor videos for the YouTube channel "{channel}" currently in rotation "{rotation_name}".

Use the vidIQ and NexLev tools to find the best performing competitor videos.

RESEARCH TASKS:
1. Use vidiq_outliers to search for outlier videos with these keywords: {', '.join(keywords[:3])}
   - Filter: channels under {MAX_SUBSCRIBERS:,} subscribers
   - Filter: minimum {MIN_VIEWS:,} views
   - Filter: published within last 6 months
   - Filter: English language
   - Minimum outlier score: {MIN_OUTLIER_SCORE}x their channel average

2. Use search_niche_finder_channels or find_outlier_faceless_channels on NexLev to find fast-growing channels in this niche with under {MAX_SUBSCRIBERS:,} subscribers
   - For each channel found, check their recent top performing videos using youtube_channel_outliers

3. Combine all results and return as a JSON array. For each video include:
   - video_id (YouTube ID)
   - video_url (full YouTube URL)
   - title
   - channel_name
   - subscriber_count
   - view_count
   - outlier_score (x times their channel average)
   - views_per_hour (if available)
   - published_date
   - video_length_seconds (if available)
   - source (vidiq or nexlev)

Return ONLY a valid JSON array. No markdown, no explanation. Just the JSON array."""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "anthropic-beta": "mcp-client-2025-04-04"
    }

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "mcp_servers": [
            {
                "type": "url",
                "url": "https://mcp.vidiq.com/mcp",
                "name": "vidiq-mcp",
                "authorization_token": VIDIQ_API_KEY
            },
            {
                "type": "url",
                "url": "https://prod.dashboard.nexlev.io/api/claude-mcp",
                "name": "nexlev-mcp"
            }
        ],
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        resp = requests.post(
            f"{ANTHROPIC_BASE}/messages",
            headers=headers,
            json=payload,
            timeout=120
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text from response
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        # Parse JSON from response
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip().rstrip("```").strip()

        videos = json.loads(text)
        return videos if isinstance(videos, list) else []

    except Exception as e:
        print(f"[Research] Claude MCP research error: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# Layer 3: Subscribr Intel API enrichment
# ─────────────────────────────────────────────────────────────

def _subscribr_lookup_videos(video_ids: list[str]) -> dict:
    """
    Look up video details via Subscribr Intel API.
    Returns dict mapping video_id -> enriched data.
    """
    headers = {
        "Authorization": f"Bearer {SUBSCRIBR_API_KEY}",
        "Content-Type": "application/json"
    }
    enriched = {}

    # Subscribr processes up to 5 videos per call
    for i in range(0, len(video_ids), 5):
        batch = video_ids[i:i+5]
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/videos/lookup",
                headers=headers,
                json={"video_ids": batch},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                for video in data.get("videos", []):
                    vid_id = video.get("video_id") or video.get("id")
                    if vid_id:
                        enriched[vid_id] = video
        except Exception as e:
            print(f"[Research] Subscribr lookup error for batch {batch}: {e}")

    return enriched


def _subscribr_channel_competitors(subscribr_channel_id: str) -> list[dict]:
    """
    Get the competitor list already configured in Subscribr for this channel.
    """
    headers = {"Authorization": f"Bearer {SUBSCRIBR_API_KEY}"}
    try:
        resp = requests.get(
            f"{SUBSCRIBR_BASE}/channels/{subscribr_channel_id}/competitors",
            headers=headers,
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json().get("competitors", [])
    except Exception as e:
        print(f"[Research] Subscribr competitors error: {e}")
    return []


def _subscribr_video_search(keywords: list[str], rotation_name: str) -> list[dict]:
    """
    Search Subscribr Intel for additional competitor videos.
    """
    headers = {"Authorization": f"Bearer {SUBSCRIBR_API_KEY}"}
    results = []
    query = " ".join(keywords[:3])

    try:
        resp = requests.post(
            f"{SUBSCRIBR_BASE}/intel/videos/search",
            headers=headers,
            json={
                "query": query,
                "min_view_count": MIN_VIEWS,
                "max_subscriber_count": MAX_SUBSCRIBERS,
                "limit": 10
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("videos", [])
    except Exception as e:
        print(f"[Research] Subscribr video search error: {e}")

    return results


# ─────────────────────────────────────────────────────────────
# Scoring and selection
# ─────────────────────────────────────────────────────────────

def _score_video(video: dict, enriched: dict) -> float:
    """
    Combined score for ranking.
    40% vidIQ breakout, 30% Subscribr outlier, 20% VPH, 10% inverse sub count.
    """
    vid_id = video.get("video_id") or video.get("id", "")
    sub_enriched = enriched.get(vid_id, {})

    # Outlier scores
    vidiq_outlier   = float(video.get("outlier_score") or 0)
    subscribr_score = float(sub_enriched.get("outlier_score") or vidiq_outlier)

    # Views per hour signal (capped for scoring)
    vph = float(video.get("views_per_hour") or 0)
    vph_score = min(vph / 100, 10.0)  # normalise

    # Inverse sub score — smaller channel = higher signal
    subs = int(video.get("subscriber_count") or MAX_SUBSCRIBERS)
    inv_subs = max(0, (MAX_SUBSCRIBERS - subs) / MAX_SUBSCRIBERS) * 10

    score = (
        vidiq_outlier * 0.40 +
        subscribr_score * 0.30 +
        vph_score * 0.20 +
        inv_subs * 0.10
    )
    return round(score, 2)


def _deduplicate(videos: list[dict]) -> list[dict]:
    """Remove duplicate videos by video_id."""
    seen = set()
    unique = []
    for v in videos:
        vid_id = v.get("video_id") or v.get("id") or v.get("video_url", "")
        if vid_id and vid_id not in seen:
            seen.add(vid_id)
            unique.append(v)
    return unique


def _extract_video_id(video: dict) -> str:
    """Extract a clean YouTube video ID."""
    vid_id = video.get("video_id") or video.get("id", "")
    url = video.get("video_url") or video.get("url", "")
    if not vid_id and "youtube.com/watch?v=" in url:
        vid_id = url.split("v=")[1].split("&")[0]
    elif not vid_id and "youtu.be/" in url:
        vid_id = url.split("youtu.be/")[1].split("?")[0]
    return vid_id


def _build_youtube_url(video: dict) -> str:
    vid_id = _extract_video_id(video)
    if vid_id:
        return f"https://www.youtube.com/watch?v={vid_id}"
    return video.get("video_url") or video.get("url", "")


# ─────────────────────────────────────────────────────────────
# Main research function
# ─────────────────────────────────────────────────────────────

def run_research(channel: str) -> list[dict]:
    """
    Full three-layer research pipeline.
    Returns top 5 ranked competitor videos with all metadata.
    """
    ch_state = get_channel_state(channel)
    keywords = get_rotation_keywords(channel)
    rotation_name = ch_state["rotation_name"]
    subscribr_channel_id = ch_state["subscribr_channel_id"]

    print(f"[Research] Starting research for {channel} — {rotation_name}")
    print(f"[Research] Keywords: {keywords}")

    # Layer 1+2: Claude with vidIQ + NexLev MCP
    print("[Research] Layer 1+2: vidIQ + NexLev via Claude MCP...")
    mcp_videos = _claude_research(channel, rotation_name, keywords)
    print(f"[Research] Layer 1+2 returned {len(mcp_videos)} videos")

    # Layer 3a: Subscribr competitor list
    print("[Research] Layer 3a: Subscribr competitor channels...")
    competitor_videos = _subscribr_channel_competitors(subscribr_channel_id)
    print(f"[Research] Subscribr competitors returned {len(competitor_videos)} entries")

    # Layer 3b: Subscribr video search
    print("[Research] Layer 3b: Subscribr video search...")
    subscribr_videos = _subscribr_video_search(keywords, rotation_name)
    print(f"[Research] Subscribr search returned {len(subscribr_videos)} videos")

    # Combine all sources
    all_candidates = mcp_videos + competitor_videos + subscribr_videos
    all_candidates = _deduplicate(all_candidates)
    print(f"[Research] Combined unique candidates: {len(all_candidates)}")

    # Filter out already-used videos
    all_candidates = [
        v for v in all_candidates
        if not is_video_used(channel, _extract_video_id(v))
    ]

    # Filter by minimum outlier score and view count
    filtered = [
        v for v in all_candidates
        if float(v.get("outlier_score") or 0) >= MIN_OUTLIER_SCORE
        or float(v.get("view_count") or 0) >= MIN_VIEWS
    ]
    print(f"[Research] After filtering: {len(filtered)} candidates")

    if not filtered:
        # Relax filter if not enough
        filtered = [
            v for v in all_candidates
            if float(v.get("view_count") or 0) >= MIN_VIEWS
        ]
        print(f"[Research] Relaxed filter: {len(filtered)} candidates")

    # Enrich with Subscribr Intel
    video_ids = [_extract_video_id(v) for v in filtered if _extract_video_id(v)]
    print(f"[Research] Enriching {len(video_ids)} videos via Subscribr Intel...")
    enriched_data = _subscribr_lookup_videos(video_ids)

    # Score and sort
    for video in filtered:
        video["combined_score"] = _score_video(video, enriched_data)
        vid_id = _extract_video_id(video)
        if vid_id in enriched_data:
            s = enriched_data[vid_id]
            video["subscribr_format"] = s.get("format", "Documentary")
            video["subscribr_topic"]  = s.get("topic", "")
            video["subscribr_angle"]  = s.get("angle", "")
            video["subscribr_goals"]  = s.get("goals", "")
        else:
            video["subscribr_format"] = "Documentary"
            video["subscribr_topic"]  = ""
            video["subscribr_angle"]  = ""
            video["subscribr_goals"]  = ""
        # Ensure YouTube URL
        video["video_url"] = _build_youtube_url(video)
        video["video_id"]  = _extract_video_id(video)

    filtered.sort(key=lambda x: x["combined_score"], reverse=True)

    # Return top N
    top = filtered[:TOP_N]
    print(f"[Research] Selected top {len(top)} videos")
    for i, v in enumerate(top, 1):
        print(f"  {i}. {v.get('title', 'Unknown')[:60]} | "
              f"Score: {v['combined_score']} | "
              f"Views: {v.get('view_count', 0):,}")

    return top
