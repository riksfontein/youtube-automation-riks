"""Load .env and expose typed config to the rest of the pipeline.

Single source of truth for every API key, URL, and channel ID. Anything that
reads os.environ outside this module is a bug.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
STATE_FILE = PROJECT_ROOT / "state.json"

load_dotenv(ENV_FILE)


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required env var: {name}. "
            f"Set it in {ENV_FILE} (see .env.example for the full list)."
        )
    return val


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip() or default


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str

    subscribr_api_key: str
    subscribr_base_url: str = "https://subscribr.ai/api/v1"

    vidiq_api_key: str = ""
    vidiq_mcp_url: str = "https://mcp.vidiq.com/mcp"
    nexlev_mcp_url: str = "https://prod.dashboard.nexlev.io/api/claude-mcp"

    elevenlabs_api_key: str = ""
    elevenlabs_voice_gia: str = ""
    elevenlabs_voice_bf: str = ""
    elevenlabs_voice_ae_long: str = ""
    elevenlabs_voice_ae_short: str = ""

    resend_api_key: str = ""
    notification_email: str = "info@croki.store"
    notification_from: str = "noreply@croki.store"

    ae_channel_id: str = "56655"
    gia_channel_id: str = "54904"
    bf_channel_id: str = "55636"


def load_config(*, require_all: bool = False) -> Config:
    """Load config from .env.

    By default only Subscribr is required (Phase 2). Set require_all=True once
    every phase is wired up to fail fast on missing keys.
    """
    if require_all:
        anthropic = _required("ANTHROPIC_API_KEY")
        elevenlabs = _required("ELEVENLABS_API_KEY")
        vidiq = _required("VIDIQ_API_KEY")
        resend = _required("RESEND_API_KEY")
    else:
        anthropic = _optional("ANTHROPIC_API_KEY")
        elevenlabs = _optional("ELEVENLABS_API_KEY")
        vidiq = _optional("VIDIQ_API_KEY")
        resend = _optional("RESEND_API_KEY")

    return Config(
        anthropic_api_key=anthropic,
        subscribr_api_key=_required("SUBSCRIBR_API_KEY"),
        vidiq_api_key=vidiq,
        elevenlabs_api_key=elevenlabs,
        elevenlabs_voice_gia=_optional("ELEVENLABS_VOICE_GIA"),
        elevenlabs_voice_bf=_optional("ELEVENLABS_VOICE_BF"),
        elevenlabs_voice_ae_long=_optional("ELEVENLABS_VOICE_AE_LONG"),
        elevenlabs_voice_ae_short=_optional("ELEVENLABS_VOICE_AE_SHORT"),
        resend_api_key=resend,
        notification_email=_optional("NOTIFICATION_EMAIL", "info@croki.store"),
        notification_from=_optional("NOTIFICATION_FROM", "noreply@croki.store"),
        ae_channel_id=_optional("AE_CHANNEL_ID", "56655"),
        gia_channel_id=_optional("GIA_CHANNEL_ID", "54904"),
        bf_channel_id=_optional("BF_CHANNEL_ID", "55636"),
    )
