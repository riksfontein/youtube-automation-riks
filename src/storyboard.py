"""
storyboard.py — Storyboard-based scene prompt generation.

Implements the storyboard prompt builder skill via Claude API.
Replaces the basic scene-by-scene generation in documents.py
with a cinematically coherent two-phase storyboard approach.

Phase 1: Storyboard sheet prompt (one composite image, all panels)
Phase 2: Per-scene cinematic video prompts (Doc 3A, 3B, 3C)
"""

import os
import json
import requests
from typing import Optional

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE    = "https://api.anthropic.com/v1"

# Style constants derived from Google Flow / VEO3.1 Filmmaking Skill
# Key findings applied:
# - Audio instructions must be in FIRST HALF of every VEO3.1 prompt
# - Every prompt must include "No subtitles. No text overlays."
# - Official 5-part formula: [Cinematography]+[Subject]+[Action]+[Context]+[Style & Ambiance]
# - Style modifiers that trigger cinematic quality in VEO3.1
# - Audio direction: SFX prefix, quotation marks for dialogue, explicit music description

CHANNEL_STYLES = {
    "AE": {
        "visual_style":    "cinematic natural history documentary",
        "style_reference": "Netflix Prehistoric Planet / BBC Earth — deep saturated color, volumetric light, epic prehistoric scale",
        "color_grade":     "warm orange-teal grade, cinematic, 35mm lens look, film grain, shallow depth of field",
        "camera_language": "slow dolly-in, ground-level tracking shot, orbital crane shot, rack focus pull, overhead reveal",
        "storyboard_type": "natural history documentary",
        "audio_style":     "deep cinematic score, sub-bass rumble, ancient ocean ambient, prehistoric atmosphere",
        "style_modifiers": "cinematic, 35mm lens look, film grain, shallow depth of field, warm orange-teal grade, volumetric light",
        "safety_suffix":   "No subtitles. No text overlays.",
        "veo_audio_prefix": "SFX: deep prehistoric ocean ambient, low sub-bass frequency, ancient water displacement.",
    },
    "GIA": {
        "visual_style":    "premium geopolitical intelligence documentary",
        "style_reference": "Narcos / Vice News — warm orange-teal grade, presence anchor, real specific locations",
        "color_grade":     "warm orange-teal grade, 35mm lens look, institutional interiors, cold teal shadows, warm amber highlights",
        "camera_language": "slow push-in, handheld surveillance tracking, static locked-off, over-shoulder reveal",
        "storyboard_type": "intelligence documentary",
        "audio_style":     "tense documentary score, institutional ambient, distant city traffic, surveillance atmosphere",
        "style_modifiers": "cinematic, warm orange-teal grade, 35mm lens look, film grain, neon-lit for exterior scenes",
        "safety_suffix":   "No subtitles. No text overlays.",
        "veo_audio_prefix": "SFX: institutional ambient, low corridor hum, distant city murmur.",
    },
    "BF": {
        "visual_style":    "biblical archaeology documentary",
        "style_reference": "warm amber and deep shadow — ancient parchment warmth, golden hour reverence",
        "color_grade":     "golden hour warm amber grade, deep shadow contrast, 35mm lens look, film grain",
        "camera_language": "slow tilt-up reveal, extreme close-up on ancient surfaces, low-angle reverence, slow pan across artifacts",
        "storyboard_type": "archaeological documentary",
        "audio_style":     "ancient sacred atmosphere, desert wind, stone resonance, deep ceremonial tone",
        "style_modifiers": "cinematic, golden hour, film grain, warm amber grade, 35mm lens look, shallow depth of field",
        "safety_suffix":   "No subtitles. No text overlays.",
        "veo_audio_prefix": "SFX: ancient desert wind, stone chamber resonance, sacred atmosphere.",
    }
}

# The storyboard skill system prompt
# Updated with Google Flow / VEO3.1 Filmmaking Skill best practices:
# - Official 5-part VEO formula: [Cinematography]+[Subject]+[Action]+[Context]+[Style & Ambiance]
# - Audio in FIRST HALF of VEO3.1 prompts (not at the end)
# - Every VEO3.1 prompt ends with "No subtitles. No text overlays."
# - Style modifiers: cinematic, 35mm lens look, film grain, warm orange-teal grade
# - SFX prefix for sound effects, quotation marks for dialogue
# - wet pavement for urban scenes, golden hour for warm scenes

