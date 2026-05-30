"""
subscribr.py — Subscribr API integration.
Env var: SUBSCRIBR_API_KEY (kept as-is — no renaming required)
"""

import os, sys, json, time, requests
from pathlib import Path
from typing import Optional

SUBSCRIBR_BASE = "https://subscribr.ai/api/v1"
POLL_INTERVAL  = 12
MAX_POLLS      = 40


def _token() -> str:
    return (os.environ.get("SUBSCRIBR_API_KEY") or
            os.environ.get("SUBSCRIBR_API_TOKEN") or "")


def _h() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type":  "application/json",
        "Accept":        "application/json"
    }


def _get(path: str, params: dict = None) -> dict:
    resp = requests.get(f"{SUBSCRIBR_BASE}{path}", headers=_h(),
                        params=params, timeout=30)
    print(f"[Subscribr] GET {path} → {resp.status_code}")
    if resp.status_code == 200:
        return resp.json()
    return {}


def _post(path: str, body: dict = None) -> dict:
    resp = requests.post(f"{SUBSCRIBR_BASE}{path}", headers=_h(),
                         json=body or {}, timeout=60)
    print(f"[Subscribr] POST {path} → {resp.status_code}")
    if resp.status_code in (200, 201, 202):
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code}
    print(f"[Subscribr] Error body: {resp.text[:200]}")
    return {}


def _unwrap(result: dict) -> dict:
    """Unwrap {"success":true,"data":...} envelope."""
    if "data" in result:
        d = result["data"]
        return d if d is not None else {}
    return result


def _poll(script_id: str, run_id: str, label: str):
    for attempt in range(MAX_POLLS):
        r = _get(f"/scripts/{script_id}/generate/poll", {"run_id": run_id})
        d = _unwrap(r)
        status = str(d.get("status") or "").lower()
        if status in ("completed", "done", "success", "finished"):
            print(f"[Subscribr] {label} complete")
            return
        if status in ("failed", "error"):
            raise RuntimeError(f"[Subscribr] {label} failed")
        print(f"[Subscribr] {label}: {status or 'pending'} ({attempt+1})")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"[Subscribr] {label} timed out")


# ─────────────────────────────────────────────────────────────
# Ideas
# ─────────────────────────────────────────────────────────────

def get_channel_ideas(channel_id: str) -> list:
    """Fetch existing ideas from the Subscribr channel."""
    r = _get(f"/channels/{channel_id}/ideas")
    d = _unwrap(r)
    if isinstance(d, list):
        ideas = d
    elif isinstance(d, dict):
        ideas = d.get("ideas") or d.get("data") or []
    else:
        ideas = []
    ideas = [i for i in ideas if isinstance(i, dict)]
    print(f"[Subscribr] {len(ideas)} ideas in channel")
    return ideas


def generate_ideas_from_video(channel_id: str, video_url: str) -> list:
    """
    Try to generate new ideas from competitor video.
    If that fails for any reason, return existing channel ideas.
    """
    print(f"[Subscribr] Requesting idea generation from: {video_url}")

    try:
        r = _post(f"/channels/{channel_id}/ideas/generate-from-video",
                  {"video_url": video_url})
        if r:
            # 202 = async — wait then fetch fresh ideas
            print("[Subscribr] Generation triggered — waiting 65s...")
            time.sleep(65)
            ideas = get_channel_ideas(channel_id)
            if ideas:
                return ideas
    except Exception as e:
        print(f"[Subscribr] generate-from-video failed: {e}")

    # Fallback — use whatever is already in the channel
    print("[Subscribr] Using existing channel ideas")
    return get_channel_ideas(channel_id)


def select_best_idea(ideas: list, rotation_name: str,
                     competitor_title: str, channel_name: str) -> dict:
    if not ideas:
        return {}
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    ideas_text = "\n".join([
        f"{i+1}. {idea.get('title','?')} | {idea.get('topic','')}"
        for i, idea in enumerate(ideas[:10])
    ])
    prompt = (
        f'Best YouTube idea for "{channel_name}" in rotation "{rotation_name}".\n'
        f'Competitor: "{competitor_title}"\nIDEAS:\n{ideas_text}\n'
        f'Return ONLY JSON: {{"selected_index": <1-10>}}'
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001",
                  "max_tokens": 64,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30
        )
        text = resp.json()["content"][0]["text"].strip()
        if "{" in text:
            text = text[text.index("{"):text.rindex("}")+1]
        idx = max(0, min(int(json.loads(text)["selected_index"]) - 1, len(ideas)-1))
        print(f"[Subscribr] Selected idea {idx+1}: {ideas[idx].get('title','?')}")
        return ideas[idx]
    except Exception as e:
        print(f"[Subscribr] Idea selection error: {e} — using first")
        return ideas[0]


# ─────────────────────────────────────────────────────────────
# Script pipeline
# ─────────────────────────────────────────────────────────────

def write_idea(idea_id: str) -> str:
    r = _post(f"/ideas/{idea_id}/write")
    d = _unwrap(r)
    script_id = str(d.get("id") or d.get("script_id") or "")
    if not script_id:
        raise RuntimeError(f"[Subscribr] No script_id: {r}")
    print(f"[Subscribr] Script canvas: {script_id}")
    return script_id


