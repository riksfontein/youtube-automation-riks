"""
tts.py — ElevenLabs TTS with character-level timestamps.
Calls /with-timestamps endpoint directly.
Returns narration audio + precise timing data for FFmpeg assembly.
"""

import os
import json
import time
import struct
import requests
from pathlib import Path

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_BASE    = "https://api.elevenlabs.io/v1"

TTS_SETTINGS = {
    "model_id":        "eleven_multilingual_v2",
    "voice_settings": {
        "speed":           0.85,
        "stability":       0.75,
        "similarity_boost": 0.75,
        "style":           0.35,
        "use_speaker_boost": True
    }
}

SILENCE_PADDING_SECONDS = 1.5


def generate_tts_with_timestamps(
    script_text: str,
    voice_id: str,
    output_dir: Path
) -> dict:
    """
    Generate narration audio with character-level timestamp data.
    Returns dict with:
        - audio_path: path to narration_padded.wav
        - timestamps: list of {char, start_time, end_time}
        - word_timestamps: aggregated word-level timing
        - scene_timings: list of {scene_number, start_ms, end_ms, duration_ms, text}
        - chapter_timings: list of {chapter_name, start_time_seconds}
        - srt_content: formatted SRT caption file content
        - total_duration_seconds: float
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[TTS] Generating narration with voice {voice_id}")
    print(f"[TTS] Script length: {len(script_text.split())} words")

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": script_text,
        "model_id": TTS_SETTINGS["model_id"],
        "voice_settings": TTS_SETTINGS["voice_settings"]
    }

    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}/with-timestamps"
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()

    data = resp.json()

    # Extract audio bytes (base64 encoded)
    import base64
    audio_b64   = data.get("audio_base64") or data.get("audio", "")
    audio_bytes = base64.b64decode(audio_b64)

    # Extract character timestamps
    alignment = data.get("alignment") or data.get("normalized_alignment") or {}
    chars       = alignment.get("characters", [])
    char_starts = alignment.get("character_start_times_seconds", [])
    char_ends   = alignment.get("character_end_times_seconds", [])

    timestamps = []
    for i, char in enumerate(chars):
        timestamps.append({
            "char":       char,
            "start_time": char_starts[i] if i < len(char_starts) else 0,
            "end_time":   char_ends[i]   if i < len(char_ends)   else 0
        })

    # Add silence padding to audio
    audio_path = output_dir / "narration_padded.wav"
    padded = _add_silence_padding(audio_bytes, SILENCE_PADDING_SECONDS)
    audio_path.write_bytes(padded)
    print(f"[TTS] Audio saved: {audio_path}")

    # Calculate total duration
    total_duration = char_ends[-1] + SILENCE_PADDING_SECONDS if char_ends else 0

    # Build word-level timestamps
    word_timestamps = _build_word_timestamps(timestamps)

    # Build SRT captions
    srt_content = _build_srt(word_timestamps)

    # Save SRT
    srt_path = output_dir / "captions.srt"
    srt_path.write_text(srt_content, encoding="utf-8")
    print(f"[TTS] Captions saved: {srt_path}")

    # Save raw timestamps for scene assignment
    ts_path = output_dir / "timestamps.json"
    ts_path.write_text(json.dumps({
        "characters": timestamps,
        "words":      word_timestamps,
        "total_duration_seconds": total_duration
    }, indent=2))

    return {
        "audio_path":             str(audio_path),
        "srt_path":               str(srt_path),
        "timestamps_path":        str(ts_path),
        "word_timestamps":        word_timestamps,
        "total_duration_seconds": total_duration,
        "srt_content":            srt_content
    }


def generate_music(duration_seconds: float, music_prompt: str, output_dir: Path) -> str:
    """
    Generate background music via ElevenLabs Music API.
    Always appends: completely instrumental, absolutely no vocals.
    Returns path to music.mp3
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_prompt = (
        music_prompt.rstrip() +
        " completely instrumental, absolutely no vocals, no singing, no choir, no chanting"
    )

    print(f"[TTS] Generating music ({duration_seconds:.1f}s)...")

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    # ElevenLabs Music API
    payload = {
        "prompt":   safe_prompt,
        "duration": min(int(duration_seconds) + 10, 300)  # buffer
    }

    try:
        resp = requests.post(
            f"{ELEVENLABS_BASE}/text-to-music",
            headers=headers,
            json=payload,
            timeout=120
        )
        resp.raise_for_status()

        music_path = output_dir / "music.mp3"
        music_path.write_bytes(resp.content)
        print(f"[TTS] Music saved: {music_path}")
        return str(music_path)

    except Exception as e:
        print(f"[TTS] Music generation failed: {e}")
        # Return empty string — assembly will skip music if not found
        return ""