STORYBOARD_SKILL = """You are a professional storyboard and cinematic video prompt specialist
trained on Google Flow / VEO3.1 best practices.

You generate two-phase storyboard prompts from a script and channel style guidelines.

PHASE 1 — STORYBOARD SHEET IMAGE PROMPT:
A single prompt generating a professional multi-panel storyboard sheet as one composite image
with numbered panels, timecodes, shot descriptions, and scene metadata.
Optimised for Nano Banana Pro and GPT Image 2.

PHASE 2 — SCENE VIDEO PROMPTS:
Per-scene cinematic video prompts. Three versions: Meta AI, VEO3.1 (Google Flow), Grok Aurora.

NARRATIVE ARC PRINCIPLES:
- Three-act structure: Setup (first 20%) → Rising action (60%) → Resolution (20%)
- Shot variety: never repeat same shot type in consecutive scenes
- Emotional escalation: build intensity through middle, peak at 70-80%
- Close-ups for emotional peaks, wide shots for context and breathing room
- Character consistency: reference character-identifying details in every scene they appear

META AI PROMPT RULES:
- Motion verb FIRST: action-oriented, 2-3 short sentences maximum
- No timestamp format. Best for fluid dynamics, water, creature movement, fire, smoke
- Lead with what is MOVING in the scene

VEO3.1 PROMPT RULES (CRITICAL — follow exactly):
1. Official 5-part formula: [Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]
2. Audio direction goes in the FIRST HALF of the prompt, before visual description
   - SFX prefix for sound effects: "SFX: deep ocean ambient, low sub-bass frequency"
   - Quotation marks for any dialogue: She says, "We need to leave now."
   - Describe music explicitly: genre, tempo, instruments
3. Timestamp format for two-beat scenes: [00:00-00:05] first angle, [00:05-00:08] second angle
4. Single angle for environment-only and closing scenes (no timestamp needed)
5. Max 8 seconds per clip. Humans/creatures minimally animated — environment carries motion
6. High-impact style modifiers that trigger cinematic quality:
   - "cinematic" — #1 quality trigger (professional lighting, color grading, composition)
   - "35mm lens look" — classic cinematic aesthetic
   - "film grain" — analog texture and depth
   - "warm orange-teal grade" — premium cinematic color grade
   - "shallow depth of field" — professional lens quality
   - "golden hour" — warm flattering light
   - "wet pavement" — dramatically improves urban/rain scenes
7. ALWAYS end every VEO3.1 prompt with: "No subtitles. No text overlays."
8. Do NOT use negative language ("no walls") — describe what IS there, not what isn't
9. Keep prompts focused — VEO3.1 cannot follow too many simultaneous instructions

GROK AURORA PROMPT RULES:
- Structure: [Subject] [Action/Motion] [Camera Movement] [Visual Style] [Audio Direction]
- Subject FIRST always (opposite of VEO3.1 which leads with camera)
- 6s for scenes ≤10 words narration, 10s for scenes 11-13 words
- No timestamp format. Audio direction embedded naturally at end of prompt
- Good for scale reveals, atmospheric wide shots, creature motion"""


