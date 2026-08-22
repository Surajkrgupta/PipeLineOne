"""Reconstructs YouTube OAuth secret files from base64-encoded environment
variables at application startup.

Why this exists: secrets/client_secret.json and secrets/yt_token.json are
correctly gitignored (never committed), which means on a fresh host like
Render they simply don't exist in the container -- there's no git-based path
to get them there. Environment variables ARE the correct way to pass secrets
to a container, but they're plain text values, not files, and the Google
OAuth libraries expect actual files on disk.

The fix: base64-encode each file's contents locally, store the resulting
string as an env var (YT_CLIENT_SECRET_B64 / YT_TOKEN_B64), and decode it
back to a real file here on every container boot. This runs before the app
starts serving requests, and it's idempotent -- safe to run on every restart.
"""

import base64
import os

from app.config import settings


def restore_youtube_secrets() -> None:
    """Writes secrets/client_secret.json and secrets/yt_token.json from their
    base64 env var counterparts, if those env vars are set. No-ops for any
    file that already exists on disk (e.g. local dev where you placed the
    real files directly) or whose env var isn't set."""
    _restore_one(settings.yt_client_secrets_file, settings.yt_client_secret_b64, "client_secret.json")
    _restore_one(settings.yt_token_file, settings.yt_token_b64, "yt_token.json")


def _restore_one(target_path: str, b64_value: str, label: str) -> None:
    if os.path.exists(target_path):
        print(f"[startup] {label} already exists at {target_path} -- skipping restore from env var")
        return

    if not b64_value:
        print(f"[startup] {label}: no env var set and no existing file -- YouTube upload will fail until this is provided")
        return

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        decoded = base64.b64decode(b64_value)
        with open(target_path, "wb") as f:
            f.write(decoded)
        print(f"[startup] Restored {label} from environment variable to {target_path}")
    except Exception as e:
        print(f"[startup] ERROR: failed to restore {label} from env var: {e}")