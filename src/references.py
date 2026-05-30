"""
references.py — Reference image analysis and new character detection.

Scans a script to identify:
1. Which composite references are needed per scene
2. Which character/creature species are new (no existing reference sheet)
3. What GPT Image 2 prompts to generate for missing references
4. Which scenes need storyboard updates when new characters are introduced

When a new character is detected:
- Generates a 4-view character reference sheet prompt (for NBP/GPT Image 2)
- Generates a scene composite reference prompt
- Tracks which scenes feature that character for targeted storyboard updates
"""

import os
import json
import requests
from src.state import get_channel_state

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────
# Reference keyword mappings per channel
# ─────────────────────────────────────────────────────────────

REFERENCE_KEYWORDS = {
    "AE": {
        "ae-composite-apex-deep-ocean":    ["megalodon", "deep ocean", "apex predator ocean", "ocean predator"],
        "ae-composite-apex-eocene-sea":    ["eocene", "shallow sea", "warm ancient ocean", "mosasaur surface"],
        "ae-composite-megafauna-tundra":   ["mammoth", "tundra", "ice age", "pleistocene", "woolly"],
        "ae-composite-megafauna-fossil":   ["fossil site", "excavation", "fossil record", "bone discovery"],
        "ae-composite-terrestrial-strata": ["geological strata", "cliff face", "rock layers", "cretaceous forest"],
        "ae-megalodon-gpt2-ref-1":         ["megalodon", "otodus megalodon"],
        "ae-mammoth-gpt2-ref-1":           ["mammoth", "woolly mammoth", "mammuthus"],
        "ae-trex-gpt2-ref-1":              ["t-rex", "tyrannosaurus", "tyrannosaurus rex"],
        "ae-mosasaur-gpt2-ref-1":          ["mosasaur", "mosasaurus"],
        "ae-sabertooth-gpt2-ref-1":        ["saber-tooth", "smilodon", "sabre tooth"],
        "ae-map-megalodon-range":          ["megalodon range", "miocene ocean", "megalodon distribution"],
        "ae-map-chicxulub-impact":         ["chicxulub", "impact site", "yucatan", "k-pg boundary"],
        "ae-map-pleistocene-megafauna":    ["ice age map", "pleistocene distribution", "mammoth range"],
        "ae-map-fossil-sites":             ["fossil sites", "paleontology sites", "fossil locations"],
        "ae-map-cambrian-world":           ["cambrian", "ancient ocean map", "cambrian world"],
    },
    "GIA": {
        "gia-composite-analyst-ops-room":     ["analyst", "operations room", "war room", "intelligence"],
        "gia-composite-analyst-corridor":     ["corridor", "institutional", "government building"],
        "gia-composite-analyst-field":        ["field intelligence", "outdoor", "surveillance"],
        "gia-composite-powerfigure-corridor": ["power figure", "kremlin", "leader"],
        "gia-composite-powerfigure-ops-room": ["leader operations", "kremlin chamber", "summit"],
        "gia-composite-operator-field":       ["operator", "tactical", "military field"],
        "gia-map-hormuz":           ["strait of hormuz", "hormuz", "persian gulf"],
        "gia-map-chokepoints":      ["maritime chokepoints", "global chokepoints", "shipping lane"],
        "gia-map-south-china-sea":  ["south china sea", "spratly", "nine-dash line"],
        "gia-map-nato-eastern-flank": ["nato eastern flank", "suwalki", "nato europe"],
        "gia-map-indo-pacific-alliances": ["indo-pacific", "aukus", "quad"],
        "gia-map-middle-east-power": ["middle east", "iran proxy", "gulf region"],
        "gia-map-europe-gas-pipelines": ["nord stream", "gas pipeline", "europe energy"],
        "gia-map-lng-trade-routes": ["lng", "liquefied natural gas", "energy trade"],
        "gia-map-critical-minerals": ["critical minerals", "rare earth", "supply chain"],
        "gia-map-miscalculation-zones": ["miscalculation", "escalation risk", "tripwire"],
        "gia-map-nuclear-tripwires": ["nuclear", "nuclear risk", "nuclear threat"],
        "gia-map-ukraine-theater":  ["ukraine", "front line", "ukraine war", "donbas"],
        "gia-map-taiwan-theater":   ["taiwan strait", "taiwan", "pla"],
        "gia-map-red-sea-theater":  ["red sea", "houthi", "bab-el-mandeb"],
    },
    "BF": {
        "bf-composite-researcher-desert":  ["researcher desert", "archaeologist", "fieldwork"],
        "bf-composite-researcher-temple":  ["researcher temple", "inside temple", "excavation temple"],
        "bf-composite-prophet-desert":     ["prophet", "ancient prophet", "biblical"],
        "bf-composite-nephilim-desert":    ["nephilim", "giant figure", "giant ancient"],
        "bf-composite-highpriest-temple":  ["high priest", "temple priest", "ancient priest"],
        "bf-composite-fallen-cave":        ["fallen angel", "cave angel", "winged figure"],
        "bf-map-giant-discoveries":        ["giant discoveries", "nephilim map", "giant bones"],
        "bf-map-ancient-near-east":        ["dead sea", "qumran", "ancient near east"],
        "bf-map-temple-mount":             ["temple mount", "jerusalem temple", "solomon temple map"],
        "bf-map-ancient-sites-world":      ["gobekli tepe", "ancient sites", "megalithic"],
        "bf-map-enoch-geography":          ["mount hermon", "watchers", "enoch geography"],
        "bf-map-smithsonian-campus":       ["smithsonian", "washington dc museum"],
    }
}

