"""
references.py — Analyse script scenes and identify reference image needs.
Checks existing reference library in state.json.
Generates GPT Image 2 prompts for missing references.
"""

import os
import json
import requests
from src.state import get_channel_state

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Reference keyword mappings per channel
REFERENCE_KEYWORDS = {
    "AE": {
        "ae-composite-apex-deep-ocean":    ["megalodon", "deep ocean", "apex predator", "ocean predator deep"],
        "ae-composite-apex-eocene-sea":    ["eocene", "shallow sea", "warm ocean", "mosasaur surface"],
        "ae-composite-megafauna-tundra":   ["mammoth", "tundra", "ice age", "pleistocene", "woolly"],
        "ae-composite-megafauna-fossil":   ["fossil site", "excavation", "fossil record", "bone discovery"],
        "ae-composite-terrestrial-strata": ["geological strata", "cliff face", "rock layers", "t-rex strata"],
        "ae-megalodon-gpt2-ref-1":         ["megalodon", "otodus"],
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
        "gia-composite-analyst-ops-room":     ["analyst", "operations room", "war room", "intelligence analyst"],
        "gia-composite-analyst-corridor":     ["analyst corridor", "institutional corridor", "government building"],
        "gia-composite-analyst-field":        ["analyst field", "field intelligence", "outdoor intel"],
        "gia-composite-powerfigure-corridor": ["power figure", "kremlin", "leader corridor"],
        "gia-composite-powerfigure-ops-room": ["power figure ops", "leader operations", "kremlin chamber"],
        "gia-composite-operator-field":       ["operator field", "tactical", "military field"],
        "gia-map-hormuz":                     ["strait of hormuz", "hormuz", "persian gulf strait"],
        "gia-map-chokepoints":               ["maritime chokepoints", "global chokepoints", "shipping lanes"],
        "gia-map-south-china-sea":           ["south china sea", "spratly", "south sea dispute"],
        "gia-map-nato-eastern-flank":        ["nato eastern flank", "suwalki", "nato europe"],
        "gia-map-indo-pacific-alliances":    ["indo-pacific", "aukus", "quad alliance"],
        "gia-map-middle-east-power":         ["middle east map", "iran proxy", "gulf region"],
        "gia-map-europe-gas-pipelines":      ["nord stream", "gas pipeline", "europe energy"],
        "gia-map-lng-trade-routes":          ["lng routes", "liquefied natural gas", "energy trade"],
        "gia-map-critical-minerals":         ["critical minerals", "rare earth", "supply chain map"],
        "gia-map-miscalculation-zones":      ["miscalculation zones", "escalation risk", "tripwire"],
        "gia-map-nuclear-tripwires":         ["nuclear", "tripwire", "nuclear risk zones"],
        "gia-map-ukraine-theater":           ["ukraine", "front line", "ukraine war"],
        "gia-map-taiwan-theater":            ["taiwan strait", "taiwan theater", "pla taiwan"],
        "gia-map-red-sea-theater":           ["red sea", "houthi", "bab-el-mandeb", "horn of africa"],
    },
    "BF": {
        "bf-composite-researcher-desert":    ["researcher desert", "archaeologist desert", "fieldwork desert"],
        "bf-composite-researcher-temple":    ["researcher temple", "archaeologist temple", "inside temple"],
        "bf-composite-prophet-desert":       ["prophet", "ancient prophet", "biblical prophet"],
        "bf-composite-nephilim-desert":      ["nephilim", "giant figure", "giant ancient"],
        "bf-composite-highpriest-temple":    ["high priest", "temple priest", "ancient priest"],
        "bf-composite-fallen-cave":          ["fallen angel", "cave angel", "winged figure cave"],
        "bf-map-giant-discoveries":          ["giant discoveries", "nephilim map", "giant bones map"],
        "bf-map-ancient-near-east":          ["dead sea", "qumran", "ancient near east", "ancient israel"],
        "bf-map-temple-mount":               ["temple mount", "jerusalem temple", "solomon temple map"],
        "bf-map-ancient-sites-world":        ["gobekli tepe", "ancient sites", "megalithic sites world"],
        "bf-map-enoch-geography":            ["mount hermon", "watchers descended", "enoch geography"],
        "bf-map-smithsonian-campus":         ["smithsonian campus", "washington dc museum"],
    }
}

