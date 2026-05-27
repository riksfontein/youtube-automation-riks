"""
research.py — Three-layer competitor research with memory-based learning.

Priority order:
1. Subscribr configured competitors (primary — you already curated these)
2. vidIQ MCP (find new viral videos in the niche)
3. NexLev MCP (find new breakout channels)

Memory system biases scoring toward competitor channels and angles
that have historically produced well-performing remixed videos.
"""

import os
import json
import requests
from src.state import get_rotation_keywords, get_channel_state, is_video_used

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SUBSCRIBR_API_KEY = os.environ.get("SUBSCRIBR_API_KEY", "")
VIDIQ_API_KEY     = os.environ.get("VIDIQ_API_KEY", "")

SUBSCRIBR_BASE = "https://subscribr.ai/api/v1"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"

MIN_VIEWS         = 50_000
MAX_SUBSCRIBERS   = 100_000
MIN_OUTLIER_SCORE = 3.5
TOP_N             = 5


# ─────────────────────────────────────────────────────────────
# PRIMARY: Subscribr configured competitors
# ─────────────────────────────────────────────────────────────

def _subscribr_competitors(channel_id: str, keywords: list) -> list:
    """
    Fetch videos from competitors already configured in Subscribr.
    This is the PRIMARY research source — these are channels you
    already identified as your best competitors.
    """
    if not SUBSCRIBR_API_KEY:
        return []

    headers = {
        "Authorization": f"Bearer {SUBSCRIBR_API_KEY}",
        "Content-Type":  "application/json"
    }
    results = []

    # Get configured competitor channels
    try:
        resp = requests.get(
            f"{SUBSCRIBR_BASE}/channels/{channel_id}/competitors",
            headers=headers,
            timeout=30
        )
        if resp.status_code == 200:
            data        = resp.json()
            competitors = (
                data.get("competitors") or
                data.get("data") or
                data if isinstance(data, list) else []
            )
            print(f"[Research] Subscribr competitors configured: {len(competitors)}")

            # For each competitor, look up their recent top videos
            for comp in competitors:
                comp_id   = comp.get("channel_id") or comp.get("id") or comp.get("youtube_channel_id", "")
                comp_name = comp.get("channel_name") or comp.get("name") or comp.get("title", "Unknown")

                if not comp_id:
                    continue

                # Look up recent videos from this competitor via Subscribr Intel
                try:
                    video_resp = requests.post(
                        f"{SUBSCRIBR_BASE}/intel/channels/lookup",
                        headers=headers,
                        json={"channel_id": comp_id},
                        timeout=30
                    )
                    if video_resp.status_code == 200:
                        channel_data = video_resp.json()
                        recent_vids  = (
                            channel_data.get("recent_videos") or
                            channel_data.get("videos") or []
                        )
                        for v in recent_vids[:5]:
                            v["channel_name"]   = comp_name
                            v["source"]         = "subscribr_competitor"
                            v["is_competitor"]  = True
                            results.append(v)
                except Exception:
                    pass

                # Also search Subscribr Intel for recent videos from this channel name
                try:
                    search_resp = requests.post(
                        f"{SUBSCRIBR_BASE}/intel/videos/search",
                        headers=headers,
                        json={
                            "query":  keywords[0] if keywords else "prehistoric",
                            "limit":  5
                        },
                        timeout=30
                    )
                    if search_resp.status_code == 200:
                        search_data = search_resp.json()
                        vids = (
                            search_data.get("videos") or
                            search_data.get("data") or []
                        )
                        for v in vids:
                            v["source"]       = "subscribr_search"
                            v["is_competitor"] = False
                        results.extend(vids)
                except Exception:
                    pass

        else:
            print(f"[Research] Subscribr competitors endpoint returned {resp.status_code}")

    except Exception as e:
        print(f"[Research] Subscribr competitor fetch error: {e}")

    # Direct keyword search on Subscribr Intel
    for keyword in keywords[:3]:
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/videos/search",
                headers=headers,
                json={
                    "query":                keyword,
                    "min_view_count":       MIN_VIEWS,
                    "max_subscriber_count": MAX_SUBSCRIBERS,
                    "limit":                8
                },
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                vids = data.get("videos") or data.get("data") or []
                for v in vids:
                    v["source"] = "subscribr_search"
                results.extend(vids)
                print(f"[Research] Subscribr '{keyword}': {len(vids)} videos")
        except Exception as e:
            print(f"[Research] Subscribr search error: {e}")

    print(f"[Research] Subscribr total: {len(results)} videos")
    return results


