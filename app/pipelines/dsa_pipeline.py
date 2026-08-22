"""Orchestrates the full DSA POTD pipeline: fetch -> generate -> render ->
assemble -> (Telegram approval gate) -> upload. Each stage updates the
PipelineRun row so a failure at any point leaves a clear record of how far
it got.

Approval now happens via Telegram inline buttons (Approve/Reject) rather
than an HTTP call -- see notifier.send_approval_request and
app/main.py's /telegram-webhook endpoint, which handles the button taps.
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
    If REQUIRE_MANUAL_APPROVAL is True, sends a Telegram approval request
    and stops -- the webhook handler calls approve_and_upload/reject_run
    when the button is tapped. Otherwise uploads immediately."""

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

    run.theme_name = theme["name"]
    run.voice_name = voice

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
        music_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "music"))
        music_track = variation_engine.get_monthly_music_track(music_dir)

        video_path, duration = video_assembler.assemble_video(
            slide_paths=[title_slide, code_slide, complexity_slide],
            voiceover_path=voiceover_path,
            output_path=f"{run_dir}/final_video.mp4",
            background_music_path=music_track,
        )
        run.video_path = video_path
        run.thumbnail_path = thumbnail_path
        run.video_duration_seconds = duration
        db.commit()
    except Exception as e:
        _fail(db, run, f"video assembly stage: {e}")
        raise

    # --- Approval gate ---
    if settings.require_manual_approval:
        run.status = RunStatus.awaiting_approval
        db.commit()

        result = notifier.send_approval_request(
            run_id=run.id,
            problem_title=run.problem_title,
            difficulty=run.difficulty,
            video_duration_seconds=run.video_duration_seconds,
            theme_name=run.theme_name,
            voice_name=run.voice_name,
        )
        if result["sent"]:
            run.telegram_chat_id = result["chat_id"]
            run.telegram_message_id = result["message_id"]
            db.commit()
        else:
            print(f"[dsa_pipeline] Warning: could not send Telegram approval request for run #{run.id}")

        return run

    return approve_and_upload(db, run)


def approve_and_upload(db: Session, run: PipelineRun) -> PipelineRun:
    """Uploads a rendered run to YouTube, including the custom thumbnail and
    the required synthetic-content disclosure flag. If this run has an
    associated Telegram message, edits it with the final result instead of
    sending a separate notification."""
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
            thumbnail_path=run.thumbnail_path,
        )

        run.youtube_video_id = video_id
        run.status = RunStatus.uploaded
        db.commit()

        final_text = f"✅ *Published!*\n\n{run.problem_title}\n\nhttps://youtu.be/{video_id}"
        if run.telegram_chat_id and run.telegram_message_id:
            notifier.edit_message(run.telegram_chat_id, run.telegram_message_id, final_text)
        else:
            notifier.notify(final_text)

        return run

    except youtube_uploader.YouTubeUploadError as e:
        _fail(db, run, f"upload stage: {e}")
        raise


def reject_run(db: Session, run: PipelineRun) -> PipelineRun:
    """Marks a run as rejected -- called from the Telegram webhook when the
    person taps Reject. Does NOT delete generated files, so you can inspect
    what went wrong if needed; just won't be uploaded."""
    run.status = RunStatus.rejected
    db.commit()

    final_text = f"❌ *Rejected*\n\n{run.problem_title}\n\nThis run will not be published."
    if run.telegram_chat_id and run.telegram_message_id:
        notifier.edit_message(run.telegram_chat_id, run.telegram_message_id, final_text)

    return run


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
            .filter(PipelineRun.status.notin_([RunStatus.uploaded, RunStatus.rejected, RunStatus.failed]))
            .order_by(PipelineRun.created_at.desc())
            .first()
        )
        if stuck_run:
            _fail(db, stuck_run, f"unhandled exception: {tb[-500:]}")
        return None