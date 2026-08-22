"""Sends run status notifications via Telegram, including interactive
Approve/Reject buttons for the video review step.

Plain text notifications (notify) work with just a bot token + chat ID.
Interactive approval (send_approval_request) additionally requires a
Telegram webhook to be registered so button taps reach this app -- see
app/main.py's /telegram-webhook endpoint and the README for the one-time
setWebhook command.
"""

import requests

from app.config import settings

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _api(method: str, payload: dict) -> dict:
    """Low-level helper: calls a Telegram Bot API method, returns the
    response JSON. Never raises -- callers get {"ok": False, ...} on failure
    so a notification problem never crashes the pipeline."""
    if not settings.telegram_bot_token:
        print(f"[notifier] TELEGRAM_BOT_TOKEN not set -- skipping {method}")
        return {"ok": False, "description": "bot token not set"}

    url = TELEGRAM_API.format(token=settings.telegram_bot_token, method=method)
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            print(f"[notifier] Telegram API error on {method}: {data}")
        return data
    except requests.RequestException as e:
        print(f"[notifier] Request failed on {method}: {e}")
        return {"ok": False, "description": str(e)}


def notify(message: str) -> dict:
    """Sends a plain text message. Returns {"sent": bool, "reason": str}."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(f"[notify - telegram not configured] {message}")
        return {"sent": False, "reason": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set"}

    result = _api("sendMessage", {"chat_id": settings.telegram_chat_id, "text": message})
    if result.get("ok"):
        return {"sent": True, "reason": "ok"}
    return {"sent": False, "reason": result.get("description", "unknown error")}


def send_approval_request(
    run_id: int,
    problem_title: str,
    difficulty: str,
    video_duration_seconds: float | None,
    theme_name: str | None,
    voice_name: str | None,
) -> dict:
    """Sends a message with video metadata and inline Approve/Reject buttons.
    Returns {"sent": bool, "message_id": str|None, "chat_id": str|None} --
    the caller should save message_id/chat_id on the run row so the webhook
    handler can edit this exact message later."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(f"[notifier] Telegram not configured -- cannot send approval request for run #{run_id}")
        return {"sent": False, "message_id": None, "chat_id": None}

    duration_str = "unknown"
    if video_duration_seconds is not None:
        minutes, seconds = divmod(int(video_duration_seconds), 60)
        duration_str = f"{minutes}:{seconds:02d}"

    text = (
        f"🎬 *New video ready for review*\n\n"
        f"*Title:* {problem_title}\n"
        f"*Difficulty:* {difficulty}\n"
        f"*Duration:* {duration_str}\n"
        f"*Theme:* {theme_name or 'default'}\n"
        f"*Voice:* {voice_name or 'default'}\n"
        f"*Run ID:* #{run_id}"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{run_id}"},
            {"text": "❌ Reject", "callback_data": f"reject:{run_id}"},
        ]]
    }

    result = _api("sendMessage", {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup,
    })

    if result.get("ok"):
        message = result["result"]
        return {"sent": True, "message_id": str(message["message_id"]), "chat_id": str(message["chat"]["id"])}
    return {"sent": False, "message_id": None, "chat_id": None}


def edit_message(chat_id: str, message_id: str, text: str, remove_buttons: bool = True) -> dict:
    """Edits a previously sent message -- used to update the approval message
    with the final result (uploaded link, rejected, or error) and remove the
    buttons so they can't be tapped twice."""
    payload = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": text,
        "parse_mode": "Markdown",
    }
    if remove_buttons:
        payload["reply_markup"] = {"inline_keyboard": []}
    return _api("editMessageText", payload)


def answer_callback_query(callback_query_id: str, text: str = "") -> dict:
    """Must be called after every button tap -- this stops Telegram's client
    from showing an infinite loading spinner on the button the user pressed."""
    return _api("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})