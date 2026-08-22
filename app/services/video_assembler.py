"""Stitches slide images + voiceover audio into a final video using MoviePy.
Each slide is shown for a duration proportional to its share of the narration,
so visuals stay roughly in sync with what's being said."""

import os

# Hosts like Render/most PaaS free tiers don't have system ffmpeg installed.
# imageio_ffmpeg bundles a static ffmpeg binary -- point MoviePy/imageio at it
# so video encoding works without any OS-level package install.
import imageio_ffmpeg
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", imageio_ffmpeg.get_ffmpeg_exe())

from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips, CompositeAudioClip


def assemble_video(
    slide_paths: list[str],
    voiceover_path: str,
    output_path: str,
    background_music_path: str | None = None,
    music_volume: float = 0.08,
) -> str:
    """slide_paths: ordered list of PNG paths (title, code, complexity, ...).
    Duration is split evenly across slides for v1 -- upgrade later by timing
    slide changes to sentence boundaries in the narration script."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    voice_audio = AudioFileClip(voiceover_path)
    total_duration = voice_audio.duration
    per_slide_duration = total_duration / len(slide_paths)

    clips = [
        ImageClip(path).set_duration(per_slide_duration)
        for path in slide_paths
    ]
    video = concatenate_videoclips(clips, method="compose")

    if background_music_path and os.path.exists(background_music_path):
        music = AudioFileClip(background_music_path).volumex(music_volume)
        # loop music to match video length if it's shorter
        if music.duration < total_duration:
            loops_needed = int(total_duration / music.duration) + 1
            music = concatenate_videoclips([music] * loops_needed).subclip(0, total_duration)
        else:
            music = music.subclip(0, total_duration)
        final_audio = CompositeAudioClip([voice_audio, music])
    else:
        final_audio = voice_audio

    video = video.set_audio(final_audio).set_duration(total_duration)
    # preset="ultrafast" + threads=1: trades a slightly larger file size for
    # much lower peak memory usage during encoding -- matters on memory-
    # constrained hosts like Render's free tier (512MB RAM). Revisit if you
    # move to a host with more headroom and want smaller output files.
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=1,
        logger=None,  # suppress MoviePy's verbose per-frame progress bar in logs
    )

    return output_path