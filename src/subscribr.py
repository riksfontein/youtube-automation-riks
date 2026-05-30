"""
subscribr.py — Subscribr API integration.
All responses follow {"success":true,"data":...} pattern.
"""

import os
import time
import json
import requests
from typing import Optional

SUBSCRIBR_BASE = "https://subscribr.ai/api/v1"
POLL_INTERVAL  = 12
MAX_POLLS      = 40


def _headers():
    key = os.environ.get("SUBSCRIBR_API_KEY", "")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json"
    }


def _d(resp) -> dict:
    """Parse response and unwrap {"success":true,"data":...} envelope."""
    try:
        body = resp.json()
    except Exception:
        return {}
    # Unwrap envelope if present
    if isinstance(body, dict) and "data" in body:
        return body["data"] if body["data"] is not None else {}
    return body if isinstance(body, dict) else {}


def _dl(resp) -> list:
    """Parse response and return list from data envelope."""
    try:
        body = resp.json()
    except Exception:
        return []
    if isinstance(body, dict) and "data" in body:
        d = body["data"]
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            # Could be {"videos":[...]} inside data
            for key in ["videos", "ideas", "competitors", "items"]:
                if key in d and isinstance(d[key], list):
                    return d[key]
        return []
    if isinstance(body, list):
        return body
    return []


