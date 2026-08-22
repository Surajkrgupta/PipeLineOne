"""Converts the narration script to speech using edge-tts (free, uses
Microsoft Edge's neural voices, no API key required)."""

import asyncio
import os

import edge_tts

DEFAULT_VOICE = "en-US-GuyNeural"  # clear, natural male voice; try en-US-AriaNeural for female


async def _synthesize(text: str, output_path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_voiceover(text: str, output_path: str, voice: str | None = None) -> str:
    """Synthesizes `text` to an mp3 file at `output_path`. Returns the path.
    If voice isn't specified, falls back to DEFAULT_VOICE -- callers wanting
    weekly rotation should pass variation_engine.get_weekly_voice()."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    asyncio.run(_synthesize(text, output_path, voice or DEFAULT_VOICE))
    return output_path


if __name__ == "__main__":
    # quick manual check
    generate_voiceover(
        "This is a test of the DSA channel voiceover pipeline.",
        "./data/runs/test_voiceover.mp3",
    )
    print("Saved test voiceover.")