def assign_scene_timings(script_text: str, timestamps_path: str) -> list[dict]:
    """
    Split the script into scenes (~10 words each) and assign exact
    start/end times from the ElevenLabs timestamp data.
    Returns list of scene timing dicts.
    """
    with open(timestamps_path) as f:
        ts_data = json.load(f)

    word_timestamps = ts_data["words"]

    # Split script into scenes by sentence/phrase boundaries
    # Target: ~10 words per scene, max 13 words
    words = script_text.split()
    scenes = []
    scene_words = []
    scene_num = 1

    for word in words:
        scene_words.append(word)
        # Break at punctuation or word count limit
        word_stripped = word.rstrip(".,;:!?")
        if (len(scene_words) >= 10 and word[-1] in ".!?,;:") or len(scene_words) >= 13:
            scenes.append({
                "scene_number": scene_num,
                "text": " ".join(scene_words)
            })
            scene_words = []
            scene_num += 1

    # Remaining words
    if scene_words:
        scenes.append({
            "scene_number": scene_num,
            "text": " ".join(scene_words)
        })

    # Assign timestamps to scenes
    word_index = 0
    scene_timings = []

    for scene in scenes:
        scene_word_count = len(scene["text"].split())
        end_index = min(word_index + scene_word_count, len(word_timestamps))

        if word_index < len(word_timestamps):
            start_ms = int(word_timestamps[word_index]["start_time"] * 1000)
        else:
            start_ms = 0

        if end_index > 0 and end_index <= len(word_timestamps):
            end_ms = int(word_timestamps[end_index - 1]["end_time"] * 1000)
        else:
            end_ms = start_ms + 4000  # fallback 4s

        duration_ms = max(end_ms - start_ms, 1000)  # minimum 1 second

        scene_timings.append({
            "scene_number":  scene["scene_number"],
            "text":          scene["text"],
            "start_ms":      start_ms,
            "end_ms":        end_ms,
            "duration_ms":   duration_ms,
            "duration_s":    round(duration_ms / 1000, 3),
            "word_count":    scene_word_count,
            # Grok duration selection: ≤10 words = 6s clip, 11-13 words = 10s clip
            "grok_duration": 6 if scene_word_count <= 10 else 10
        })

        word_index = end_index

    print(f"[TTS] Assigned timings to {len(scene_timings)} scenes")
    return scene_timings


def extract_chapter_timings(script_text: str, scene_timings: list[dict]) -> list[dict]:
    """
    Extract chapter start times from scene timings.
    Chapters are identified by ALL CAPS headings in the script.
    """
    chapters = []
    lines = script_text.split("\n")

    # Find chapter names (typically written as headers in Subscribr output)
    chapter_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and (
            stripped.isupper() and len(stripped.split()) <= 10
            or stripped.startswith("##")
            or stripped.startswith("**") and stripped.endswith("**")
        ):
            clean = stripped.strip("#").strip("*").strip()
            if len(clean.split()) >= 3:
                chapter_lines.append(clean)

    if not chapter_lines:
        return [{"chapter_name": "Introduction", "start_time_seconds": 0}]

    # Match chapter positions to scene timings
    full_words = script_text.lower().split()
    chapters = [{"chapter_name": "Introduction", "start_time_seconds": 0}]

    for chapter in chapter_lines[1:]:
        chapter_words = chapter.lower().split()[:4]
        # Find approximate position in script
        for i, scene in enumerate(scene_timings):
            scene_lower = scene["text"].lower()
            if any(w in scene_lower for w in chapter_words):
                chapters.append({
                    "chapter_name":        chapter,
                    "start_time_seconds":  scene["start_ms"] / 1000
                })
                break

    return chapters


def format_chapters_for_description(chapter_timings: list[dict]) -> str:
    """Format chapter timings as YouTube description timestamps."""
    lines = []
    for ch in chapter_timings:
        secs = int(ch["start_time_seconds"])
        mins = secs // 60
        remaining_secs = secs % 60
        timestamp = f"{mins:02d}:{remaining_secs:02d}"
        lines.append(f"{timestamp} {ch['chapter_name']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────

def _add_silence_padding(audio_bytes: bytes, seconds: float) -> bytes:
    """
    Append silence to a WAV file.
    Reads the sample rate and channels from WAV header.
    """
    try:
        # Parse WAV header
        if audio_bytes[:4] != b"RIFF":
            # Not WAV format — return as-is
            return audio_bytes

        sample_rate = struct.unpack_from("<I", audio_bytes, 24)[0]
        num_channels = struct.unpack_from("<H", audio_bytes, 22)[0]
        bits_per_sample = struct.unpack_from("<H", audio_bytes, 34)[0]

        bytes_per_sample = bits_per_sample // 8
        num_silence_samples = int(sample_rate * seconds)
        silence = b"\x00" * (num_silence_samples * num_channels * bytes_per_sample)

        # Append silence after audio data
        return audio_bytes + silence

    except Exception:
        return audio_bytes


def _build_word_timestamps(char_timestamps: list[dict]) -> list[dict]:
    """Aggregate character timestamps into word timestamps."""
    words = []
    current_word = ""
    word_start = None
    word_end = None

    for ts in char_timestamps:
        char = ts["char"]
        if char == " " or char == "\n":
            if current_word.strip():
                words.append({
                    "word":       current_word.strip(),
                    "start_time": word_start or 0,
                    "end_time":   word_end or 0
                })
            current_word = ""
            word_start = None
            word_end = None
        else:
            if word_start is None:
                word_start = ts["start_time"]
            current_word += char
            word_end = ts["end_time"]

    # Last word
    if current_word.strip():
        words.append({
            "word":       current_word.strip(),
            "start_time": word_start or 0,
            "end_time":   word_end or 0
        })

    return words


def _build_srt(word_timestamps: list[dict], words_per_line: int = 7) -> str:
    """Build SRT caption file from word timestamps."""
    if not word_timestamps:
        return ""

    lines = []
    entry_num = 1

    # Group words into subtitle lines
    groups = [
        word_timestamps[i:i + words_per_line]
        for i in range(0, len(word_timestamps), words_per_line)
    ]

    for group in groups:
        if not group:
            continue
        start = group[0]["start_time"]
        end   = group[-1]["end_time"]
        text  = " ".join(w["word"] for w in group)

        start_str = _format_srt_time(start)
        end_str   = _format_srt_time(end)

        lines.append(f"{entry_num}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
        entry_num += 1

    return "\n".join(lines)


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format HH:MM:SS,mmm"""
    ms       = int((seconds % 1) * 1000)
    total_s  = int(seconds)
    s        = total_s % 60
    m        = (total_s // 60) % 60
    h        = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
