"""
subscribr.py — Full Subscribr API integration.
Handles: idea generation, outline, script, humanize, thumbnails, metadata.
"""

import os
import time
import json
import requests
from typing import Optional

SUBSCRIBR_API_KEY = os.environ["SUBSCRIBR_API_KEY"]
SUBSCRIBR_BASE    = "https://subscribr.ai/api/v1"

HEADERS = {
    "Authorization": f"Bearer {SUBSCRIBR_API_KEY}",
    "Content-Type":  "application/json"
}

POLL_INTERVAL = 12   # seconds
MAX_POLLS     = 40   # 8 minutes max per step


# ─────────────────────────────────────────────────────────────
# Polling helper
# ─────────────────────────────────────────────────────────────

def _poll(url: str, label: str) -> dict:
    """Poll an endpoint until status is completed or failed."""
    for attempt in range(MAX_POLLS):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status") or data.get("state", "")

        if status in ("completed", "done", "success"):
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"[Subscribr] {label} failed: {data}")

        print(f"[Subscribr] {label}: {status} (attempt {attempt+1}/{MAX_POLLS})")
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"[Subscribr] {label} timed out after {MAX_POLLS * POLL_INTERVAL}s")


# ─────────────────────────────────────────────────────────────
# Idea generation
# ─────────────────────────────────────────────────────────────

