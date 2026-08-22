"""Sends run status notifications via Telegram (free, simple, works from any
server without exposing ports). Optional -- if TELEGRAM_BOT_TOKEN is unset,
notify() no-ops silently so the pipeline still runs without it configured.

notify() itself still never raises (a notification failure should never
crash the pipeline) -- but it now returns a result dict so callers like the
/test-telegram endpoint can report the REAL outcome instead of always
claiming success.
"""

import requests

from app.config import settings


def notify(message: str) -> dict:
    """Returns {"sent": bool, "reason": str} -- reason explains what happened
    whether it succeeded or not, so callers can surface real diagnostics."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(f"[notify - telegram not configured] {message}")
        return {"sent": False, "reason": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set"}

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": settings.telegram_chat_id, "text": message}, timeout=10)
        if resp.status_code == 200:
            return {"sent": True, "reason": "ok"}
        else:
            # Telegram returns useful error detail in the response body --
            # e.g. "Unauthorized" (bad token) or "chat not found" (bad chat_id)
            print(f"[notify - telegram API error] {resp.status_code}: {resp.text}")
            return {"sent": False, "reason": f"Telegram API returned {resp.status_code}: {resp.text}"}
    except requests.RequestException as e:
        print(f"[notify - failed to send telegram message] {e}")
        return {"sent": False, "reason": f"Request failed: {e}"}