# Composite selection by character type × environment type
COMPOSITE_MAP = {
    "AE": {
        ("apex-predator",    "deep-ocean"):          "ae-composite-apex-deep-ocean",
        ("apex-predator",    "eocene-sea"):           "ae-composite-apex-eocene-sea",
        ("ice-age-megafauna","pleistocene-tundra"):   "ae-composite-megafauna-tundra",
        ("ice-age-megafauna","fossil-site"):          "ae-composite-megafauna-fossil",
        ("terrestrial-giant","geological-strata"):   "ae-composite-terrestrial-strata",
    },
    "GIA": {
        ("the-analyst",      "ops-room"):             "gia-composite-analyst-ops-room",
        ("the-analyst",      "corridor"):             "gia-composite-analyst-corridor",
        ("the-analyst",      "field"):                "gia-composite-analyst-field",
        ("the-power-figure", "corridor"):             "gia-composite-powerfigure-corridor",
        ("the-power-figure", "ops-room"):             "gia-composite-powerfigure-ops-room",
        ("the-operator",     "field"):                "gia-composite-operator-field",
    },
    "BF": {
        ("the-researcher",   "ancient-desert"):       "bf-composite-researcher-desert",
        ("the-researcher",   "temple-interior"):      "bf-composite-researcher-temple",
        ("the-prophet",      "ancient-desert"):       "bf-composite-prophet-desert",
        ("the-nephilim",     "ancient-desert"):       "bf-composite-nephilim-desert",
        ("the-high-priest",  "temple-interior"):      "bf-composite-highpriest-temple",
        ("the-fallen",       "hidden-text-cave"):     "bf-composite-fallen-cave",
    }
}

# Known species/creatures that have dedicated reference images
KNOWN_SPECIES = {
    "AE": {
        "megalodon":     "ae-megalodon-gpt2-ref-1",
        "woolly mammoth": "ae-mammoth-gpt2-ref-1",
        "t-rex":         "ae-trex-gpt2-ref-1",
        "tyrannosaurus": "ae-trex-gpt2-ref-1",
        "mosasaur":      "ae-mosasaur-gpt2-ref-1",
        "smilodon":      "ae-sabertooth-gpt2-ref-1",
        "saber-tooth":   "ae-sabertooth-gpt2-ref-1",
    }
}


