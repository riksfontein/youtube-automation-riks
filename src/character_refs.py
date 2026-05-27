"""
character_refs.py — Character and creature reference sheet generator.

Generates 4-view reference sheet prompts for each channel archetype.
Run this during channel setup to create reference images for NBP.

Usage:
  python src/character_refs.py --channel AE
  python src/character_refs.py --channel AE --archetype apex-predator
  python src/character_refs.py --channel GIA --all
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_all_refs(channel: str) -> dict:
    """Generate reference sheet prompts for all archetypes in a channel."""
    from src.storyboard import CHARACTER_REFERENCE_PROMPTS

    if channel not in CHARACTER_REFERENCE_PROMPTS:
        print(f"[CharRefs] Unknown channel: {channel}")
        return {}

    results = {}
    archetypes = CHARACTER_REFERENCE_PROMPTS[channel]

    print(f"\n[CharRefs] Generating reference prompts for {channel}")
    print(f"[CharRefs] {len(archetypes)} archetypes\n")

    for name, prompt_fn in archetypes.items():
        prompt = prompt_fn()
        results[name] = prompt
        print(f"─── {name} ───")
        print(prompt)
        print()

    return results


def save_refs_to_file(channel: str, results: dict):
    """Save all reference prompts to a text file for easy copy-paste."""
    output_dir = Path(__file__).parent.parent / "docs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{channel}_character_refs.txt"

    lines = [f"CHARACTER REFERENCE SHEET PROMPTS — {channel}\n", "=" * 60, ""]
    for name, prompt in results.items():
        lines.append(f"ARCHETYPE: {name}")
        lines.append("-" * 40)
        lines.append(prompt)
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.append("1. Open Nano Banana Pro or GPT Image 2")
        lines.append("2. Paste the prompt above")
        lines.append(f"3. Save output as: {name}-ref-1.jpg, {name}-ref-2.jpg, {name}-ref-3.jpg, {name}-ref-4.jpg")
        lines.append(f"4. Upload to Google Drive: YouTube-Automation/{channel}/reference-library/")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"[CharRefs] Saved to: {output_file}")
    return str(output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate character reference sheet prompts")
    parser.add_argument("--channel",   required=True, choices=["AE", "GIA", "BF"])
    parser.add_argument("--archetype", default=None, help="Specific archetype name, or omit for all")
    parser.add_argument("--all",       action="store_true", help="Generate all archetypes")
    parser.add_argument("--save",      action="store_true", help="Save prompts to file")

    args = parser.parse_args()

    if args.archetype:
        from src.storyboard import CHARACTER_REFERENCE_PROMPTS
        archetypes = CHARACTER_REFERENCE_PROMPTS.get(args.channel, {})
        if args.archetype not in archetypes:
            print(f"Unknown archetype: {args.archetype}")
            print(f"Available: {list(archetypes.keys())}")
            sys.exit(1)
        prompt = archetypes[args.archetype]()
        print(f"\n{args.archetype}:\n")
        print(prompt)
        results = {args.archetype: prompt}
    else:
        results = generate_all_refs(args.channel)

    if args.save and results:
        save_refs_to_file(args.channel, results)