GPT_IMAGE_PROMPTS = {
    "ae-megalodon-gpt2-ref-1": """GPT Image 2, thinking mode enabled. Scientifically accurate reference image of Otodus megalodon for prehistoric documentary production. Visual quality: Prehistoric Planet / BBC Earth. Otodus megalodon, late Miocene, 15-18 meters long. Full lateral profile, complete body visible. Correct anatomy: robust fusiform body, large crescent caudal fin, broad pectoral fins, conical snout. Counter-shaded: dark grey-blue dorsal, pale off-white ventral. Modern great white shark alongside at correct relative scale (5 meters vs 18 meters). Deep Miocene Pacific Ocean, cold blue-black water, surface light creating cold caustic patterns. Netflix/BBC Earth natural history grade. This is a real animal at real scale — not a monster movie.""",

    "ae-mammoth-gpt2-ref-1": """GPT Image 2, thinking mode enabled. Scientifically accurate reference image of Mammuthus primigenius — Woolly Mammoth — for prehistoric documentary production. Visual quality: Prehistoric Planet / BBC Earth. Pleistocene epoch, 20,000 years ago. Full lateral profile. Correct anatomy: 3.4m shoulder height, long curved tusks ~3 meters, pronounced shoulder hump, thick dense brown-auburn fur, small ears, high-domed head. Modern human silhouette shown at correct scale (1.75m). Pleistocene Siberian tundra, compacted snow, heavy overcast grey-white sky, flat diffused cold light. Warm orange-grey hull against cold grey-blue world.""",

    "ae-trex-gpt2-ref-1": """GPT Image 2, thinking mode enabled. Scientifically accurate reference image of Tyrannosaurus rex for prehistoric documentary. Visual quality: Prehistoric Planet. Late Cretaceous, Hell Creek Formation, 66 million years ago. Three-quarter view, full body visible. Correct modern posture: horizontal body balanced over hindlimbs, forward-leaning, tail as counterbalance. Robust skull, tiny two-clawed forelimbs, massive hindlimbs. Sparse feather-like integument on upper body consistent with paleontological evidence. Dark earth tones, subtle countershading. African elephant silhouette at correct scale alongside. Late Cretaceous forest, warm amber afternoon light through ancient canopy.""",

    "ae-mosasaur-gpt2-ref-1": """GPT Image 2, thinking mode enabled. Scientifically accurate reference image of Mosasaurus hoffmannii for prehistoric documentary. Visual quality: Prehistoric Planet / BBC Earth. Late Cretaceous Western Interior Seaway, 66 million years ago. Full lateral profile in warm ancient ocean. Correct anatomy: 14-17 meters, four paddle-like limbs, laterally flattened tail with small fluke, long narrow skull with conical teeth, forked tongue visible. Dark counter-shading, grey-green dorsally, pale ventrally. Modern great white shark at correct relative scale (5 meters). Warm tropical Cretaceous sea, amber-gold sunlight from above creating caustic patterns.""",

    "ae-sabertooth-gpt2-ref-1": """GPT Image 2, thinking mode enabled. Scientifically accurate reference image of Smilodon fatalis for prehistoric documentary. Visual quality: Prehistoric Planet. Pleistocene, 12,000 years ago. Three-quarter view, full body visible. Correct anatomy: more robustly built than modern lion, deep chest, powerful forelimbs, short hindlimbs, short bob-tail. Two characteristic upper canines extending ~18cm below jaw when closed. Tawny coat, possible subtle rosette patterning, possible neck mane or ruff. Modern African lion at correct relative scale. Late Pleistocene California grassland, late afternoon amber light.""",
}


def _find_matching_refs(scene_text: str, channel: str) -> list[str]:
    """Find reference image IDs that match a scene based on keyword presence."""
    scene_lower = scene_text.lower()
    channel_refs = REFERENCE_KEYWORDS.get(channel, {})
    matches = []
    for ref_id, keywords in channel_refs.items():
        if any(kw.lower() in scene_lower for kw in keywords):
            matches.append(ref_id)
    return matches