# ─────────────────────────────────────────────────────────────
# GPT Image 2 prompts for missing references
# ─────────────────────────────────────────────────────────────

def _build_character_sheet_prompt(character_name: str, channel: str,
                                   scene_text: str) -> str:
    """
    Generate a 4-view character reference sheet prompt for a new character
    detected in the script. Uses Claude to build the correct prompt based
    on how the character is described in the scene context.
    """
    if not ANTHROPIC_API_KEY:
        return f"GPT Image 2, thinking mode enabled. 4-view character reference sheet for {character_name}."

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [{
                    "role": "user",
                    "content": f"""Generate a 4-view character reference sheet prompt for GPT Image 2.

Character: {character_name}
Channel: {channel}
Scene context: {scene_text}

The prompt must follow this exact structure:
"Character reference sheet — four views on a neutral grey background.
Show the same [character description] across all four views.

[VIEW 1 — FULL BODY, FRONT] Full-body front-facing three-quarter view. Full body visible head to feet.
[VIEW 2 — FULL BODY, REAR] Full-body rear view, directly from behind. Full body visible head to feet.
[VIEW 3 — FRONT CLOSE-UP] Head and shoulders close-up, straight-on. Sharp detail on features.
[VIEW 4 — PROFILE CLOSE-UP] Head and shoulders, 90-degree left profile view.

Lighting: Clean studio lighting — soft key light upper left, gentle fill right.
Consistent identity across all four views. No text, no watermarks, no extra figures.
Style: [appropriate style for {channel} channel]"

Write the complete prompt. Return only the prompt text, nothing else."""
                }]
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"[References] Character sheet prompt error: {e}")
        return (
            f"GPT Image 2, thinking mode enabled. "
            f"Character reference sheet — four views on neutral grey background. "
            f"Show {character_name} from: {scene_text[:100]}. "
            f"[VIEW 1 — FULL BODY, FRONT] [VIEW 2 — FULL BODY, REAR] "
            f"[VIEW 3 — FRONT CLOSE-UP] [VIEW 4 — PROFILE CLOSE-UP] "
            f"Clean studio lighting. Consistent across all four views. No text, no watermarks."
        )


def _build_composite_prompt(ref_id: str, channel: str) -> str:
    """Return a pre-written GPT Image 2 prompt for known composite references."""
    prompts = {
        "ae-megalodon-gpt2-ref-1": (
            "GPT Image 2, thinking mode enabled. Scientifically accurate Otodus megalodon "
            "reference image for prehistoric documentary. 18 meters long, full lateral profile, "
            "deep Miocene Pacific Ocean. Counter-shaded grey-blue dorsal, pale ventral. "
            "Modern great white shark alongside at correct scale. BBC Earth natural history grade."
        ),
        "ae-mosasaur-gpt2-ref-1": (
            "GPT Image 2, thinking mode enabled. Scientifically accurate Mosasaurus hoffmannii "
            "reference image. 14-17 meters, four paddle limbs, laterally flattened tail, "
            "long narrow skull. Cretaceous Western Interior Seaway. Warm tropical sunlight."
        ),
        "ae-mammoth-gpt2-ref-1": (
            "GPT Image 2, thinking mode enabled. Scientifically accurate Woolly Mammoth "
            "Mammuthus primigenius reference image. 3.4m shoulder height, long curved tusks, "
            "thick brown-auburn fur. Pleistocene tundra. Human silhouette for scale."
        ),
        "ae-trex-gpt2-ref-1": (
            "GPT Image 2, thinking mode enabled. Scientifically accurate Tyrannosaurus rex "
            "reference image. Correct forward-leaning posture, sparse feather integument, "
            "dark earth tones. Late Cretaceous Hell Creek. Elephant silhouette for scale."
        ),
        "ae-sabertooth-gpt2-ref-1": (
            "GPT Image 2, thinking mode enabled. Scientifically accurate Smilodon fatalis "
            "reference image. 18cm upper canines, robust muscular build, tawny coat. "
            "Pleistocene California. Modern lion alongside for scale."
        ),
    }
    return prompts.get(ref_id, f"GPT Image 2, thinking mode enabled. Reference image for {ref_id}.")