def _poll(script_id: str, run_id: str, label: str) -> dict:
    """Poll script generation until completed or failed."""
    url = f"{SUBSCRIBR_BASE}/scripts/{script_id}/generate/poll"
    params = {"run_id": run_id}

    for attempt in range(MAX_POLLS):
        try:
            resp = requests.get(url, headers=_headers(), params=params, timeout=30)
            if resp.status_code == 200:
                body = resp.json()
                data = body.get("data") or body
                status = str(data.get("status") or data.get("state") or "").lower()

                if status in ("completed", "done", "success", "finished"):
                    print(f"[Subscribr] {label}: complete")
                    return data
                if status in ("failed", "error"):
                    raise RuntimeError(f"[Subscribr] {label} failed: {data}")

                print(f"[Subscribr] {label}: {status or 'pending'} (attempt {attempt+1}/{MAX_POLLS})")
            else:
                print(f"[Subscribr] Poll {resp.status_code}: {resp.text[:100]}")
        except RuntimeError:
            raise
        except Exception as e:
            print(f"[Subscribr] Poll error: {e}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"[Subscribr] {label} timed out after {MAX_POLLS * POLL_INTERVAL}s")


# ─────────────────────────────────────────────────────────────
# Ideas
# ─────────────────────────────────────────────────────────────

def generate_ideas_from_video(channel_id: str, video_url: str) -> list:
    """Generate ideas from a competitor video URL."""
    print(f"[Subscribr] Generating ideas from: {video_url}")
    try:
        resp = requests.post(
            f"{SUBSCRIBR_BASE}/channels/{channel_id}/ideas/generate-from-video",
            headers=_headers(),
            json={"video_url": video_url},
            timeout=120
        )
        if resp.status_code == 200:
            ideas = _dl(resp)
            if not ideas:
                # Try alternative response shape
                body = resp.json()
                ideas = (body.get("ideas") or body.get("data") or [])
                if isinstance(ideas, dict):
                    ideas = ideas.get("ideas") or []
            print(f"[Subscribr] {len(ideas)} ideas generated")
            return ideas if isinstance(ideas, list) else []
        else:
            print(f"[Subscribr] Ideas error {resp.status_code}: {resp.text[:200]}")
            return []
    except Exception as e:
        print(f"[Subscribr] Ideas exception: {e}")
        return []


def select_best_idea(ideas: list, rotation_name: str,
                     competitor_title: str, channel_name: str) -> dict:
    """Use Claude to select the best idea."""
    if not ideas:
        return {}

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

    ideas_text = "\n".join([
        f"{i+1}. {idea.get('title','No title')} | "
        f"Topic: {idea.get('topic','')} | Angle: {idea.get('angle','')}"
        for i, idea in enumerate(ideas[:10])
    ])

    prompt = (
        f'Select the single best YouTube video idea for "{channel_name}" '
        f'in rotation "{rotation_name}". Competitor video: "{competitor_title}".\n\n'
        f'IDEAS:\n{ideas_text}\n\n'
        f'Criteria: rotation alignment, strong CTR title formula, specific topic.\n'
        f'Return ONLY JSON: {{"selected_index": <1-10>, "reason": "<one sentence>"}}'
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 128,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        if "{" in text:
            text = text[text.index("{"):text.rindex("}")+1]
        result = json.loads(text)
        idx = max(0, min(int(result.get("selected_index", 1)) - 1, len(ideas)-1))
        selected = ideas[idx]
        print(f"[Subscribr] Selected idea {idx+1}: {selected.get('title','?')}")
        return selected
    except Exception as e:
        print(f"[Subscribr] Idea selection error: {e} — using first idea")
        return ideas[0] if ideas else {}


# ─────────────────────────────────────────────────────────────
# Script pipeline
# ─────────────────────────────────────────────────────────────

def write_idea(idea_id: str) -> str:
    """Convert idea to script canvas. Returns script_id."""
    resp = requests.post(
        f"{SUBSCRIBR_BASE}/ideas/{idea_id}/write",
        headers=_headers(),
        timeout=30
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"[Subscribr] write_idea {resp.status_code}: {resp.text[:200]}")

    data = _d(resp)
    script_id = str(data.get("script_id") or data.get("id") or data.get("script", {}).get("id", ""))
    if not script_id:
        # Try unwrapped
        body = resp.json()
        script_id = str(body.get("script_id") or body.get("id") or "")

    if not script_id:
        raise RuntimeError(f"[Subscribr] Could not get script_id from: {resp.text[:200]}")

    print(f"[Subscribr] Script canvas: {script_id}")
    return script_id


def _start_generation(endpoint: str, label: str) -> str:
    """POST to a generation endpoint and return run_id."""
    resp = requests.post(endpoint, headers=_headers(), timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"[Subscribr] {label} {resp.status_code}: {resp.text[:200]}")

    data = _d(resp)
    run_id = str(data.get("run_id") or data.get("id") or "")
    if not run_id:
        body = resp.json()
        run_id = str(body.get("run_id") or body.get("id") or "")

    if not run_id:
        raise RuntimeError(f"[Subscribr] No run_id from {label}: {resp.text[:200]}")

    print(f"[Subscribr] {label} started: {run_id}")
    return run_id


def generate_outline(script_id: str):
    run_id = _start_generation(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/outline/generate",
        "Outline"
    )
    _poll(script_id, run_id, "Outline")


def generate_script(script_id: str):
    run_id = _start_generation(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/script/generate",
        "Script"
    )
    _poll(script_id, run_id, "Script")


def humanize_script(script_id: str):
    run_id = _start_generation(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/script/humanize",
        "Humanize"
    )
    _poll(script_id, run_id, "Humanize")


def export_script(script_id: str) -> str:
    """Export final script text."""
    for fmt in ["markdown", "text", "plain"]:
        try:
            resp = requests.get(
                f"{SUBSCRIBR_BASE}/scripts/{script_id}/export",
                headers=_headers(),
                params={"format": fmt},
                timeout=30
            )
            if resp.status_code == 200:
                data = _d(resp)
                text = (
                    data.get("content") or data.get("script") or
                    data.get("text") or data.get("markdown") or ""
                )
                if not text:
                    body = resp.json()
                    text = (
                        body.get("content") or body.get("script") or
                        body.get("text") or ""
                    )
                if text:
                    print(f"[Subscribr] Exported {len(text.split())} words")
                    return text
        except Exception as e:
            print(f"[Subscribr] Export {fmt} error: {e}")

    raise RuntimeError("[Subscribr] Could not export script in any format")


# ─────────────────────────────────────────────────────────────
# Thumbnails
# ─────────────────────────────────────────────────────────────

def generate_thumbnails(channel_id: str, idea_id: str,
                        competitor_thumbnail_url: Optional[str] = None) -> list:
    thumbnails = []

    for strategy, label, extra in [
        ("standard",   "A — idea-based",        {}),
        ("brainstorm", "B — brainstorm variant", {}),
    ]:
        try:
            payload = {"idea_id": idea_id, "strategy": strategy}
            payload.update(extra)
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations",
                headers=_headers(),
                json=payload,
                timeout=60
            )
            if resp.status_code in (200, 201):
                data = _d(resp)
                gen_id = str(data.get("generation_id") or data.get("id") or "")
                if gen_id:
                    # Poll for completion
                    for _ in range(20):
                        time.sleep(8)
                        pr = requests.get(
                            f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations/{gen_id}",
                            headers=_headers(), timeout=30
                        )
                        if pr.status_code == 200:
                            pd = _d(pr)
                            status = str(pd.get("status", "")).lower()
                            if status in ("completed", "done", "success"):
                                url = pd.get("url") or pd.get("thumbnail_url") or ""
                                if url:
                                    thumbnails.append({
                                        "variant": strategy[0].upper(),
                                        "label":   label,
                                        "url":     url
                                    })
                                break
                            if status in ("failed", "error"):
                                break
                print(f"[Subscribr] Thumbnail {label} done")
        except Exception as e:
            print(f"[Subscribr] Thumbnail {label} error: {e}")

    # Variant C — competitor clone
    if competitor_thumbnail_url:
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations",
                headers=_headers(),
                json={
                    "idea_id":       idea_id,
                    "strategy":      "clone",
                    "reference_url": competitor_thumbnail_url
                },
                timeout=60
            )
            if resp.status_code in (200, 201):
                data = _d(resp)
                url = data.get("url") or data.get("thumbnail_url") or ""
                if url:
                    thumbnails.append({"variant": "C", "label": "C — competitor clone", "url": url})
        except Exception as e:
            print(f"[Subscribr] Thumbnail C error: {e}")

    print(f"[Subscribr] {len(thumbnails)} thumbnails generated")
    return thumbnails


