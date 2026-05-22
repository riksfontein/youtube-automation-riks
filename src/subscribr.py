"""Subscribr REST API wrapper.

Base URL and endpoints from master briefing Section 7. Authentication is
Bearer token with the Subscribr API key.

This module is intentionally small in Phase 2 — only the credits check is
implemented. Ideas / outline / script / humanize / thumbnail endpoints land
in Phases 5 and 9.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import Config

DEFAULT_TIMEOUT = 30  # seconds


class SubscribrError(RuntimeError):
    """Raised when Subscribr returns an error or unexpected response shape."""


@dataclass
class CreditsResponse:
    credits_remaining: int
    raw: dict[str, Any]


class SubscribrClient:
    def __init__(self, config: Config) -> None:
        self._base = config.subscribr_base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.subscribr_api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base}{path}"
        resp = self._session.get(url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code >= 400:
            raise SubscribrError(
                f"GET {path} failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise SubscribrError(
                f"GET {path} returned non-JSON: {resp.text[:500]}"
            ) from exc

    def get_credits(self) -> CreditsResponse:
        """GET /team/credits — used at the start of every scheduled run.

        Per briefing Section 7 Step 1.2: if credits_remaining < 5, the pipeline
        sends a warning email and halts.
        """
        body = self._get("/team/credits")
        try:
            credits_data = body.get("credits", body)
            remaining = int(credits_data["credits_remaining"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SubscribrError(
                f"Could not parse credits from response: {body!r}"
            ) from exc
        return CreditsResponse(credits_remaining=remaining, raw=body)