# ─────────────────────────────────────────────────────────────
# Main analysis function
# ─────────────────────────────────────────────────────────────

def analyse_script_references(script_text: str, channel: str) -> list:
    """
    Analyse a script and return per-scene reference analysis.
    Detects new characters and returns targeted storyboard update info.
    """
    ch_state    = get_channel_state(channel)
    ref_library = ch_state.get("reference_library", {})

    # Use Claude to parse scenes
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 8096,
                "messages": [{
                    "role": "user",
                    "content": f"""Parse this script into scenes (~10 words each) and identify reference needs.

Channel: {channel}
Script:
{script_text[:4000]}

For each scene return JSON:
{{
  "scene_number": 1,
  "scene_text": "exact words",
  "character_type": "the-analyst|apex-predator|ice-age-megafauna|terrestrial-giant|the-researcher|the-prophet|the-nephilim|the-high-priest|the-fallen|the-operator|the-power-figure|none",
  "species_name": "specific species if named e.g. megalodon, mosasaur, livyatan — or null",
  "environment_type": "deep-ocean|eocene-sea|pleistocene-tundra|fossil-site|geological-strata|ops-room|corridor|field|temple-interior|ancient-desert|hidden-text-cave|none",
  "needs_map": false,
  "map_type": null
}}

Return ONLY valid JSON array."""
                }]
            },
            timeout=60
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        if "[" in text:
            text = text[text.index("["):text.rindex("]")+1]
        scenes = json.loads(text)
    except Exception as e:
        print(f"[References] Scene parse error: {e}")
        return []

    # Track new characters across the whole script
    new_characters = {}  # character_name → list of scene numbers

    results = []
    for scene in scenes:
        char_type    = scene.get("character_type", "none")
        env_type     = scene.get("environment_type", "none")
        species_name = scene.get("species_name")
        scene_num    = scene.get("scene_number", 0)
        scene_text   = scene.get("scene_text", "")

        # Determine reference ID
        composite_map = COMPOSITE_MAP.get(channel, {})
        ref_id = composite_map.get((char_type, env_type))

        # Check for species-specific reference
        species_ref = None
        if species_name:
            known = KNOWN_SPECIES.get(channel, {})
            species_lower = species_name.lower()
            for key, rid in known.items():
                if key in species_lower or species_lower in key:
                    species_ref = rid
                    break

        # Determine status
        if species_ref:
            url    = ref_library.get(species_ref, "")
            status = "COVERED" if url else "MISSING"
            final_ref = species_ref
        elif ref_id:
            url    = ref_library.get(ref_id, "")
            status = "COVERED" if url else "MISSING"
            final_ref = ref_id
        else:
            # Check keyword matching as fallback
            scene_lower = scene_text.lower()
            kw_map = REFERENCE_KEYWORDS.get(channel, {})
            matched_ref = None
            for rid, keywords in kw_map.items():
                if any(kw in scene_lower for kw in keywords):
                    matched_ref = rid
                    break
            if matched_ref:
                url    = ref_library.get(matched_ref, "")
                status = "COVERED" if url else "MISSING"
                final_ref = matched_ref
            else:
                status    = "NO_REF_NEEDED"
                final_ref = None

        entry = {
            "scene_number":  scene_num,
            "scene_text":    scene_text,
            "reference_id":  final_ref,
            "status":        status,
            "character_type": char_type,
            "environment_type": env_type,
            "species_name":  species_name,
        }

        # Flag new character for storyboard update tracking
        if species_name and status == "MISSING":
            if species_name not in new_characters:
                new_characters[species_name] = []
            new_characters[species_name].append(scene_num)

        if status == "MISSING" and final_ref:
            entry["gpt_image_prompt"] = _build_composite_prompt(final_ref, channel)
            entry["filename"]         = f"{final_ref}.jpg"
            folder_map = {"AE": "AE-Reference-Images", "GIA": "GIA-Reference-Images", "BF": "BF-Reference-Images"}
            entry["upload_to"]        = folder_map.get(channel, "Reference-Images")

            # If this is a new species, also add character sheet prompt
            if species_name and species_name in new_characters:
                entry["is_new_character"]      = True
                entry["character_sheet_prompt"] = _build_character_sheet_prompt(
                    species_name, channel, scene_text
                )
                entry["character_sheet_filename"] = f"{channel.lower()}-{species_name.lower().replace(' ', '-')}-character-sheet.jpg"
                entry["scenes_featuring_character"] = new_characters[species_name]
                entry["storyboard_update_needed"]   = True

        results.append(entry)

    # Add storyboard update info to all scenes featuring new characters
    for entry in results:
        species = entry.get("species_name")
        if species and species in new_characters:
            entry["storyboard_update_scenes"] = new_characters[species]

    print(f"[References] Analysed {len(results)} scenes")
    print(f"[References] New characters needing sheets: {list(new_characters.keys())}")
    return results