def generate_storyboard_sheet_prompt(
    script_text: str,
    channel: str,
    scene_timings: list,
    video_title: str
) -> str:
    """
    Phase 1: Generate a storyboard sheet image prompt.
    This produces ONE prompt that creates a composite storyboard image
    showing all scenes as numbered panels in a grid layout.
    Used to give a bird's-eye view of the whole video's visual narrative.
    """
    style = CHANNEL_STYLES.get(channel, CHANNEL_STYLES["AE"])
    scene_count = len(scene_timings)

    # Determine grid layout
    if scene_count <= 9:
        grid = "3×3 grid"
    elif scene_count <= 12:
        grid = "3×4 grid"
    elif scene_count <= 15:
        grid = "3×5 grid"
    elif scene_count <= 20:
        grid = "4×5 grid"
    else:
        grid = "5×6 grid"  # for longer videos, show first 30 scenes

    # Build condensed scene list for the prompt
    scenes_preview = scene_timings[:30]  # storyboard shows first 30 scenes
    scene_list = "\n".join([
        f"Scene {s['scene_number']} ({s['duration_s']:.1f}s): {s['text']}"
        for s in scenes_preview
    ])

    prompt = f"""Generate a storyboard sheet image prompt for a {style['storyboard_type']} video.

VIDEO TITLE: {video_title}
CHANNEL: {channel}
VISUAL STYLE: {style['style_reference']}
COLOR GRADE: {style['color_grade']}
TOTAL SCENES: {scene_count}
STORYBOARD SHOWS: First {len(scenes_preview)} scenes in a {grid}

SCENE LIST:
{scene_list}

Generate a complete Phase 1 storyboard sheet image prompt following the storyboard skill rules.
The prompt should produce a professional multi-panel storyboard sheet as ONE composite image.
Include the grid layout, scene metadata, shot types, and visual style.
Format as a single continuous text block ready to paste into Nano Banana Pro or GPT Image 2."""

    try:
        resp = requests.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":   "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system":  STORYBOARD_SKILL,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        resp.raise_for_status()
        result = resp.json()["content"][0]["text"]
        print(f"[Storyboard] Phase 1 storyboard sheet prompt generated ({len(result)} chars)")
        return result

    except Exception as e:
        print(f"[Storyboard] Phase 1 error: {e}")
        return ""


def generate_scene_video_prompts(
    scenes: list,
    channel: str,
    script_text: str,
    video_title: str
) -> list:
    """
    Phase 2: Generate cinematic video prompts for all scenes.
    Returns enhanced scenes with cinematically coherent video prompts
    for Meta AI, VEO3.1, and Grok Aurora.

    Uses the storyboard skill to ensure:
    - Three-act narrative arc across all scenes
    - Shot variety (no consecutive identical shot types)
    - Emotional escalation toward the climax
    - Consistent character identity
    """
    style = CHANNEL_STYLES.get(channel, CHANNEL_STYLES["AE"])
    total = len(scenes)

    # Process in batches of 20 for API efficiency
    BATCH_SIZE = 20
    enhanced_scenes = []

    for batch_start in range(0, total, BATCH_SIZE):
        batch = scenes[batch_start:batch_start + BATCH_SIZE]
        batch_end = min(batch_start + BATCH_SIZE, total)
        arc_position = f"scenes {batch_start+1}-{batch_end} of {total} total"

        # Build batch context
        scene_context = json.dumps([
            {
                "scene_number": s["scene_number"],
                "text":         s["text"],
                "duration_s":   s.get("duration_s", 4.0),
                "grok_duration": s.get("grok_duration", 6),
                "word_count":   len(s["text"].split()),
                "nbp_ref":      s.get("nbp_composite_ref", ""),
                "image_prompt": s.get("image_prompt", "")[:200]  # truncated for context
            }
            for s in batch
        ], ensure_ascii=False)

        prompt = f"""Generate Phase 2 cinematic video prompts for a batch of scenes.

CHANNEL: {channel}
VIDEO TITLE: {video_title}
VISUAL STYLE: {style['visual_style']}
STYLE REFERENCE: {style['style_reference']}
COLOR GRADE: {style['color_grade']}
CAMERA LANGUAGE: {style['camera_language']}

NARRATIVE POSITION: {arc_position}
THREE-ACT CONTEXT:
- If these are the opening scenes (1-20% of total): establish world, creature, atmosphere
- If middle scenes (20-80%): build tension, reveal, escalate
- If closing scenes (80-100%): resolve, emotional landing, silence

SCENES TO GENERATE PROMPTS FOR:
{scene_context}

For EACH scene, generate THREE video prompts following the storyboard skill rules:
1. meta_ai: Motion verb first, 2-3 short sentences, no timestamps
2. veo31: [Camera] [Subject] [Action] [Environment] [Lighting] [Audio], with timestamps for 8s clips
3. grok: [Subject] [Action] [Camera] [Style] [Audio], 6s or 10s duration

Ensure shot variety across consecutive scenes. Never use the same shot type twice in a row.
Reference the three-act position to adjust emotional intensity.

Return a JSON array. Each element:
{{
  "scene_number": <int>,
  "shot_type": "Wide|Medium|Close-up|Low Angle|High Angle|Dynamic|Over-shoulder|Macro",
  "emotional_beat": "one word: establish|tension|reveal|peak|resolve|silence",
  "video_prompt_meta": "Meta AI prompt",
  "video_prompt_veo31": "VEO3.1 prompt with timestamps",
  "video_prompt_grok": "Grok Aurora prompt with duration note"
}}

Return ONLY valid JSON array. No markdown."""

        try:
            resp = requests.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json"
                },
                json={
                    "model":      "claude-sonnet-4-20250514",
                    "max_tokens": 8096,
                    "system":     STORYBOARD_SKILL,
                    "messages":   [{"role": "user", "content": prompt}]
                },
                timeout=90
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"].strip()

            if "[" in text:
                start = text.index("[")
                end   = text.rindex("]") + 1
                text  = text[start:end]

            batch_results = json.loads(text)

            # Merge results back into scenes
            result_map = {r["scene_number"]: r for r in batch_results}
            for scene in batch:
                n = scene["scene_number"]
                if n in result_map:
                    r = result_map[n]
                    scene["video_prompt_meta"]  = r.get("video_prompt_meta",  scene.get("video_prompt_meta", ""))
                    scene["video_prompt_veo31"] = r.get("video_prompt_veo31", scene.get("video_prompt_veo31", ""))
                    scene["video_prompt_grok"]  = r.get("video_prompt_grok",  scene.get("video_prompt_grok", ""))
                    scene["shot_type"]          = r.get("shot_type", "Medium")
                    scene["emotional_beat"]     = r.get("emotional_beat", "tension")

            enhanced_scenes.extend(batch)
            print(f"[Storyboard] Phase 2: {batch_end}/{total} scenes processed")

        except Exception as e:
            print(f"[Storyboard] Phase 2 batch error ({arc_position}): {e}")
            enhanced_scenes.extend(batch)  # keep original prompts on error

    return enhanced_scenes


