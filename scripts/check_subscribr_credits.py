"""Phase 2 smoke test — confirms Subscribr API key works.

Usage (from repo root, with venv activated):
    python -m scripts.check_subscribr_credits

Or directly:
    python scripts/check_subscribr_credits.py

Pass criteria: prints `credits_remaining` and exits 0.
Briefing Section 7 Step 1.2: real runs abort if credits < 5.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as a plain script (python scripts/check_subscribr_credits.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.subscribr import SubscribrClient, SubscribrError  # noqa: E402


def main() -> int:
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"[config] {exc}", file=sys.stderr)
        return 2

    client = SubscribrClient(config)
    try:
        result = client.get_credits()
    except SubscribrError as exc:
        print(f"[subscribr] {exc}", file=sys.stderr)
        return 1

    print(f"credits_remaining: {result.credits_remaining}")
    print(f"raw response: {json.dumps(result.raw, indent=2)}")
    if result.credits_remaining < 5:
        print("WARNING: credits < 5 — real runs would abort here.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