def _enrich_with_subscribr(video_ids: list) -> dict:
    """Add angle/format/goals data from Subscribr Intel."""
    if not SUBSCRIBR_API_KEY or not video_ids:
        return {}

    headers = {
        "Authorization": f"Bearer {SUBSCRIBR_API_KEY}",
        "Content-Type":  "application/json"
    }
    enriched = {}

    for i in range(0, len(video_ids), 5):
        batch = [v for v in video_ids[i:i+5] if v]
        if not batch:
            continue
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/videos/lookup",
                headers=headers,
                json={"video_ids": batch},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                for video in data.get("videos") or []:
                    vid_id = video.get("video_id") or video.get("id")
                    if vid_id:
                        enriched[str(vid_id)] = video
        except Exception as e:
            print(f"[Research] Enrichment batch error: {e}")

    return enriched


# ─────────────────────────────────────────────────────────────
# SECONDARY: vidIQ via Claude MCP
# ─────────────────────────────────────────────────────────────

def _vidiq_research(keywords: list, rotation_name: str) -> list:
    """Find outlier videos via vidIQ MCP."""
    if not ANTHROPIC_API_KEY:
        return []

    prompt = f"""Use the vidIQ tools to find outlier YouTube videos in this niche: "{rotation_name}".

Try these search keywords: {', '.join(keywords[:3])}

Use vidiq_outliers to find videos:
- From channels under {MAX_SUBSCRIBERS:,} subscribers
- Published within the last 6 months
- With strong outlier performance (many times above channel average)
- In English language

Return a JSON array. Each item must have:
- video_id (11-character YouTube ID)
- video_url (https://www.youtube.com/watch?v=VIDEO_ID)
- title (string)
- channel_name (string)
- subscriber_count (integer)
- view_count (integer)
- outlier_score (float)
- views_per_hour (float, 0 if unknown)
- published_date (string)
- source: "vidiq"

Return ONLY the JSON array. No markdown. No explanation."""

    try:
        resp = requests.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "anthropic-beta":    "mcp-client-2025-04-04",
                "content-type":      "application/json"
            },
            json={
                "model":       "claude-sonnet-4-20250514",
                "max_tokens":  4096,
                "mcp_servers": [
                    {
                        "type":                "url",
                        "url":                 "https://mcp.vidiq.com/mcp",
                        "name":                "vidiq",
                        "authorization_token": VIDIQ_API_KEY
                    }
                ],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )
        resp.raise_for_status()

        text = ""
        for block in resp.json().get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        text = text.strip()
        # Extract JSON array from response
        if "[" in text:
            start = text.index("[")
            end   = text.rindex("]") + 1
            text  = text[start:end]

        videos = json.loads(text)
        result = [v for v in videos if isinstance(v, dict)]
        print(f"[Research] vidIQ: {len(result)} videos")
        return result

    except Exception as e:
        print(f"[Research] vidIQ error: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# SECONDARY: NexLev via Claude MCP
# ─────────────────────────────────────────────────────────────

def _nexlev_research(keywords: list, rotation_name: str) -> list:
    """Find breakout channels and videos via NexLev MCP."""
    if not ANTHROPIC_API_KEY:
        return []

    prompt = f"""Use the NexLev tools to find fast-growing YouTube channels in: "{rotation_name}".

Keywords: {', '.join(keywords[:3])}

1. Use search_niche_finder_channels or find_outlier_faceless_channels to find channels under {MAX_SUBSCRIBERS:,} subscribers with high growth
2. For each top channel found, get their best recent videos

Return a JSON array. Each item:
- video_id, video_url, title, channel_name, subscriber_count
- view_count (integer), outlier_score (float), views_per_hour (float)
- published_date (string), source: "nexlev"

Return ONLY the JSON array. No markdown."""

    try:
        resp = requests.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "anthropic-beta":    "mcp-client-2025-04-04",
                "content-type":      "application/json"
            },
            json={
                "model":       "claude-sonnet-4-20250514",
                "max_tokens":  4096,
                "mcp_servers": [
                    {
                        "type": "url",
                        "url":  "https://prod.dashboard.nexlev.io/api/claude-mcp",
                        "name": "nexlev"
                    }
                ],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )
        resp.raise_for_status()

        text = ""
        for block in resp.json().get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        text = text.strip()
        if "[" in text:
            start = text.index("[")
            end   = text.rindex("]") + 1
            text  = text[start:end]

        videos = json.loads(text)
        result = [v for v in videos if isinstance(v, dict)]
        print(f"[Research] NexLev: {len(result)} videos")
        return result

    except Exception as e:
        print(f"[Research] NexLev error: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# Scoring with memory bonuses
# ─────────────────────────────────────────────────────────────

def _score_video(video: dict, enriched: dict, channel: str) -> float:
    """
    Score a video combining research signals with memory-based bonuses.
    Memory bonuses reward competitor channels and angles that have
    historically produced well-performing remixed videos for this channel.
    """
    try:
        from src.memory import get_competitor_bonus, get_angle_bonus
        mem_available = True
    except Exception:
        mem_available = False

    vid_id = _extract_id(video)
    sub    = enriched.get(str(vid_id), {})

    # Base research scores
    outlier_primary  = float(video.get("outlier_score") or 0)
    outlier_enriched = float(sub.get("outlier_score") or outlier_primary)
    vph    = min(float(video.get("views_per_hour") or 0) / 100, 10.0)
    subs   = int(video.get("subscriber_count") or MAX_SUBSCRIBERS)
    inv    = max(0, (MAX_SUBSCRIBERS - subs) / MAX_SUBSCRIBERS) * 10

    # Subscribr configured competitor bonus — highest signal
    is_configured_competitor = video.get("is_competitor", False)
    competitor_source_bonus  = 7.0 if is_configured_competitor else 0.0

    # Memory-based bonuses
    memory_bonus = 0.0
    if mem_available:
        comp_name    = str(video.get("channel_name") or "")
        angle        = str(sub.get("angle") or video.get("subscribr_angle") or "")
        memory_bonus = get_competitor_bonus(channel, comp_name) + get_angle_bonus(channel, angle)

    score = (
        outlier_primary           * 0.30 +
        outlier_enriched          * 0.20 +
        vph                       * 0.15 +
        inv                       * 0.05 +
        competitor_source_bonus   * 0.20 +  # configured competitors get priority
        memory_bonus              * 0.10    # learned performance data
    )

    return round(score, 2)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _extract_id(video: dict) -> str:
    vid_id = str(video.get("video_id") or video.get("id") or "")
    url    = str(video.get("video_url") or video.get("url") or "")
    if not vid_id and "watch?v=" in url:
        vid_id = url.split("v=")[1].split("&")[0]
    elif not vid_id and "youtu.be/" in url:
        vid_id = url.split("youtu.be/")[1].split("?")[0]
    return vid_id.strip()


def _build_url(video: dict) -> str:
    vid_id = _extract_id(video)
    return f"https://www.youtube.com/watch?v={vid_id}" if vid_id else ""


def _deduplicate(videos: list) -> list:
    seen, unique = set(), []
    for v in videos:
        key = _extract_id(v) or str(v.get("title", ""))[:60]
        if key and key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


# ─────────────────────────────────────────────────────────────
# Main research function
# ─────────────────────────────────────────────────────────────

def run_research(channel: str) -> list:
    """
    Full three-layer research with memory-based learning.
    Subscribr configured competitors are the primary source.
    Returns top 5 scored videos for Checkpoint 1 email.
    """
    # Check pending performance data first (learning step)
    try:
        from src.memory import check_pending_performance
        check_pending_performance(channel)
    except Exception as e:
        print(f"[Research] Memory check skipped: {e}")

    ch_state      = get_channel_state(channel)
    keywords      = get_rotation_keywords(channel)
    rotation_name = ch_state["rotation_name"]
    channel_id    = ch_state["subscribr_channel_id"]

    print(f"\n[Research] {channel} — {rotation_name}")
    print(f"[Research] Keywords: {keywords}")

    # Layer 1 — PRIMARY: Subscribr configured competitors
    print("[Research] Layer 1 (PRIMARY): Subscribr configured competitors...")
    subscribr_videos = _subscribr_competitors(channel_id, keywords)

    # Layer 2: vidIQ
    print("[Research] Layer 2: vidIQ MCP...")
    vidiq_videos = _vidiq_research(keywords, rotation_name)

    # Layer 3: NexLev
    print("[Research] Layer 3: NexLev MCP...")
    nexlev_videos = _nexlev_research(keywords, rotation_name)

    # Combine — Subscribr first so its videos appear first before dedup
    all_videos = subscribr_videos + vidiq_videos + nexlev_videos
    all_videos = _deduplicate(all_videos)
    print(f"[Research] Combined unique: {len(all_videos)} videos")

    # Remove already-used competitor videos
    all_videos = [v for v in all_videos if not is_video_used(channel, _extract_id(v))]
    print(f"[Research] After removing used: {len(all_videos)}")

    # Filter by minimum views
    filtered = [
        v for v in all_videos
        if int(v.get("view_count") or v.get("views") or 0) >= MIN_VIEWS
        or float(v.get("outlier_score") or 0) >= MIN_OUTLIER_SCORE
        or v.get("is_competitor")  # always include configured competitors
    ]

    # If still empty, use all without view filter
    if not filtered:
        filtered = all_videos
        print(f"[Research] Relaxed filters — using all {len(filtered)} videos")

    if not filtered:
        print("[Research] WARNING: All research layers returned no results")
        return []

    # Enrich with Subscribr angle/format/goals
    video_ids = [_extract_id(v) for v in filtered if _extract_id(v)]
    enriched  = _enrich_with_subscribr(video_ids[:30])
    print(f"[Research] Enriched {len(enriched)} videos via Subscribr Intel")

    # Score with memory bonuses
    for v in filtered:
        v["combined_score"]    = _score_video(v, enriched, channel)
        v["video_url"]         = v.get("video_url") or _build_url(v)
        v["video_id"]          = _extract_id(v)

        vid_id = _extract_id(v)
        if str(vid_id) in enriched:
            s = enriched[str(vid_id)]
            v["subscribr_format"] = s.get("format", "Documentary")
            v["subscribr_topic"]  = s.get("topic", "")
            v["subscribr_angle"]  = s.get("angle", "")
            v["subscribr_goals"]  = s.get("goals", "")
        else:
            v.setdefault("subscribr_format", "Documentary")
            v.setdefault("subscribr_topic",  "")
            v.setdefault("subscribr_angle",  "")
            v.setdefault("subscribr_goals",  "")

    filtered.sort(key=lambda x: x["combined_score"], reverse=True)
    top = filtered[:TOP_N]

    print(f"\n[Research] TOP {len(top)} VIDEOS:")
    for i, v in enumerate(top, 1):
        is_comp = "★ COMPETITOR" if v.get("is_competitor") else ""
        print(f"  {i}. {str(v.get('title','?'))[:50]} | "
              f"Score: {v['combined_score']} | "
              f"Views: {int(v.get('view_count') or 0):,} {is_comp}")

    return top
