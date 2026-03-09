from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import yt_dlp
import os
import re
import asyncio
import time

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

CACHE = "music_cache"
MAX_DURATION = 900
COOLDOWN = 3

if not os.path.exists(CACHE):
    os.makedirs(CACHE)

search_results = {}
last_request = {}


def safe(text):
    return re.sub(r'[\\/*?:"<>|]', "", text)


def progress_hook(d):

    if d["status"] == "downloading":

        percent = d.get("_percent_str", "")
        speed = d.get("_speed_str", "")
        eta = d.get("_eta_str", "")

        print(f"{percent} {speed} ETA {eta}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🎵 Музыкальный бот\n\n"
        "Напиши название песни."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Как пользоваться:\n"
        "1. Напиши название песни\n"
        "2. Выбери трек\n"
        "3. Получи mp3"
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    if user in last_request:
        if time.time() - last_request[user] < COOLDOWN:
            await update.message.reply_text("⏳ Подожди пару секунд")
            return

    last_request[user] = time.time()

    query = update.message.text

    msg = await update.message.reply_text("🔎 Ищу музыку...")

    try:

        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:

            info = ydl.extract_info(
                f"ytsearch10:{query}",
                download=False
            )

        videos = info["entries"]

        keyboard = []
        results = []

        for i, v in enumerate(videos):

            title = v["title"]
            url = v["webpage_url"]
            duration = v.get("duration", 0)

            mins = duration // 60
            secs = duration % 60

            label = f"{title[:35]} ({mins}:{secs:02d})"

            keyboard.append([
                InlineKeyboardButton(
                    label,
                    callback_data=f"music_{i}"
                )
            ])

            results.append((title, url, duration))

        search_results[update.message.chat_id] = results

        await msg.edit_text(
            "🎧 Выбери трек:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:

        await msg.edit_text(f"❌ Ошибка поиска\n{e}")


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    index = int(query.data.split("_")[1])

    title, url, duration = search_results[query.message.chat_id][index]

    if duration > MAX_DURATION:

        await query.message.reply_text(
            "❌ Трек слишком длинный (макс 15 минут)"
        )
        return

    filename = safe(title)

    path = f"{CACHE}/{filename}.mp3"

    if os.path.exists(path):

        await query.message.reply_audio(
            open(path, "rb"),
            title=title
        )
        return

    msg = await query.message.reply_text("⬇️ Скачиваю...")

    ydl_opts = {

        "format": "bestaudio/best",

        "outtmpl": f"{CACHE}/{filename}.%(ext)s",

        "quiet": True,

        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 60,

        "progress_hooks": [progress_hook],

        "concurrent_fragment_downloads": 3,

        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    }

    try:

        loop = asyncio.get_event_loop()

        await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).download([url])
        )

        await msg.delete()

        await query.message.reply_audio(
            open(path, "rb"),
            title=title
        )

    except Exception as e:await msg.edit_text(f"❌ Ошибка\n{e}")


async def clean_cache():

    while True:

        now = time.time()

        for file in os.listdir(CACHE):

            path = os.path.join(CACHE, file)

            if os.path.isfile(path):

                if now - os.path.getmtime(path) > 86400:

                    os.remove(path)

        await asyncio.sleep(3600)


async def on_start(app):

    asyncio.create_task(clean_cache())


app = ApplicationBuilder().token(TOKEN).post_init(on_start).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

app.add_handler(CallbackQueryHandler(download, pattern="music_"))

print("Бот запущен...")

app.run_polling()