# ─────────────────────────────────────────────────────────────
# AB titles
# ─────────────────────────────────────────────────────────────

def generate_ab_titles(script_text: str, rotation_name: str,
                       competitor_title: str, channel_name: str) -> list:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

    prompt = (
        f"Generate exactly 3 YouTube title variants for a {rotation_name} documentary video.\n"
        f"Channel: {channel_name}\n"
        f"Competitor reference: {competitor_title}\n\n"
        f"Script (first 300 words):\n{' '.join(script_text.split()[:300])}\n\n"
        f"Rules:\n"
        f"- Title 1: Comparison formula ('The X That Made Y Look Like Z')\n"
        f"- Title 2: Revelation formula ('Why X Is More [Adjective] Than You Think')\n"
        f"- Title 3: Contradiction formula ('We Have Been Wrong About X')\n"
        f"- 50-70 characters each. Include primary subject keyword.\n"
        f"Return ONLY a JSON array of 3 strings."
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":    "claude-sonnet-4-20250514",
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        if "[" in text:
            text = text[text.index("["):text.rindex("]")+1]
        titles = json.loads(text)
        return [str(t) for t in titles[:3]]
    except Exception as e:
        print(f"[Subscribr] Title generation error: {e}")
        return [competitor_title, f"Why {rotation_name} Is More Extreme Than You Think", f"The Truth About {rotation_name}"]


# ─────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────

def full_script_pipeline(channel_id: str, rotation_name: str,
                         channel_name: str, video_url: str,
                         video_title: str) -> dict:
    print(f"\n[Subscribr] Pipeline start: {channel_name} — {rotation_name}")

    # Ideas
    ideas = generate_ideas_from_video(channel_id, video_url)
    if not ideas:
        raise RuntimeError("[Subscribr] No ideas returned — check Subscribr channel setup")

    # Select best
    best_idea = select_best_idea(ideas, rotation_name, video_title, channel_name)
    idea_id   = str(best_idea.get("id") or best_idea.get("idea_id") or "")
    if not idea_id:
        raise RuntimeError(f"[Subscribr] No idea_id in: {best_idea}")

    # Script canvas
    script_id = write_idea(idea_id)

    # Outline → Script → Humanize
    generate_outline(script_id)
    generate_script(script_id)
    humanize_script(script_id)

    # Export
    script_text = export_script(script_id)

    # AB titles
    ab_titles = generate_ab_titles(script_text, rotation_name, video_title, channel_name)

    return {
        "script_id":   script_id,
        "idea_id":     idea_id,
        "idea":        best_idea,
        "script_text": script_text,
        "ab_titles":   ab_titles,
        "word_count":  len(script_text.split())
    }
