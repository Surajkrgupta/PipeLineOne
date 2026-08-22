"""Sends run status notifications via Telegram (free, simple, works from any
server without exposing ports). Optional -- if TELEGRAM_BOT_TOKEN is unset,
notify() silently no-ops so the pipeline still runs without it configured.
"""

import requests

from app.config import settings


def notify(message: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(f"[notify - telegram not configured] {message}")
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": settings.telegram_chat_id, "text": message}, timeout=10)
    except requests.RequestException as e:
        print(f"[notify - failed to send telegram message] {e}")
