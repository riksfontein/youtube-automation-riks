"""
research.py — Three-layer competitor research.
Fixed: Subscribr API paths, NexLev MCP format, graceful fallbacks.
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


def _subscribr_headers():
    return {
        "Authorization": f"Bearer {SUBSCRIBR_API_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json"
    }


def _safe_json(resp) -> dict:
    """Parse JSON safely, return empty dict on failure."""
    try:
        text = resp.text.strip()
        if not text:
            return {}
        return resp.json()
    except Exception as e:
        print(f"[Research] JSON parse error: {e} | Response: {resp.text[:200]}")
        return {}


# ─────────────────────────────────────────────────────────────
# Layer 1: Subscribr configured competitors (PRIMARY)
# ─────────────────────────────────────────────────────────────

def _subscribr_competitors(channel_id: str, keywords: list) -> list:
    """Fetch videos from Subscribr configured competitors and search."""
    if not SUBSCRIBR_API_KEY:
        return []

    results = []

    # Step 1 — Get configured competitor channels
    # Response: {"success":true,"data":[{"channel_id":"UC...","title":"ExtinctZoo",...}]}
    competitor_channel_ids = []
    try:
        resp = requests.get(
            f"{SUBSCRIBR_BASE}/channels/{channel_id}/competitors",
            headers=_subscribr_headers(),
            timeout=30
        )
        if resp.status_code == 200:
            data  = _safe_json(resp)
            comps = data.get("data") or []
            if isinstance(comps, list):
                print(f"[Research] Subscribr configured competitors: {len(comps)}")
                for comp in comps:
                    if isinstance(comp, dict):
                        yt_id = comp.get("channel_id") or comp.get("youtube_channel_id", "")
                        title = comp.get("title", "")
                        if yt_id:
                            competitor_channel_ids.append({"id": yt_id, "title": title})
    except Exception as e:
        print(f"[Research] Subscribr competitors error: {e}")

    # Step 2 — Search for videos from competitor channels via Intel
    # For each competitor channel, search their recent videos
    for comp in competitor_channel_ids[:5]:
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/channels/lookup",
                headers=_subscribr_headers(),
                json={"channel_id": comp["id"]},
                timeout=30
            )
            if resp.status_code == 200:
                data = _safe_json(resp)
                # Try multiple response shapes
                channel_data = data.get("data") or data
                videos = (channel_data.get("recent_videos") or
                         channel_data.get("videos") or [])
                for v in videos:
                    if isinstance(v, dict):
                        v["channel_name"]  = comp["title"]
                        v["source"]        = "subscribr_competitor"
                        v["is_competitor"] = True
                        results.append(v)
        except Exception as e:
            print(f"[Research] Competitor channel lookup error: {e}")

    # Step 3 — Keyword video search
    # Response: {"success":true,"data":{"videos":[{...}]}}
    for keyword in keywords[:3]:
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/videos/search",
                headers=_subscribr_headers(),
                json={"query": keyword, "limit": 8},
                timeout=30
            )
            if resp.status_code == 200:
                data   = _safe_json(resp)
                # Correct path: data["data"]["videos"]
                inner  = data.get("data") or {}
                if isinstance(inner, dict):
                    videos = inner.get("videos") or []
                elif isinstance(inner, list):
                    videos = inner
                else:
                    videos = []
                for v in videos:
                    if isinstance(v, dict):
                        v["source"] = "subscribr_search"
                        results.append(v)
                print(f"[Research] Subscribr '{keyword}': {len(videos)} videos")
            else:
                print(f"[Research] Subscribr search {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[Research] Subscribr search error '{keyword}': {e}")

    print(f"[Research] Subscribr total: {len(results)}")
    return results


def _enrich_with_subscribr(video_ids: list) -> dict:
    """Enrich videos with Subscribr angle/format/goals."""
    if not SUBSCRIBR_API_KEY or not video_ids:
        return {}

    enriched = {}
    for i in range(0, len(video_ids), 5):
        batch = [v for v in video_ids[i:i+5] if v]
        if not batch:
            continue
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/videos/lookup",
                headers=_subscribr_headers(),
                json={"video_ids": batch},
                timeout=30
            )
            if resp.status_code == 200:
                data  = _safe_json(resp)
                # Response: {"success":true,"data":{"videos":[...]}}
                inner = data.get("data") or {}
                if isinstance(inner, dict):
                    videos_list = inner.get("videos") or []
                elif isinstance(inner, list):
                    videos_list = inner
                else:
                    videos_list = []
                for video in videos_list:
                    if isinstance(video, dict):
                        vid_id = video.get("video_id") or video.get("id")
                        if vid_id:
                            enriched[str(vid_id)] = video
        except Exception as e:
            print(f"[Research] Enrichment error: {e}")
    return enriched


# ─────────────────────────────────────────────────────────────
# Layer 2: vidIQ via Claude MCP
# ─────────────────────────────────────────────────────────────

def _vidiq_research(keywords: list, rotation_name: str) -> list:
    """Find outlier videos via vidIQ MCP."""
    if not ANTHROPIC_API_KEY or not VIDIQ_API_KEY:
        return []

    prompt = (
        f'Use vidIQ to find outlier YouTube videos in "{rotation_name}". '
        f'Keywords: {", ".join(keywords[:3])}. '
        f'Find videos from channels under {MAX_SUBSCRIBERS:,} subs, '
        f'published within 6 months, with strong outlier scores. '
        f'Return a JSON array with fields: '
        f'video_id, video_url, title, channel_name, subscriber_count, '
        f'view_count, outlier_score, views_per_hour, published_date. '
        f'source="vidiq". Return ONLY the JSON array, no markdown.'
    )

    try:
        payload = {
            "model":      "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages":   [{"role": "user", "content": prompt}]
        }

        # Try with MCP servers
        try:
            payload["mcp_servers"] = [
                {
                    "type":                "url",
                    "url":                 "https://mcp.vidiq.com/mcp",
                    "name":                "vidiq",
                    "authorization_token": VIDIQ_API_KEY
                }
            ]
            resp = requests.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta":    "mcp-client-2025-04-04",
                    "content-type":      "application/json"
                },
                json=payload,
                timeout=120
            )
            resp.raise_for_status()
        except Exception:
            # Fallback without MCP beta header
            payload.pop("mcp_servers", None)
            resp = requests.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json"
                },
                json=payload,
                timeout=60
            )
            resp.raise_for_status()

        text = ""
        for block in resp.json().get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        text = text.strip()
        if "[" in text and "]" in text:
            text = text[text.index("["):text.rindex("]")+1]
            videos = json.loads(text)
            result = [v for v in videos if isinstance(v, dict)]
            print(f"[Research] vidIQ: {len(result)} videos")
            return result

    except Exception as e:
        print(f"[Research] vidIQ error: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# Layer 3: NexLev via Claude MCP
# ─────────────────────────────────────────────────────────────

def _nexlev_research(keywords: list, rotation_name: str) -> list:
    """Find breakout channels via NexLev MCP."""
    if not ANTHROPIC_API_KEY:
        return []

    prompt = (
        f'Find fast-growing YouTube channels in "{rotation_name}". '
        f'Keywords: {", ".join(keywords[:3])}. '
        f'Channels under {MAX_SUBSCRIBERS:,} subscribers with high growth. '
        f'Return a JSON array with: '
        f'video_id, video_url, title, channel_name, subscriber_count, '
        f'view_count, outlier_score, published_date. source="nexlev". '
        f'Return ONLY the JSON array, no markdown.'
    )

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
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 4096,
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
        if "[" in text and "]" in text:
            text = text[text.index("["):text.rindex("]")+1]
            videos = json.loads(text)
            result = [v for v in videos if isinstance(v, dict)]
            print(f"[Research] NexLev: {len(result)} videos")
            return result

    except Exception as e:
        print(f"[Research] NexLev error: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────

def _normalise_video(video: dict) -> dict:
    """
    Normalise a video dict from any source to consistent field names.
    Subscribr returns: video_id, channel:{title,channel_id}, title,
                       view_count, outlier_score, published_at
    vidIQ/NexLev return: video_id, channel_name, subscriber_count, etc.
    """
    v = dict(video)

    # Flatten nested channel object from Subscribr
    if isinstance(v.get("channel"), dict):
        ch = v["channel"]
        if not v.get("channel_name"):
            v["channel_name"] = ch.get("title") or ch.get("handle") or ""
        if not v.get("channel_id"):
            v["channel_id"] = ch.get("channel_id") or ch.get("id") or ""

    # Ensure video_url exists
    vid_id = str(v.get("video_id") or v.get("id") or "")
    url    = str(v.get("video_url") or v.get("url") or "")
    if not url and vid_id:
        url = f"https://www.youtube.com/watch?v={vid_id}"
    v["video_url"] = url
    v["video_id"]  = vid_id

    # Normalise view count
    if not v.get("view_count") and v.get("views"):
        v["view_count"] = v["views"]

    return v


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


def _score(video: dict, enriched: dict, channel: str) -> float:
    vid_id = _extract_id(video)
    sub    = enriched.get(str(vid_id), {})

    outlier_primary   = float(video.get("outlier_score") or 0)
    outlier_enriched  = float(sub.get("outlier_score") or outlier_primary)
    vph               = min(float(video.get("views_per_hour") or 0) / 100, 10.0)
    subs              = int(video.get("subscriber_count") or MAX_SUBSCRIBERS)
    inv               = max(0, (MAX_SUBSCRIBERS - subs) / MAX_SUBSCRIBERS) * 10
    is_comp           = 7.0 if video.get("is_competitor") else 0.0

    try:
        from src.memory import get_competitor_bonus, get_angle_bonus
        angle  = str(sub.get("angle") or "")
        comp   = str(video.get("channel_name") or "")
        mem_bonus = get_competitor_bonus(channel, comp) + get_angle_bonus(channel, angle)
    except Exception:
        mem_bonus = 0.0

    return round(
        outlier_primary  * 0.30 +
        outlier_enriched * 0.20 +
        vph              * 0.15 +
        inv              * 0.05 +
        is_comp          * 0.20 +
        mem_bonus        * 0.10,
        2
    )


# ─────────────────────────────────────────────────────────────
# Main research function
# ─────────────────────────────────────────────────────────────

def run_research(channel: str) -> list:
    """Full three-layer research. Returns top 5 videos."""

    # Check pending performance data
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

    # Three layers
    print("[Research] Layer 1 (PRIMARY): Subscribr configured competitors...")
    subscribr_videos = _subscribr_competitors(channel_id, keywords)

    print("[Research] Layer 2: vidIQ MCP...")
    vidiq_videos = _vidiq_research(keywords, rotation_name)

    print("[Research] Layer 3: NexLev MCP...")
    nexlev_videos = _nexlev_research(keywords, rotation_name)

    # Combine
    all_videos = subscribr_videos + vidiq_videos + nexlev_videos
    all_videos = _deduplicate(all_videos)
    print(f"[Research] Combined unique: {len(all_videos)}")

    # Remove already-used
    all_videos = [v for v in all_videos
                  if not is_video_used(channel, _extract_id(v))]

    # Filter — configured competitors always pass regardless of view count
    filtered = [
        v for v in all_videos
        if int(v.get("view_count") or v.get("views") or 0) >= MIN_VIEWS
        or float(v.get("outlier_score") or 0) >= MIN_OUTLIER_SCORE
        or v.get("is_competitor")
    ]

    if not filtered:
        filtered = all_videos
        print(f"[Research] Relaxed to all {len(filtered)} videos")

    # Enrich
    video_ids = [_extract_id(v) for v in filtered if _extract_id(v)]
    enriched  = _enrich_with_subscribr(video_ids[:30])

    # Normalise all videos to consistent field names
    filtered = [_normalise_video(v) for v in filtered]

    # Score and sort
    for v in filtered:
        v["combined_score"]    = _score(v, enriched, channel)
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
        print(f"  {i}. {str(v.get('title','?'))[:55]} | "
              f"Score: {v['combined_score']} | "
              f"Views: {int(v.get('view_count') or 0):,} "
              f"{'★' if v.get('is_competitor') else ''}")

    return top