def analyse_script_references(script_text: str, channel: str) -> list[dict]:
    """
    Analyse a script and return per-scene reference analysis.
    Uses Claude to break script into scenes and identify references needed.
    """
    from src.state import get_channel_state
    ch_state = get_channel_state(channel)
    ref_library = ch_state["reference_library"]

    # Use Claude to parse scenes and identify reference needs
    prompt = f"""Analyse this script for the YouTube channel "{ch_state['channel_name']}" 
and identify what reference images each scene needs.

Script:
{script_text[:4000]}

For each scene (break at sentence boundaries, ~10 words per scene), identify:
1. The scene text
2. Which character archetype appears (if any)
3. Which environment type appears
4. Whether a map reference might be needed

Return a JSON array. Each element:
{{
  "scene_number": 1,
  "scene_text": "exact words for this scene",
  "character_type": "the-analyst|the-operator|the-power-figure|apex-predator|ice-age-megafauna|terrestrial-giant|the-researcher|the-prophet|the-nephilim|the-high-priest|the-fallen|none",
  "environment_type": "deep-ocean|eocene-sea|pleistocene-tundra|fossil-site|geological-strata|ops-room|corridor|field|temple-interior|ancient-desert|hidden-text-cave|none",
  "needs_map": true/false,
  "map_type": "map identifier if needs_map is true, else null"
}}

Return ONLY valid JSON array. No markdown."""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 8096,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=60
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip().rstrip("```")

    scenes = json.loads(text)

    # Determine reference image and status for each scene
    COMPOSITE_MAP = {
        "AE": {
            ("apex-predator", "deep-ocean"):        "ae-composite-apex-deep-ocean",
            ("apex-predator", "eocene-sea"):         "ae-composite-apex-eocene-sea",
            ("ice-age-megafauna", "pleistocene-tundra"): "ae-composite-megafauna-tundra",
            ("ice-age-megafauna", "fossil-site"):    "ae-composite-megafauna-fossil",
            ("terrestrial-giant", "geological-strata"): "ae-composite-terrestrial-strata",
        },
        "GIA": {
            ("the-analyst", "ops-room"):             "gia-composite-analyst-ops-room",
            ("the-analyst", "corridor"):             "gia-composite-analyst-corridor",
            ("the-analyst", "field"):                "gia-composite-analyst-field",
            ("the-power-figure", "corridor"):        "gia-composite-powerfigure-corridor",
            ("the-power-figure", "ops-room"):        "gia-composite-powerfigure-ops-room",
            ("the-operator", "field"):               "gia-composite-operator-field",
        },
        "BF": {
            ("the-researcher", "ancient-desert"):    "bf-composite-researcher-desert",
            ("the-researcher", "temple-interior"):   "bf-composite-researcher-temple",
            ("the-prophet", "ancient-desert"):       "bf-composite-prophet-desert",
            ("the-nephilim", "ancient-desert"):      "bf-composite-nephilim-desert",
            ("the-high-priest", "temple-interior"):  "bf-composite-highpriest-temple",
            ("the-fallen", "hidden-text-cave"):      "bf-composite-fallen-cave",
        }
    }

    results = []
    for scene in scenes:
        char_type = scene.get("character_type", "none")
        env_type  = scene.get("environment_type", "none")

        # Find composite
        composite_key = (char_type, env_type)
        composite_map = COMPOSITE_MAP.get(channel, {})
        ref_id = composite_map.get(composite_key)

        # Check status
        if ref_id:
            url = ref_library.get(ref_id, "")
            if url:
                status = "COVERED"
            else:
                status = "MISSING"
                prompt_text = GPT_IMAGE_PROMPTS.get(ref_id, "")
        else:
            # Look for species-specific ref
            scene_text = scene.get("scene_text", "")
            matches = _find_matching_refs(scene_text, channel)
            if matches:
                ref_id = matches[0]
                url = ref_library.get(ref_id, "")
                status = "COVERED" if url else "MISSING"
            else:
                ref_id = None
                status = "NO_REF_NEEDED"

        entry = {
            "scene_number": scene["scene_number"],
            "scene_text": scene.get("scene_text", ""),
            "reference_id": ref_id,
            "status": status,
            "character_type": char_type,
            "environment_type": env_type,
        }

        if status == "MISSING" and ref_id:
            entry["gpt_image_prompt"] = GPT_IMAGE_PROMPTS.get(ref_id, "")
            filename = f"{ref_id}.jpg"
            entry["filename"] = filename
            folder_map = {
                "AE": "AE-Reference-Images",
                "GIA": "GIA-Reference-Images",
                "BF": "BF-Reference-Images"
            }
            entry["upload_to"] = folder_map.get(channel, "Reference-Images")

        results.append(entry)

    return results


def get_missing_references(analysis: list[dict]) -> list[dict]:
    """Filter to only scenes with MISSING status."""
    return [s for s in analysis if s["status"] == "MISSING" and s.get("gpt_image_prompt")]