def generate_character_reference_sheet_prompt(
    channel: str,
    archetype_name: str,
    archetype_description: str,
    style_notes: str = ""
) -> str:
    """
    Generate a 4-view character reference sheet prompt.
    Used during channel setup to create reference images for each archetype.
    Output is pasted into Nano Banana Pro or GPT Image 2.
    """
    style = CHANNEL_STYLES.get(channel, CHANNEL_STYLES["AE"])

    prompt = f"""Character reference sheet — four views on a neutral grey background.
Show the same character across all four views. Character: {archetype_description}

[VIEW 1 — FULL BODY, FRONT]
Full-body front-facing three-quarter view of this character, full body visible head to feet.
{archetype_description} — front view, complete outfit and silhouette visible.

[VIEW 2 — FULL BODY, REAR]
Full-body rear view of the same character, directly from behind.
Full body visible head to feet. Same clothing, same proportions.

[VIEW 3 — FRONT CLOSE-UP]
Head and shoulders close-up, straight-on front view.
Sharp detail on face, skin texture, accessories, and costume surface detail.
Upper chest and shoulder visible at the bottom of frame.

[VIEW 4 — PROFILE CLOSE-UP]
Head and shoulders close-up, 90-degree left profile view.
Neck and upper shoulder visible. Same face as View 3.

LIGHTING & PRESENTATION:
Clean studio lighting — soft key light upper left, gentle fill from the right.
Consistent character identity, proportions, and costume details across all four views.
No text, no watermarks, no extra figures, no background environment.

STYLE: {style['style_reference']}. {style_notes}
Visual grade: {style['color_grade']}.
The character should look exactly as they would appear in a {style['storyboard_type']} production."""

    print(f"[Storyboard] Character reference prompt generated: {archetype_name}")
    return prompt


