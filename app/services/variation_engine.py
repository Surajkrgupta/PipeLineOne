"""Central place for all 'randomized but automated' variation choices --
thumbnail/slide themes, fonts, music tracks, TTS voices, narration tone.

Design choice: everything is seeded by the current week/month number (not
pure random.choice() on every run), so:
  - Within the same week, all videos share a consistent look/voice/tone
    (feels like an intentional design choice, not chaos).
  - It changes automatically every week/month with zero manual intervention.
  - It's reproducible -- if a viewer asks "why did last Tuesday's video look
    different", you can recompute exactly which theme/voice was active.
"""

import random
from datetime import date

# --- Visual themes for slides + thumbnails (rotates weekly) ---
THEMES = [
    {
        "name": "midnight_blue",
        "bg": "#0d1117", "text": "#e6edf3", "accent": "#58a6ff",
        "font": "'Segoe UI', Arial, sans-serif",
    },
    {
        "name": "terminal_green",
        "bg": "#0a0e0a", "text": "#d4f8d4", "accent": "#3ddc3d",
        "font": "'Consolas', 'Courier New', monospace",
    },
    {
        "name": "sunset_orange",
        "bg": "#1a1013", "text": "#fbe8d8", "accent": "#ff8c42",
        "font": "'Trebuchet MS', Arial, sans-serif",
    },
    {
        "name": "royal_purple",
        "bg": "#12081f", "text": "#e8dcf5", "accent": "#a56eff",
        "font": "'Georgia', 'Times New Roman', serif",
    },
    {
        "name": "slate_teal",
        "bg": "#0b1a1a", "text": "#dff5f5", "accent": "#2dd4bf",
        "font": "'Verdana', Arial, sans-serif",
    },
]

# --- Narration tones (rotates weekly) -- injected into the LLM system prompt ---
NARRATION_TONES = [
    "energetic and enthusiastic, like explaining an exciting puzzle to a friend",
    "calm and analytical, like a patient mentor walking through the logic step by step",
    "conversational and slightly informal, using natural filler transitions like 'so here's the thing' or 'now here's where it gets interesting'",
    "direct and confident, focused on quickly getting to the key insight",
]

# --- Video opening styles (rotates weekly) -- injected into the LLM prompt ---
OPENING_STYLES = [
    "Open with a thought-provoking question related to the problem.",
    "Open by stating an interesting or surprising fact about the problem's constraints.",
    "Open by framing the problem as a challenge: 'Here's a problem that trips up a lot of people...'",
    "Open by briefly relating the problem to a real-world analogy before diving in.",
]

# --- edge-tts voices (rotates weekly) ---
VOICES = [
    "en-US-GuyNeural",
    "en-US-AndrewNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
]

# --- Background music pool (rotates monthly) -- filenames expected in assets/music/ ---
MUSIC_TRACKS = [
    "track_calm_lofi.mp3",
    "track_upbeat_corporate.mp3",
    "track_ambient_focus.mp3",
    "track_minimal_piano.mp3",
]


def _week_seed(offset: int = 0) -> int:
    """ISO week number + year, so it changes every week and wraps yearly."""
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return iso_year * 100 + iso_week + offset


def _month_seed(offset: int = 0) -> int:
    today = date.today()
    return today.year * 100 + today.month + offset


def get_weekly_theme() -> dict:
    rng = random.Random(_week_seed(offset=1))  # offset decorrelates from other pickers
    return rng.choice(THEMES)


def get_weekly_narration_tone() -> str:
    rng = random.Random(_week_seed(offset=2))
    return rng.choice(NARRATION_TONES)


def get_weekly_opening_style() -> str:
    rng = random.Random(_week_seed(offset=3))
    return rng.choice(OPENING_STYLES)


def get_weekly_voice() -> str:
    rng = random.Random(_week_seed(offset=4))
    return rng.choice(VOICES)


def get_monthly_music_track(music_dir: str) -> str | None:
    """Returns a full path to the selected month's track, or None if the
    pool is empty / files aren't present yet (caller should handle gracefully)."""
    import os
    rng = random.Random(_month_seed())
    track_name = rng.choice(MUSIC_TRACKS)
    full_path = os.path.join(music_dir, track_name)
    return full_path if os.path.exists(full_path) else None
