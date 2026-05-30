"""
research.py — Three-layer competitor research with memory-based learning.

Priority:
1. Subscribr configured competitors (primary)
2. vidIQ MCP via Claude
3. NexLev MCP via Claude

Handles multiple response formats:
- vidIQ API: camelCase (videoId, channelTitle, breakoutScore, subscriberCount, vph)
- Subscribr: snake_case with nested channel object
- Competitor lookup: channel objects
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
    try:
        text = resp.text.strip()
        return json.loads(text) if text else {}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# Normalise video dict from any source to consistent fields
# ─────────────────────────────────────────────────────────────

def _normalise(video: dict) -> dict:
    """
    Convert any video dict to consistent snake_case fields.
    Handles:
    - vidIQ camelCase: videoId, videoTitle, channelTitle, subscriberCount,
                       viewCount, breakoutScore, vph, videoPublishedAt
    - Subscribr: video_id, title, channel{title}, view_count, outlier_score
    - Generic: id, url, views
    """
    v = dict(video)

    # --- ID ---
    vid_id = (
        str(v.get("video_id") or v.get("videoId") or v.get("id") or "")
    )
    url = str(v.get("video_url") or v.get("videoUrl") or v.get("url") or "")
    if not vid_id and "watch?v=" in url:
        vid_id = url.split("v=")[1].split("&")[0]
    elif not vid_id and "youtu.be/" in url:
        vid_id = url.split("youtu.be/")[1].split("?")[0]
    if vid_id and not url:
        url = f"https://www.youtube.com/watch?v={vid_id}"
    v["video_id"]  = vid_id
    v["video_url"] = url

    # --- Title ---
    v["title"] = str(v.get("title") or v.get("videoTitle") or "Unknown")

    # --- Channel name ---
    channel_name = str(v.get("channel_name") or v.get("channelTitle") or "")
    if not channel_name and isinstance(v.get("channel"), dict):
        channel_name = str(v["channel"].get("title") or v["channel"].get("handle") or "")
    v["channel_name"] = channel_name

    # --- Subscriber count ---
    subs = (
        v.get("subscriber_count") or v.get("subscriberCount") or
        v.get("channel_subscriber_count") or
        (v.get("channel", {}).get("subscriber_count") if isinstance(v.get("channel"), dict) else None) or
        0
    )
    v["subscriber_count"] = int(subs)

    # --- View count ---
    views = (
        v.get("view_count") or v.get("viewCount") or v.get("views") or 0
    )
    v["view_count"] = int(views)

    # --- Outlier score (vidIQ uses breakoutScore) ---
    outlier = (
        v.get("outlier_score") or v.get("breakoutScore") or
        v.get("outlier") or 0
    )
    v["outlier_score"] = float(outlier)

    # --- Views per hour ---
    vph = v.get("views_per_hour") or v.get("vph") or 0
    v["views_per_hour"] = float(vph)

    # --- Published date ---
    pub = v.get("published_at") or v.get("videoPublishedAt") or v.get("published_date") or ""
    if isinstance(pub, (int, float)) and pub > 1000000000:
        # Unix timestamp → date string
        from datetime import datetime, timezone
        pub = datetime.fromtimestamp(pub, tz=timezone.utc).strftime("%Y-%m-%d")
    v["published_date"] = str(pub)[:10]

    # --- Thumbnail ---
    thumb = v.get("thumbnail_url") or v.get("videoThumbnail") or ""
    v["thumbnail_url"] = str(thumb)

    return v


def _extract_id(video: dict) -> str:
    return str(video.get("video_id") or "")


def _deduplicate(videos: list) -> list:
    seen, unique = set(), []
    for v in videos:
        key = v.get("video_id") or v.get("title", "")[:50]
        if key and key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


# ─────────────────────────────────────────────────────────────
# Layer 1: Subscribr (primary)
# ─────────────────────────────────────────────────────────────

def _subscribr_search(keywords: list, channel_id: str) -> list:
    if not SUBSCRIBR_API_KEY:
        return []

    results = []

    # Get configured competitor channels
    try:
        resp = requests.get(
            f"{SUBSCRIBR_BASE}/channels/{channel_id}/competitors",
            headers=_subscribr_headers(), timeout=30
        )
        if resp.status_code == 200:
            body  = _safe_json(resp)
            comps = body.get("data") or []
            print(f"[Research] Subscribr competitors: {len(comps)}")
            for comp in (comps if isinstance(comps, list) else []):
                if isinstance(comp, dict):
                    comp["source"] = "subscribr_competitor"
                    comp["is_competitor"] = True
                    results.append(comp)
    except Exception as e:
        print(f"[Research] Subscribr competitor error: {e}")

    # Keyword video search
    for keyword in keywords[:3]:
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/intel/videos/search",
                headers=_subscribr_headers(),
                json={"query": keyword, "limit": 8},
                timeout=30
            )
            if resp.status_code == 200:
                body  = _safe_json(resp)
                inner = body.get("data") or {}
                vids  = (inner.get("videos") or []) if isinstance(inner, dict) else (inner if isinstance(inner, list) else [])
                for v in vids:
                    if isinstance(v, dict):
                        v["source"] = "subscribr_search"
                        results.append(v)
                print(f"[Research] Subscribr '{keyword}': {len(vids)} videos")
            else:
                print(f"[Research] Subscribr search {resp.status_code}")
        except Exception as e:
            print(f"[Research] Subscribr search error: {e}")

    return results


def _enrich_subscribr(video_ids: list) -> dict:
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
                json={"video_ids": batch}, timeout=30
            )
            if resp.status_code == 200:
                body  = _safe_json(resp)
                inner = body.get("data") or {}
                vids  = inner.get("videos") or [] if isinstance(inner, dict) else []
                for vd in vids:
                    if isinstance(vd, dict):
                        vid_id = vd.get("video_id") or vd.get("id")
                        if vid_id:
                            enriched[str(vid_id)] = vd
        except Exception as e:
            print(f"[Research] Enrichment error: {e}")
    return enriched


# ─────────────────────────────────────────────────────────────
# Layer 2: vidIQ via Claude MCP
# ─────────────────────────────────────────────────────────────

def _vidiq_research(keywords: list, rotation_name: str) -> list:
    if not ANTHROPIC_API_KEY:
        return []

    prompt = (
        f"Use the vidiq_outliers tool to find outlier YouTube videos about: {rotation_name}.\n"
        f"Search keyword: {keywords[0] if keywords else rotation_name}\n"
        f"Parameters: maxSubscribers=100000, minOutlierScore=3.5, minViews=50000, "
        f"publishedWithin=oneYear, contentType=long\n\n"
        f"After getting the results, return them as a JSON array. "
        f"Map the fields: videoId→video_id, videoTitle→title, channelTitle→channel_name, "
        f"subscriberCount→subscriber_count, viewCount→view_count, "
        f"breakoutScore→outlier_score, vph→views_per_hour, videoPublishedAt→published_date.\n"
        f"Add source='vidiq' to each item.\n"
        f"Return ONLY the JSON array. No explanation. No markdown."
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
                "mcp_servers": [{
                    "type":                "url",
                    "url":                 "https://mcp.vidiq.com/mcp",
                    "name":                "vidiq",
                    "authorization_token": VIDIQ_API_KEY
                }],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract from all content blocks — text, tool_result, etc.
        all_text = ""
        for block in data.get("content", []):
            if isinstance(block, dict):
                if block.get("type") == "text":
                    all_text += block.get("text", "")
                elif block.get("type") == "tool_result":
                    for inner in block.get("content", []):
                        if isinstance(inner, dict) and inner.get("type") == "text":
                            all_text += inner.get("text", "")

        # Find JSON array in output
        if "[" in all_text and "]" in all_text:
            start = all_text.index("[")
            end   = all_text.rindex("]") + 1
            arr   = json.loads(all_text[start:end])
            if isinstance(arr, list):
                print(f"[Research] vidIQ MCP: {len(arr)} videos")
                return arr

    except Exception as e:
        print(f"[Research] vidIQ MCP error: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# Layer 3: NexLev via Claude MCP
# ─────────────────────────────────────────────────────────────

def _nexlev_research(keywords: list, rotation_name: str) -> list:
    if not ANTHROPIC_API_KEY:
        return []

    prompt = (
        f"Use NexLev to find fast-growing YouTube channels about: {rotation_name}.\n"
        f"Keywords: {', '.join(keywords[:2])}\n"
        f"Find channels under 100,000 subscribers with high growth.\n"
        f"For the top channels found, get their best recent videos.\n\n"
        f"Return a JSON array of videos with fields: "
        f"video_id, video_url, title, channel_name, subscriber_count, "
        f"view_count, outlier_score, views_per_hour, published_date, source='nexlev'.\n"
        f"Return ONLY the JSON array. No markdown."
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
                "mcp_servers": [{
                    "type": "url",
                    "url":  "https://prod.dashboard.nexlev.io/api/claude-mcp",
                    "name": "nexlev"
                }],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )
        resp.raise_for_status()
        data = resp.json()

        all_text = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                all_text += block.get("text", "")

        if "[" in all_text and "]" in all_text:
            start = all_text.index("[")
            end   = all_text.rindex("]") + 1
            arr   = json.loads(all_text[start:end])
            if isinstance(arr, list):
                print(f"[Research] NexLev MCP: {len(arr)} videos")
                return arr

    except Exception as e:
        print(f"[Research] NexLev MCP error: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# Relevance filter (fail-safe — returns original if anything fails)
# ─────────────────────────────────────────────────────────────

def _filter_relevant(videos: list, rotation_name: str, keywords: list) -> list:
    """Filter irrelevant videos. Returns original list if filter fails."""
    if not videos or not ANTHROPIC_API_KEY or len(videos) <= 3:
        return videos

    titles = [f"{i}: {v.get('title','?')[:80]}" for i, v in enumerate(videos)]
    prompt = (
        f"Topic: {rotation_name}. Keywords: {', '.join(keywords[:3])}.\n"
        f"Videos:\n" + "\n".join(titles) +
        f"\n\nReturn a JSON array of index numbers of videos RELEVANT to {rotation_name}. "
        f"Remove obviously unrelated content (cooking, ASMR, gaming, farming). "
        f"Be generous — keep anything potentially related to prehistoric animals, "
        f"ocean creatures, extinction, geology, ancient earth. "
        f"Return ONLY a JSON array of integers e.g. [0,1,3]. No explanation."
    )

    try:
        resp = requests.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 128,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=20
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()

        if "[" in text and "]" in text:
            text = text[text.index("["):text.rindex("]")+1]
            keep = set(json.loads(text))
            filtered = [v for i, v in enumerate(videos) if i in keep]
            if filtered:  # only use filter if it kept at least something
                removed = len(videos) - len(filtered)
                if removed > 0:
                    print(f"[Research] Relevance filter removed {removed} irrelevant videos")
                return filtered

        # Filter returned nothing — return originals
        return videos

    except Exception as e:
        print(f"[Research] Relevance filter failed: {e} — keeping all {len(videos)} videos")
        return videos


# ─────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────

def _score(video: dict, enriched: dict, channel: str) -> float:
    vid_id = _extract_id(video)
    sub    = enriched.get(str(vid_id), {})

    outlier_primary  = float(video.get("outlier_score") or 0)
    outlier_enriched = float(sub.get("outlier_score") or outlier_primary)
    vph  = min(float(video.get("views_per_hour") or 0) / 100, 10.0)
    subs = int(video.get("subscriber_count") or MAX_SUBSCRIBERS)
    inv  = max(0, (MAX_SUBSCRIBERS - subs) / MAX_SUBSCRIBERS) * 10
    comp = 7.0 if video.get("is_competitor") else 0.0

    mem_bonus = 0.0
    try:
        from src.memory import get_competitor_bonus, get_angle_bonus
        angle = str(sub.get("angle") or video.get("subscribr_angle") or "")
        cname = str(video.get("channel_name") or "")
        mem_bonus = get_competitor_bonus(channel, cname) + get_angle_bonus(channel, angle)
    except Exception:
        pass

    return round(
        outlier_primary  * 0.30 +
        outlier_enriched * 0.20 +
        vph              * 0.15 +
        inv              * 0.05 +
        comp             * 0.20 +
        mem_bonus        * 0.10,
        2
    )


# ─────────────────────────────────────────────────────────────
# Main research function
# ─────────────────────────────────────────────────────────────

def run_research(channel: str) -> list:
    # Check performance memory
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
    print("[Research] Layer 1: Subscribr...")
    sub_videos = _subscribr_search(keywords, channel_id)

    print("[Research] Layer 2: vidIQ MCP...")
    vidiq_videos = _vidiq_research(keywords, rotation_name)

    print("[Research] Layer 3: NexLev MCP...")
    nexlev_videos = _nexlev_research(keywords, rotation_name)

    print(f"[Research] Raw counts — Subscribr: {len(sub_videos)}, vidIQ: {len(vidiq_videos)}, NexLev: {len(nexlev_videos)}")

    # Combine and normalise ALL videos to consistent fields
    all_raw = sub_videos + vidiq_videos + nexlev_videos
    all_videos = [_normalise(v) for v in all_raw]
    all_videos = _deduplicate(all_videos)
    print(f"[Research] After normalise+dedup: {len(all_videos)}")

    # Remove already-used
    all_videos = [v for v in all_videos if not is_video_used(channel, _extract_id(v))]
    print(f"[Research] After removing used: {len(all_videos)}")

    # Filter irrelevant — fail-safe
    all_videos = _filter_relevant(all_videos, rotation_name, keywords)

    # Filter by minimum criteria — configured competitors always pass
    filtered = [
        v for v in all_videos
        if v.get("view_count", 0) >= MIN_VIEWS
        or v.get("outlier_score", 0) >= MIN_OUTLIER_SCORE
        or v.get("is_competitor")
    ]

    if not filtered:
        print(f"[Research] Min filter removed all — relaxing to all {len(all_videos)}")
        filtered = all_videos

    if not filtered:
        print("[Research] WARNING: No videos found from any source")
        return []

    # Enrich and score
    video_ids = [_extract_id(v) for v in filtered if _extract_id(v)]
    enriched  = _enrich_subscribr(video_ids[:30])
    print(f"[Research] Subscribr enrichment: {len(enriched)} videos enriched")

    for v in filtered:
        v["combined_score"]    = _score(v, enriched, channel)
        vid_id = _extract_id(v)
        if str(vid_id) in enriched:
            s = enriched[str(vid_id)]
            v["subscribr_format"] = s.get("format", "Documentary")
            v["subscribr_angle"]  = s.get("angle", "")
            v["subscribr_goals"]  = s.get("goals", "")
        else:
            v.setdefault("subscribr_format", "Documentary")
            v.setdefault("subscribr_angle",  "")
            v.setdefault("subscribr_goals",  "")

    filtered.sort(key=lambda x: x["combined_score"], reverse=True)
    top = filtered[:TOP_N]

    print(f"\n[Research] TOP {len(top)} VIDEOS:")
    for i, v in enumerate(top, 1):
        comp_flag = " ★COMPETITOR" if v.get("is_competitor") else ""
        print(f"  {i}. {v.get('title','?')[:55]}")
        print(f"     Views: {v.get('view_count',0):,} | Outlier: {v.get('outlier_score',0):.1f}x | Score: {v['combined_score']}{comp_flag}")

    return top