# Pre-built character reference prompts for all three channels
CHARACTER_REFERENCE_PROMPTS = {
    "AE": {
        "apex-predator": lambda: generate_character_reference_sheet_prompt(
            "AE",
            "apex-predator",
            "Otodus megalodon — scientifically accurate prehistoric marine apex predator. "
            "18 meters long, robust fusiform body, crescent-shaped caudal fin, broad pectoral fins, "
            "conical snout. Counter-shaded: dark grey-blue dorsally, pale off-white ventrally. "
            "No fantasy elements. Anatomically accurate per current paleontological consensus.",
            "BBC Earth Prehistoric Planet natural history grade. Deep Miocene Pacific Ocean."
        ),
        "ice-age-megafauna": lambda: generate_character_reference_sheet_prompt(
            "AE",
            "ice-age-megafauna",
            "Mammuthus primigenius — Woolly Mammoth. 3.4m shoulder height, long curved tusks ~3m, "
            "pronounced shoulder hump, thick dense brown-auburn fur with longer guard hairs, "
            "small ears, high-domed head. More compact and heavily built than modern elephant.",
            "Pleistocene Siberian tundra, 20,000 years ago. Cold overcast arctic light."
        ),
        "terrestrial-giant": lambda: generate_character_reference_sheet_prompt(
            "AE",
            "terrestrial-giant",
            "Tyrannosaurus rex — scientifically accurate. Correct modern posture: horizontal body "
            "balanced over hindlimbs, forward-leaning, tail as counterbalance. Robust skull, "
            "tiny two-clawed forelimbs, massive hindlimbs. Sparse feather-like integument on "
            "upper body. Dark earth tones, subtle countershading.",
            "Late Cretaceous Hell Creek Formation. Warm amber afternoon forest light."
        ),
    },
    "GIA": {
        "the-analyst": lambda: generate_character_reference_sheet_prompt(
            "GIA",
            "the-analyst",
            "Intelligence analyst figure — always seen from behind or in profile, never full face. "
            "Dark tactical clothing, professional build, short dark hair. Carrying a leather document "
            "case or tablet. The presence of authority and knowledge without revealing identity.",
            "Institutional interiors, government corridors. Teal-orange Narcos grade."
        ),
        "the-operator": lambda: generate_character_reference_sheet_prompt(
            "GIA",
            "the-operator",
            "Field operator figure — tactical dark clothing, practical gear, always in motion or "
            "observing. Seen from distance or back-of-head only. Conveys competence and awareness "
            "without facial identification.",
            "Outdoor field environments, urban surveillance positions."
        ),
        "the-power-figure": lambda: generate_character_reference_sheet_prompt(
            "GIA",
            "the-power-figure",
            "Power figure — tailored dark suit, hands visible holding documents or gesturing, "
            "never showing face. The silhouette of authority. Shot from behind at a window "
            "or across a conference table.",
            "Institutional boardrooms, corridors of power. Amber institutional lighting."
        ),
    },
    "BF": {
        "the-researcher": lambda: generate_character_reference_sheet_prompt(
            "BF",
            "the-researcher",
            "Archaeological researcher — khaki field clothes, brush and tools at belt, "
            "always shot from behind or with face obscured by equipment. "
            "Conveying scholarly dedication without personal identity.",
            "Ancient desert excavation sites. Warm amber afternoon light on ancient earth."
        ),
        "the-prophet": lambda: generate_character_reference_sheet_prompt(
            "BF",
            "the-prophet",
            "Ancient biblical prophet figure — robes of undyed linen and wool, simple sandals, "
            "staff in hand. Bearded, weathered face showing wisdom and years. "
            "Aged but powerful presence. Shot from medium distance.",
            "Ancient Near Eastern desert landscape. Warm golden light."
        ),
        "the-nephilim": lambda: generate_character_reference_sheet_prompt(
            "BF",
            "the-nephilim",
            "Giant figure — enormous scale communicated through environment reference, "
            "ancient rough-woven garment, massively built frame, archaic weapons or tools. "
            "Intimidating physical presence. Shot to emphasise scale against landscape.",
            "Ancient desert with scale reference objects. Dramatic low sun angle."
        ),
    }
}