def generate_outline(script_id: str):
    r = _post(f"/scripts/{script_id}/outline/generate")
    d = _unwrap(r)
    run_id = str(d.get("run_id") or d.get("id") or "")
    if not run_id:
        raise RuntimeError(f"[Subscribr] No run_id for outline: {r}")
    _poll(script_id, run_id, "Outline")


def generate_script(script_id: str):
    r = _post(f"/scripts/{script_id}/script/generate")
    d = _unwrap(r)
    run_id = str(d.get("run_id") or d.get("id") or "")
    if not run_id:
        raise RuntimeError(f"[Subscribr] No run_id for script: {r}")
    _poll(script_id, run_id, "Script")


def humanize_script(script_id: str):
    r = _post(f"/scripts/{script_id}/script/humanize")
    d = _unwrap(r)
    run_id = str(d.get("run_id") or d.get("id") or "")
    if run_id:
        _poll(script_id, run_id, "Humanize")
    else:
        print("[Subscribr] Humanize: no run_id — skipping poll")


def export_script(script_id: str) -> str:
    for fmt in ["markdown", "text"]:
        r = _get(f"/scripts/{script_id}/export", {"format": fmt})
        d = _unwrap(r)
        text = (d.get("content") or d.get("script") or
                d.get("text") or d.get("markdown") or "")
        if not text and isinstance(r, dict):
            text = (r.get("content") or r.get("script") or
                    r.get("text") or "")
        if text:
            print(f"[Subscribr] Exported {len(text.split())} words")
            return text
    raise RuntimeError("[Subscribr] Export failed")


def generate_ab_titles(script_text: str, rotation_name: str,
                       competitor_title: str, channel_name: str) -> list:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    prompt = (
        f"3 YouTube titles for a {rotation_name} documentary. "
        f"Channel: {channel_name}. Competitor: {competitor_title}.\n"
        f"Script: {' '.join(script_text.split()[:250])}\n"
        f"Formula 1: Comparison. Formula 2: Revelation. Formula 3: Contradiction.\n"
        f"50-70 chars each. Return ONLY a JSON array of 3 strings."
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514",
                  "max_tokens": 256,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30
        )
        text = resp.json()["content"][0]["text"].strip()
        if "[" in text:
            text = text[text.index("["):text.rindex("]")+1]
        return json.loads(text)[:3]
    except Exception as e:
        print(f"[Subscribr] Titles error: {e}")
        return [competitor_title,
                f"Why {rotation_name} Is More Extreme Than You Think",
                f"The Truth About {rotation_name}"]


def generate_thumbnails(channel_id: str, idea_id: str,
                        competitor_thumbnail_url: Optional[str] = None) -> list:
    """Thumbnail generation — non-critical, returns empty list on failure."""
    thumbnails = []
    try:
        r = _post(f"/channels/{channel_id}/thumbnails/generations",
                  {"idea_id": idea_id, "strategy": "brainstorm"})
        d = _unwrap(r)
        run_id = str(d.get("run_id") or d.get("id") or d.get("generation_id") or "")
        if run_id:
            for _ in range(15):
                time.sleep(8)
                pr = _get(f"/channels/{channel_id}/thumbnails/generations/{run_id}")
                pd = _unwrap(pr)
                if str(pd.get("status","")).lower() in ("completed","done","success"):
                    urls = pd.get("output_urls") or [pd.get("url","")]
                    if urls and urls[0]:
                        thumbnails.append({"variant": "A", "url": urls[0], "label": "A"})
                    break
    except Exception as e:
        print(f"[Subscribr] Thumbnail error: {e}")
    print(f"[Subscribr] {len(thumbnails)} thumbnails generated")
    return thumbnails


# ─────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────

def full_script_pipeline(channel_id: str, rotation_name: str,
                         channel_name: str, video_url: str,
                         video_title: str) -> dict:
    print(f"\n[Subscribr] Pipeline: {channel_name} — {rotation_name}")

    ideas = generate_ideas_from_video(channel_id, video_url)
    if not ideas:
        raise RuntimeError(
            "[Subscribr] No ideas available. "
            "Go to subscribr.ai and add ideas to the AE channel manually, "
            "then run Stage 2 again."
        )

    best_idea = select_best_idea(ideas, rotation_name, video_title, channel_name)
    idea_id   = str(best_idea.get("id") or best_idea.get("idea_id") or "")
    if not idea_id:
        raise RuntimeError(f"[Subscribr] No idea_id in: {best_idea}")

    script_id   = write_idea(idea_id)
    generate_outline(script_id)
    generate_script(script_id)
    humanize_script(script_id)
    script_text = export_script(script_id)
    ab_titles   = generate_ab_titles(script_text, rotation_name,
                                     video_title, channel_name)
    return {
        "script_id":   script_id,
        "idea_id":     idea_id,
        "idea":        best_idea,
        "script_text": script_text,
        "ab_titles":   ab_titles,
        "word_count":  len(script_text.split())
    }