def generate_ideas_from_video(channel_id: str, video_url: str) -> list[dict]:
    """Generate 10 script ideas based on a competitor video."""
    print(f"[Subscribr] Generating ideas from: {video_url}")
    resp = requests.post(
        f"{SUBSCRIBR_BASE}/channels/{channel_id}/ideas/generate-from-video",
        headers=HEADERS,
        json={"video_url": video_url},
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    ideas = data.get("ideas") or data.get("data", [])
    print(f"[Subscribr] {len(ideas)} ideas generated")
    return ideas


def select_best_idea(ideas: list[dict], rotation_name: str,
                     competitor_title: str, channel_name: str) -> dict:
    """
    Use Claude to select the best idea from the list.
    Criteria: rotation alignment, title strength, topic uniqueness.
    """
    import requests as req
    ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

    ideas_text = "\n".join([
        f"{i+1}. Title: {idea.get('title', 'No title')}\n"
        f"   Topic: {idea.get('topic', '')}\n"
        f"   Angle: {idea.get('angle', '')}"
        for i, idea in enumerate(ideas)
    ])

    prompt = f"""You are selecting the best YouTube video idea for the channel "{channel_name}" 
currently in rotation "{rotation_name}".

The competitor video was: "{competitor_title}"

Here are 10 generated ideas. Select the SINGLE BEST one based on:
1. Strong alignment with the rotation topic "{rotation_name}"
2. Title uses a proven high-CTR format (comparison, revelation, curiosity gap, "we've been wrong")
3. Topic is specific and distinctive (not a generic broad topic)
4. Has strong emotional hook for the target audience

IDEAS:
{ideas_text}

Return ONLY a JSON object: {{"selected_index": <1-10>, "reason": "<one sentence>"}}"""

    resp = req.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()

    # Parse JSON response
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()
    result = json.loads(text)
    idx = int(result["selected_index"]) - 1
    selected = ideas[max(0, min(idx, len(ideas)-1))]
    print(f"[Subscribr] Selected idea {idx+1}: {selected.get('title', 'Unknown')}")
    print(f"[Subscribr] Reason: {result.get('reason', '')}")
    return selected


# ─────────────────────────────────────────────────────────────
# Script generation pipeline
# ─────────────────────────────────────────────────────────────

def write_idea(idea_id: str) -> str:
    """Convert idea to script canvas. Returns script_id."""
    resp = requests.post(
        f"{SUBSCRIBR_BASE}/ideas/{idea_id}/write",
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    script_id = data.get("script_id") or data.get("id")
    print(f"[Subscribr] Script canvas created: {script_id}")
    return script_id


def generate_outline(script_id: str) -> str:
    """Generate outline. Returns run_id."""
    resp = requests.post(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/outline/generate",
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    run_id = resp.json().get("run_id") or resp.json().get("id")
    print(f"[Subscribr] Outline generation started: {run_id}")

    # Poll for completion
    _poll(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/generate/poll?run_id={run_id}",
        "Outline generation"
    )
    print("[Subscribr] Outline complete")
    return run_id


def generate_script(script_id: str) -> str:
    """Generate full script from outline. Returns run_id."""
    resp = requests.post(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/script/generate",
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    run_id = resp.json().get("run_id") or resp.json().get("id")
    print(f"[Subscribr] Script generation started: {run_id}")

    _poll(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/generate/poll?run_id={run_id}",
        "Script generation"
    )
    print("[Subscribr] Script complete")
    return run_id


def humanize_script(script_id: str) -> str:
    """Humanize the generated script. Returns run_id."""
    resp = requests.post(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/script/humanize",
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    run_id = resp.json().get("run_id") or resp.json().get("id")
    print(f"[Subscribr] Humanize started: {run_id}")

    _poll(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/generate/poll?run_id={run_id}",
        "Humanize"
    )
    print("[Subscribr] Humanize complete")
    return run_id


def export_script(script_id: str, fmt: str = "markdown") -> str:
    """Export the final script as markdown text."""
    resp = requests.get(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}/export",
        headers=HEADERS,
        params={"format": fmt},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    script_text = data.get("content") or data.get("script") or data.get("text", "")
    word_count = len(script_text.split())
    print(f"[Subscribr] Script exported: {word_count} words")
    return script_text


def get_script_metadata(script_id: str) -> dict:
    """Get script title, topic, angle, and goals."""
    resp = requests.get(
        f"{SUBSCRIBR_BASE}/scripts/{script_id}",
        headers=HEADERS,
        timeout=30
    )
    if resp.status_code == 200:
        return resp.json()
    return {}


# ─────────────────────────────────────────────────────────────
# Thumbnail generation
# ─────────────────────────────────────────────────────────────

def generate_thumbnails(channel_id: str, idea_id: str,
                        competitor_thumbnail_url: Optional[str] = None) -> list[dict]:
    """
    Generate 3 thumbnail variants:
    A: from idea (standard)
    B: brainstorm variant
    C: clone of competitor thumbnail style
    Returns list of thumbnail dicts with url field.
    """
    thumbnails = []

    # Variant A — standard from idea
    print("[Subscribr] Generating Thumbnail A (idea-based)...")
    try:
        resp = requests.post(
            f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations",
            headers=HEADERS,
            json={"idea_id": idea_id, "strategy": "standard"},
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            gen_id = data.get("generation_id") or data.get("id")
            if gen_id:
                result = _poll(
                    f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations/{gen_id}",
                    "Thumbnail A"
                )
                thumbnails.append({
                    "variant": "A",
                    "label": "Idea-based (auto-set on upload)",
                    "url": result.get("url") or result.get("thumbnail_url", ""),
                    "generation_id": gen_id
                })
    except Exception as e:
        print(f"[Subscribr] Thumbnail A error: {e}")

    # Variant B — brainstorm
    print("[Subscribr] Generating Thumbnail B (brainstorm)...")
    try:
        resp = requests.post(
            f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations",
            headers=HEADERS,
            json={"idea_id": idea_id, "strategy": "brainstorm"},
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            gen_id = data.get("generation_id") or data.get("id")
            if gen_id:
                result = _poll(
                    f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations/{gen_id}",
                    "Thumbnail B"
                )
                thumbnails.append({
                    "variant": "B",
                    "label": "Brainstorm variant (add manually in Studio)",
                    "url": result.get("url") or result.get("thumbnail_url", ""),
                    "generation_id": gen_id
                })
    except Exception as e:
        print(f"[Subscribr] Thumbnail B error: {e}")

    # Variant C — clone competitor thumbnail
    if competitor_thumbnail_url:
        print("[Subscribr] Generating Thumbnail C (competitor clone)...")
        try:
            resp = requests.post(
                f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations",
                headers=HEADERS,
                json={
                    "idea_id": idea_id,
                    "strategy": "clone",
                    "reference_url": competitor_thumbnail_url
                },
                timeout=60
            )
            if resp.status_code == 200:
                data = resp.json()
                gen_id = data.get("generation_id") or data.get("id")
                if gen_id:
                    result = _poll(
                        f"{SUBSCRIBR_BASE}/channels/{channel_id}/thumbnails/generations/{gen_id}",
                        "Thumbnail C"
                    )
                    thumbnails.append({
                        "variant": "C",
                        "label": "Competitor-style clone (add manually in Studio)",
                        "url": result.get("url") or result.get("thumbnail_url", ""),
                        "generation_id": gen_id
                    })
        except Exception as e:
            print(f"[Subscribr] Thumbnail C error: {e}")

    print(f"[Subscribr] {len(thumbnails)} thumbnails generated")
    return thumbnails


# ─────────────────────────────────────────────────────────────
# Title generation
# ─────────────────────────────────────────────────────────────

def generate_ab_titles(script_text: str, rotation_name: str,
                       competitor_title: str, channel_name: str) -> list[str]:
    """
    Generate 3 AB test title variants using Claude.
    Uses proven high-CTR title formulas.
    """
    ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

    prompt = f"""Generate exactly 3 YouTube title variants for a video about the following script.

Channel: {channel_name}
Rotation/Niche: {rotation_name}
Competitor video title (for reference): {competitor_title}

Script excerpt (first 500 words):
{script_text[:2000]}

RULES:
- Each title must be 50-70 characters
- Each title must use a different proven CTR formula:
  Title 1: Comparison/scale formula ("The X That Made Y Look Like Z")
  Title 2: Revelation formula ("Why X Is More Terrifying Than You Think") 
  Title 3: Contradiction formula ("We've Been Wrong About X All Along")
- Include the primary creature/subject/keyword from the script
- Maximum curiosity gap — the viewer must click to find out
- No clickbait that misrepresents content
- Never duplicate the competitor title

Return ONLY a JSON array of 3 strings. No markdown, no explanation."""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()

    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip().rstrip("```")
    titles = json.loads(text)
    print(f"[Subscribr] AB titles generated: {titles}")
    return titles[:3]


# ─────────────────────────────────────────────────────────────
# Full script pipeline
# ─────────────────────────────────────────────────────────────

def full_script_pipeline(channel_id: str, rotation_name: str,
                         channel_name: str, video_url: str,
                         video_title: str) -> dict:
    """
    Run the complete script generation pipeline.
    Returns dict with script_id, script_text, idea, titles.
    """
    print(f"\n[Subscribr] Starting full pipeline for {channel_name}")
    print(f"[Subscribr] Competitor video: {video_title}")

    # Step 1: Generate ideas
    ideas = generate_ideas_from_video(channel_id, video_url)
    if not ideas:
        raise RuntimeError("[Subscribr] No ideas generated")

    # Step 2: Select best idea
    best_idea = select_best_idea(ideas, rotation_name, video_title, channel_name)
    idea_id   = best_idea.get("id") or best_idea.get("idea_id")

    # Step 3: Convert idea to script canvas
    script_id = write_idea(idea_id)

    # Step 4: Generate outline
    generate_outline(script_id)

    # Step 5: Generate script
    generate_script(script_id)

    # Step 6: Humanize
    humanize_script(script_id)

    # Step 7: Export
    script_text = export_script(script_id)

    # Step 8: Generate 3 AB titles
    ab_titles = generate_ab_titles(script_text, rotation_name, video_title, channel_name)

    return {
        "script_id":   script_id,
        "idea_id":     idea_id,
        "idea":        best_idea,
        "script_text": script_text,
        "ab_titles":   ab_titles,
        "word_count":  len(script_text.split()),
    }
