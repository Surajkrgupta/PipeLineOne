"""Orchestrates the full DSA POTD pipeline: fetch -> generate -> render ->
assemble -> (approval gate) -> upload. Each stage updates the PipelineRun row
so a failure at any point leaves a clear record of how far it got.

This version wires in variation_engine so theme, narration tone, voice, and
music all rotate automatically (weekly for visuals/voice/tone, monthly for
music) -- no manual switching, and no two consecutive weeks look identical,
which matters for staying clear of YouTube's inauthentic-content policy.
"""

import os

from sqlalchemy.orm import Session

from app.config import settings
from app.models import PipelineRun, RunStatus
from app.services import (
    code_renderer,
    leetcode_fetcher,
    llm_generator,
    notifier,
    tts_generator,
    variation_engine,
    video_assembler,
    youtube_uploader,
)


def run_dsa_pipeline(db: Session) -> PipelineRun:
    """Runs stages 1-4 (fetch, generate, render, assemble) always.
    If REQUIRE_MANUAL_APPROVAL is True, stops and waits for a call to
    approve_and_upload(). Otherwise uploads immediately."""

    # --- Stage 1: fetch ---
    try:
        problem = leetcode_fetcher.fetch_potd()
    except leetcode_fetcher.LeetCodeFetchError as e:
        notifier.notify(f"❌ DSA pipeline failed at fetch stage: {e}")
        raise

    existing = db.query(PipelineRun).filter_by(problem_slug=problem["problem_slug"]).first()
    if existing:
        notifier.notify(f"ℹ️ POTD '{problem['title']}' already processed (run #{existing.id}). Skipping.")
        return existing

    run = PipelineRun(
        problem_slug=problem["problem_slug"],
        problem_title=problem["title"],
        difficulty=problem["difficulty"],
        status=RunStatus.fetched,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_dir = os.path.join(settings.output_dir, f"run_{run.id}")
    os.makedirs(run_dir, exist_ok=True)

    # Pick this week's/month's variation choices ONCE per run, so every
    # asset in this video (slides, thumbnail, voice, music) is consistent.
    theme = variation_engine.get_weekly_theme()
    voice = variation_engine.get_weekly_voice()
    tone = variation_engine.get_weekly_narration_tone()
    opening_style = variation_engine.get_weekly_opening_style()

    # --- Stage 2: LLM generation ---
    try:
        generated = llm_generator.generate_solution(problem, narration_tone=tone, opening_style=opening_style)
        run.script_text = generated["narration_script"]
        run.solution_code = generated["solution_code"]
        run.status = RunStatus.generated
        db.commit()
    except llm_generator.LLMGenerationError as e:
        _fail(db, run, f"generation stage: {e}")
        raise

    # --- Stage 3: render slides + thumbnail + voiceover ---
    try:
        title_slide = code_renderer.render_title_slide(
            run.problem_title, run.difficulty, theme, f"{run_dir}/slide_title.png"
        )
        code_slide = code_renderer.render_code_slide(
            run.solution_code, theme, f"{run_dir}/slide_code.png"
        )
        complexity_slide = code_renderer.render_complexity_slide(
            generated["time_complexity"], generated["space_complexity"], theme, f"{run_dir}/slide_complexity.png"
        )
        thumbnail_path = code_renderer.render_thumbnail(
            run.problem_title, run.difficulty, theme, f"{run_dir}/thumbnail.png"
        )
        voiceover_path = tts_generator.generate_voiceover(
            run.script_text, f"{run_dir}/voiceover.mp3", voice=voice
        )
        run.status = RunStatus.rendered
        db.commit()
    except Exception as e:
        _fail(db, run, f"rendering stage: {e}")
        raise

    # --- Stage 4: assemble video ---
    try:
        music_dir = os.path.join(os.path.dirname(settings.output_dir), "..", "assets", "music")
        music_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "music"))
        music_track = variation_engine.get_monthly_music_track(music_dir)

        video_path = video_assembler.assemble_video(
            slide_paths=[title_slide, code_slide, complexity_slide],
            voiceover_path=voiceover_path,
            output_path=f"{run_dir}/final_video.mp4",
            background_music_path=music_track,
        )
        run.video_path = video_path
        run.thumbnail_path = thumbnail_path
    except Exception as e:
        _fail(db, run, f"video assembly stage: {e}")
        raise

    # --- Approval gate ---
    if settings.require_manual_approval:
        run.status = RunStatus.awaiting_approval
        db.commit()
        notifier.notify(
            f"🎬 Video ready for review: '{run.problem_title}' (run #{run.id})\n"
            f"Theme: {theme['name']} | Voice: {voice}\n"
            f"File: {video_path}\n"
            f"Call POST /approve/{run.id} to publish, or review the file first."
        )
        return run

    return approve_and_upload(db, run)


def approve_and_upload(db: Session, run: PipelineRun) -> PipelineRun:
    """Uploads a rendered run to YouTube, including the custom thumbnail and
    the required synthetic-content disclosure flag."""
    try:
        run.status = RunStatus.uploading
        db.commit()

        title = f"{run.problem_title} - LeetCode Daily Challenge Solution ({run.difficulty})"
        description = (
            f"Solution walkthrough for today's LeetCode Problem of the Day: {run.problem_title}.\n\n"
            f"Difficulty: {run.difficulty}\n\n"
            f"This video uses AI-assisted narration and visuals.\n\n"
            f"#LeetCode #DSA #CodingInterview #Programming"
        )
        video_id = youtube_uploader.upload_video(
            video_path=run.video_path,
            title=title,
            description=description,
            tags=["leetcode", "dsa", "coding interview", run.problem_title.lower()],
            thumbnail_path=getattr(run, "thumbnail_path", None),
        )

        run.youtube_video_id = video_id
        run.status = RunStatus.uploaded
        db.commit()
        notifier.notify(f"✅ Uploaded: https://youtu.be/{video_id}")
        return run

    except youtube_uploader.YouTubeUploadError as e:
        _fail(db, run, f"upload stage: {e}")
        raise


def _fail(db: Session, run: PipelineRun, message: str) -> None:
    run.status = RunStatus.failed
    run.error_message = message
    db.commit()
    notifier.notify(f"❌ DSA pipeline failed for run #{run.id} at {message}")


def run_dsa_pipeline_safe(db: Session) -> PipelineRun | None:
    """Real entry point to call from FastAPI BackgroundTasks / the scheduler.
    Logs the full traceback and, if a run row already exists by this point,
    marks it failed -- so a run can NEVER be left stuck silently."""
    import logging
    import traceback

    logger = logging.getLogger("dsa_pipeline")

    try:
        return run_dsa_pipeline(db)
    except Exception:
        tb = traceback.format_exc()
        logger.error("DSA pipeline crashed:\n%s", tb)
        print(f"[dsa_pipeline] CRASHED:\n{tb}")

        stuck_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.status.notin_([RunStatus.uploaded, RunStatus.failed]))
            .order_by(PipelineRun.created_at.desc())
            .first()
        )
        if stuck_run:
            _fail(db, stuck_run, f"unhandled exception: {tb[-500:]}")
        return None