def get_missing_references(analysis: list) -> list:
    """Return only scenes with MISSING status."""
    return [s for s in analysis if s.get("status") == "MISSING" and s.get("gpt_image_prompt")]


def get_new_characters(analysis: list) -> list:
    """Return unique new characters that need character reference sheets."""
    seen = set()
    new_chars = []
    for scene in analysis:
        if scene.get("is_new_character") and scene.get("species_name"):
            name = scene["species_name"]
            if name not in seen:
                seen.add(name)
                new_chars.append({
                    "name":                   name,
                    "character_sheet_prompt": scene.get("character_sheet_prompt", ""),
                    "filename":               scene.get("character_sheet_filename", ""),
                    "scenes_featuring":       scene.get("scenes_featuring_character", []),
                    "composite_ref_id":       scene.get("reference_id"),
                    "composite_prompt":       scene.get("gpt_image_prompt", ""),
                    "composite_filename":     scene.get("filename", "")
                })
    return new_chars


def update_storyboard_for_new_character(
    scenes: list,
    character_name: str,
    character_sheet_url: str,
    channel: str,
    video_title: str
) -> list:
    """
    After a new character sheet is generated and uploaded, update the
    storyboard video prompts for only the scenes featuring that character.
    Returns the updated scenes list.
    """
    from src.storyboard import generate_scene_video_prompts

    # Find which scenes feature this character
    affected_scenes = [
        s for s in scenes
        if character_name.lower() in s.get("scene_text", "").lower()
        or s.get("species_name", "").lower() == character_name.lower()
    ]

    if not affected_scenes:
        print(f"[References] No scenes found for character: {character_name}")
        return scenes

    affected_nums = [s["scene_number"] for s in affected_scenes]
    print(f"[References] Updating storyboard for {character_name} — scenes: {affected_nums}")

    # Inject character sheet reference into affected scenes
    for scene in affected_scenes:
        scene["character_sheet_ref"] = character_sheet_url
        scene["new_character_name"]  = character_name

    # Re-run Phase 2 storyboard generation for affected scenes only
    updated = generate_scene_video_prompts(
        affected_scenes, channel,
        f"Video featuring {character_name}",
        video_title
    )

    # Merge updated scenes back into the full scene list
    updated_map = {s["scene_number"]: s for s in updated}
    for i, scene in enumerate(scenes):
        if scene["scene_number"] in updated_map:
            scenes[i] = updated_map[scene["scene_number"]]

    print(f"[References] Storyboard updated for {len(affected_scenes)} scenes featuring {character_name}")
    return scenes
