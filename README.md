# DSA POTD → YouTube Automation Pipeline

Fully automated: fetch LeetCode's Problem of the Day → generate solution +
human-sounding narration via LLM → render themed slides + thumbnail →
synthesize voiceover → assemble video → upload to YouTube with disclosure.

## Tech stack

| Layer | Tool |
|---|---|
| API framework | FastAPI |
| Scheduling | APScheduler (daily cron) |
| Database | SQLite (SQLAlchemy ORM) |
| LLM | Groq (hosted, free tier) or Ollama (local, free) |
| Slide/thumbnail rendering | Playwright + Jinja2 + Pygments |
| Voiceover | edge-tts |
| Video assembly | MoviePy + imageio_ffmpeg |
| Publishing | YouTube Data API v3 |
| Notifications | Telegram Bot API |
| Deployment | Docker (recommended) or Render native buildpack |

## Architecture

```
LeetCode GraphQL
      │
      ▼
variation_engine (picks this week's theme/voice/tone, this month's music)
      │
      ▼
llm_generator (Groq/Ollama) ──► approach + code + complexity + narration script
      │
      ▼
code_renderer ──► title slide, code slide, complexity slide, thumbnail (themed)
tts_generator ──► voiceover.mp3 (rotating voice)
      │
      ▼
video_assembler ──► final_video.mp4 (slides + voice + rotating background music)
      │
      ▼
[Manual approval gate, if enabled]
      │
      ▼
youtube_uploader ──► uploads video + thumbnail + synthetic-content disclosure
      │
      ▼
notifier (Telegram) ──► confirms success/failure at every stage
```

Every run is tracked in the `pipeline_runs` SQLite table -- you always know
exactly which stage a run reached and why it failed if it did.

## Why the variation engine matters (read this before going live)

YouTube's inauthentic-content policy targets templated, interchangeable
videos -- same layout, same voice, same structure, every time. This pipeline
avoids that by rotating, **automatically, with zero manual switching**:

- **Weekly**: visual theme (5 color/font combos), TTS voice (4 options),
  narration tone (4 styles), video opening style (4 styles)
- **Monthly**: background music track (pool in `assets/music/`)

All rotation is deterministic (seeded by week/month number), so it changes
on schedule without you touching config, and it's reproducible if you ever
need to check what was active on a given date.

**You must still**: set the "Altered or synthetic content" disclosure on
every upload (this pipeline does it automatically via the API), and use the
manual approval gate to actually watch/edit videos, not just rubber-stamp
them -- especially in your first few weeks.

## Setup

### 1. Clone and install locally (for testing before deploying)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # add --with-deps only on Linux with root access
```

Windows users: `playwright install chromium` alone is enough -- Windows
doesn't need the Linux system library step.

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in:
- `GROQ_API_KEY` -- free at https://console.groq.com. **Check the model
  list there before deploying** -- Groq periodically retires older model
  names (this has already happened once during this project's development).
- Leave `REQUIRE_MANUAL_APPROVAL=true` until you trust the output.

### 3. Set up YouTube API access (one-time)

1. [Google Cloud Console](https://console.cloud.google.com) → new project →
   enable **YouTube Data API v3**.
2. Create OAuth2 credentials, type **Desktop app** → download as JSON.
3. Save as `secrets/client_secret.json`.
4. Run once locally: `python -m app.services.youtube_uploader` -- opens a
   browser for consent, then caches a refresh token so future runs (even on
   a headless server) never need browser interaction again.
5. Upload the resulting `secrets/yt_token.json` to your server/host alongside
   `client_secret.json` (both are gitignored -- never commit them).

### 4. Set up Telegram notifications (recommended)

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` →
   follow prompts → copy the bot token into `TELEGRAM_BOT_TOKEN`.
2. Message your new bot once (anything), then visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser --
   find your `chat.id` in the JSON response, put it in `TELEGRAM_CHAT_ID`.
3. **Verify it works** by starting the app and calling:
   ```bash
   curl -X POST http://localhost:8000/test-telegram
   ```
   You should get a message in Telegram within a few seconds. If not,
   double check the token/chat ID -- this is a common setup mistake.

### 5. Add background music (optional but recommended)

