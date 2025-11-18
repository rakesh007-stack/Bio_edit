#app.py
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Header, HTTPException
import httpx
import urllib.parse

TELEGRAM_BOT_TOKEN = os.environ.get("7950458032:AAG8WUk44Ol-uCana62IWf_UuxztIHkzZ9Y")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
LONG_BIO_API = "https://danger-long-bio.vercel.app/update_bio?bio={bio}&uid={guest_uid}&password={guest_password}"

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN env var")

TELEGRAM_API_BASE = f"7950458032:AAG8WUk44Ol-uCana62IWf_UuxztIHkzZ9Y"

app = FastAPI()


async def tg_send(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/{method}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, timeout=30.0)
        try:
            return r.json()
        except Exception:
            return {"ok": False, "status_code": r.status_code, "text": r.text}


def main_menu_keyboard() -> Dict[str, Any]:
    keyboard = [
        ["Set Bio ✏️"],
        ["Help ❓", "Cancel ❌"]
    ]
    return {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": False}


@app.post("/api/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    # Verify webhook secret (if set)
    if WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True, "info": "no message"}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    reply_to = message.get("reply_to_message")

    async def reply(text_to_send: str, reply_markup: Optional[Dict] = None, force_reply: bool = False):
        payload = {"chat_id": chat_id, "text": text_to_send}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if force_reply:
            # force_reply markup for next user reply
            payload["reply_markup"] = {"force_reply": True}
        return await tg_send("sendMessage", payload)

    lc = text.lower()

    # START / MENU
    if lc in ("/start", "start"):
        welcome = "Welcome! Use the menu below."
        await reply(welcome, reply_markup=main_menu_keyboard())
        return {"ok": True}

    # Menu buttons
    if lc == "help ❓" or lc == "help":
        help_text = (
            "Flow:\n"
            "1) Tap 'Set Bio' → provide access token (reply to the prompt).\n"
            "2) Then reply to the bot's bio prompt with your new bio.\n\n"
            "Note: Token is not stored; you'll paste it each time."
        )
        await reply(help_text, reply_markup=main_menu_keyboard())
        return {"ok": True}

    if lc == "cancel ❌" or lc == "cancel":
        await reply("Cancelled. Back to main menu.", reply_markup=main_menu_keyboard())
        return {"ok": True}

    # User chose Set Bio from menu
    if lc == "set bio ✏️" or lc == "set bio":
        # Ask for token (force reply)
        await reply("Please send your access token (reply to this message).", force_reply=True)
        return {"ok": True}

    # ---- Handling replies ----
    # 1) User replied to our "Please send your access token" prompt -> treat as token
    if reply_to:
        replied_text = (reply_to.get("text") or "").lower()

        # If user replied to the token prompt -> this message is the token
        if "please send your access token" in replied_text:
            token = text.strip()
            # Next, ask for bio, embedding the token in the bot message so that the user's bio reply can be matched to the token.
            # (We include token text in the message so the webhook can later parse it when user replies to this prompt.)
            bio_prompt = (
                "Welcome to the ArC Bio Updater || drop your new bio here\n\n"
                f"Using token: {token}\n\n"
                "Reply to this message with your new bio."
            )
            await reply(bio_prompt, force_reply=True)
            return {"ok": True}

        # 2) User replied to the bio prompt. We expect the replied-to bot text to contain "Using token: {token}"
        if "welcome to the arc bio updater || drop your new bio here" in replied_text or "using token:" in replied_text:
            # Extract token from replied message text
            # Find the line starting with "Using token:"
            full_replied_text = reply_to.get("text") or ""
            token_line = None
            for line in full_replied_text.splitlines():
                if line.strip().lower().startswith("using token:"):
                    token_line = line.strip()
                    break
            if not token_line:
                await reply("❌ Could not find the token in the previous prompt. Start again with Set Bio.", reply_markup=main_menu_keyboard())
                return {"ok": True}
            # token_line format: "Using token: {token}"
            token = token_line.partition(":")[2].strip()
            bio_text = text.strip()
            if not token or not bio_text:
                await reply("❌ Missing token or bio. Start again with Set Bio.", reply_markup=main_menu_keyboard())
                return {"ok": True}

            # Call the long-bio API using provided token and bio
            async with httpx.AsyncClient() as client:
                try:
                    params = {"access_token": token, "bio": bio_text}
                    r = await client.get(LONG_BIO_API, params=params, timeout=20.0)
                    if r.status_code == 200:
                        await reply("✅ Bio updated successfully.", reply_markup=main_menu_keyboard())
                    else:
                        # attempt to show some error detail if available
                        detail = r.text or str(r.status_code)
                        await reply(f"❌ Failed to update bio (status {r.status_code}). {detail}", reply_markup=main_menu_keyboard())
                except Exception as e:
                    await reply(f"❌ Error while contacting bio API: {e}", reply_markup=main_menu_keyboard())
            return {"ok": True}

    # Fallback: unknown text — show menu
    await reply("I didn't understand that. Use the menu below.", reply_markup=main_menu_keyboard())
    return {"ok": True}