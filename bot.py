import os
import sqlite3
import asyncio
from typing import List, Dict

import aiohttp
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

print("MODEL:", OPENROUTER_MODEL)
print("SITE_NAME:", OPENROUTER_SITE_NAME)
print("SITE_URL:", OPENROUTER_SITE_URL)
print("OPENROUTER_API_KEY present?", bool(OPENROUTER_API_KEY))
print("BOT_TOKEN present?", bool(TOKEN))

# Python 3.14 fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

if not TOKEN:
    raise RuntimeError("Missing BOT_TOKEN")
if not OPENROUTER_API_KEY:
    raise RuntimeError("Missing OPENROUTER_API_KEY")

# -------------------- DB --------------------

db = sqlite3.connect("bot.db", check_same_thread=False)
db.execute("""
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT
)
""")
db.commit()

def save_message(user_id: int, role: str, content: str):
    db.execute(
        "INSERT INTO messages(user_id, role, content) VALUES(?,?,?)",
        (user_id, role, content),
    )
    db.commit()

def get_recent_messages(user_id: int, limit: int = 50):
    rows = db.execute(
        "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]

# -------------------- TRAINING FILE --------------------

def load_training_prompt() -> str:
    try:
        with open("training.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a confident adult female influencer. Respond naturally."

# -------------------- LLM CALL --------------------

async def call_llm(messages: List[Dict[str, str]]) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.9,
        "presence_penalty": 0.4,
        "frequency_penalty": 0.2,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()

# -------------------- CHAT HANDLER --------------------

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    if user_text.startswith("/"):
        return

    save_message(user_id, "user", user_text)
    await update.message.chat.send_action(action=ChatAction.TYPING)

    training_prompt = load_training_prompt()
    history = get_recent_messages(user_id)

    messages = [{"role": "system", "content": training_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        reply = await call_llm(messages)
    except Exception:
        reply = "Hmm… say that again, handsome 😌"

    save_message(user_id, "assistant", reply)
    await update.message.reply_text(reply)

# -------------------- START --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hey… you came back for me? 😌")

# -------------------- MAIN --------------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()