Drop 4 royalty-free tracks into `assets/music/` named exactly:
```
track_calm_lofi.mp3
track_upbeat_corporate.mp3
track_ambient_focus.mp3
track_minimal_piano.mp3
```
(Get free tracks from YouTube Audio Library or Pixabay Music.) If this
folder is empty, the pipeline still works -- it just skips background music.

### 6. Run locally

```bash
uvicorn app.main:app --reload
```

## Deploying (Render or similar)

**Recommended: Docker deploy.** Render's native Python buildpack cannot run
`playwright install --with-deps` (it requires root access the buildpack
doesn't grant -- you'll see `su: Authentication failure` if you try). The
included `Dockerfile` sidesteps this entirely by installing Chromium's
system dependencies during the Docker build, which does have root access.

On Render: **New → Web Service → connect repo → Environment: Docker**
(Render auto-detects the `Dockerfile`). No custom build/start command needed
-- it's all in the Dockerfile.

**If you must use the native buildpack instead**, set the Build Command to:
```
pip install -r requirements.txt && playwright install chromium
```
(without `--with-deps` -- it will fail the build otherwise). This works for
most cases but can occasionally hit missing shared-library errors at
runtime that only Docker fully avoids.

### Environment variables on Render

Your local `.env` file is gitignored and **never reaches Render**. Add every
variable from `.env` manually in Render's **Environment** tab. Common miss:
forgetting this step, or forgetting to redeploy after adding them.

### Known Render-specific gotchas

- **Free tier disk is ephemeral** -- `data/pipeline.db` and generated videos
  are wiped on every redeploy/restart. Fine for testing; for production,
  use a Render persistent disk or move to hosted Postgres.
- **Free tier spins down when idle** -- the in-app APScheduler cron won't
  fire reliably if the service is asleep. Either use a paid always-on plan,
  or ping `POST /run/dsa-pipeline` on a schedule via a free external cron
  service like cron-job.org.

## API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/run/dsa-pipeline` | POST | Trigger today's pipeline immediately |
| `/runs` | GET | List the last 30 runs and their status |
| `/runs/{id}` | GET | Get details of a specific run |
| `/approve/{id}` | POST | Approve a rendered video and publish to YouTube |
| `/test-telegram` | POST | Verify Telegram notifications are configured correctly |
| `/health` | GET | Basic liveness check |

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| Run stuck at `fetched` forever | Exception swallowed by background task | Already handled -- `run_dsa_pipeline_safe` guarantees a DB update |
| `Client.__init__() got an unexpected keyword argument 'proxies'` | `httpx`/`groq` version mismatch | Ensure `httpx==0.27.2` is installed (in requirements.txt already) |
| `model_not_found` / 404 from Groq | Model name retired | Check https://console.groq.com/docs/models, update `GROQ_MODEL` |
| `NotImplementedError` from Playwright on Windows | Background thread uses wrong asyncio event loop | Already handled in `code_renderer.py` |
| `APIConnectionError` from Groq on Render | Render injects proxy env vars `httpx` tries to use | Already handled via `trust_env=False` in `llm_generator.py` |
| `su: Authentication failure` during Render build | `--with-deps` needs root, buildpack denies it | Use the included Dockerfile instead |
| Pipeline skips a problem you expected to retry | Dedup check found existing `problem_slug` row | Delete that row from the DB, or clear `data/pipeline.db` entirely for a fresh start |

## Recommended workflow while validating quality

1. `POST /run/dsa-pipeline`
2. `GET /runs` -- wait for `awaiting_approval`
3. Open the video file (path in `GET /runs/{id}`), actually watch it
4. If good: `POST /approve/{id}`
5. Once you trust output consistently over 2-3 weeks: set
   `REQUIRE_MANUAL_APPROVAL=false` for hands-off operation

## Next steps / not yet built

- No frontend dashboard -- drive everything via `/runs` + `/approve` for now
- Slide timing is split evenly across narration duration, not synced to
  sentence boundaries -- fine for short scripts, worth improving for longer ones
- Solution code isn't executed against example test cases before being shown
  on screen -- the LLM occasionally gets edge cases wrong on harder problems,
  which is exactly why the manual approval gate exists
