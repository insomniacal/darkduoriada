from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import os
import asyncio
import re
<<<<<<< HEAD
import hashlib
=======
>>>>>>> 2486404 (.)
from concurrent.futures import ThreadPoolExecutor

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

# Больше потоков = быстрее параллельные запросы
executor = ThreadPoolExecutor(max_workers=8)

<<<<<<< HEAD
# Простой кэш: {хэш_запроса: путь_к_файлу + мета}
# Повторный запрос той же песни — мгновенная отдача без скачивания
cache: dict = {}
CACHE_MAX = 20  # максимум 20 записей в памяти

URL_PATTERN = re.compile(
    r'https?://(www\.)?(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com|pin\.it'
    r'|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

def is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))

def is_pinterest(text: str) -> bool:
    return 'pinterest.com' in text or 'pin.it' in text

def cache_key(query: str) -> str:
    return hashlib.md5(query.lower().strip().encode()).hexdigest()

def extract_spotify_query(url: str) -> str | None:
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            artist = info.get('artist') or info.get('uploader', '')
            return f"{artist} {title}".strip() if title else None
    except Exception:
        return None

# --- Общие быстрые настройки yt-dlp ---
BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'socket_timeout': 15,       # быстрее отказываемся от зависшего соединения
    'retries': 3,
    'fragment_retries': 3,
    'http_chunk_size': 10485760,
    'extractor_retries': 2,
    'playlistend': 1,
    'noplaylist': True,
    'concurrent_fragment_downloads': 4,  # параллельная загрузка фрагментов
}

def download_audio(query_or_url: str) -> dict | None:
    """Скачивает MP3."""
    pid = os.getpid()
    ydl_opts = {
        **BASE_OPTS,
        'format': 'bestaudio[filesize<50M]/bestaudio/best',  # лимит 50MB — быстрее
        'outtmpl': f'song_{pid}.%(ext)s',
=======
# Поддерживаемые домены для ссылок
URL_PATTERN = re.compile(
    r'https?://(www\.)?(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com|pin\.it'
    r'|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

def is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))

def extract_spotify_query(url: str) -> str | None:
    """Spotify не даёт скачивать — извлекаем название трека из URL для поиска на YouTube."""
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            artist = info.get('artist') or info.get('uploader', '')
            return f"{artist} {title}".strip() if title else None
    except Exception:
        return None

def download_song(query_or_url: str) -> dict | None:
    """Скачивает аудио синхронно — запускается в отдельном потоке."""

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'song_{os.getpid()}.%(ext)s',
        'socket_timeout': 20,
        'retries': 2,
>>>>>>> 2486404 (.)
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',  # 128 вместо 192 — в 1.5x быстрее, качество не отличить
        }],
<<<<<<< HEAD
    }

    if 'spotify.com' in query_or_url:
        spotify_query = extract_spotify_query(query_or_url)
        sources = [f"ytsearch:{spotify_query}", f"scsearch:{spotify_query}"] if spotify_query else []
    elif is_url(query_or_url):
        sources = [query_or_url]
    else:
        # Параллельный поиск: SoundCloud быстрее, YouTube — запасной
        sources = [f"scsearch:{query_or_url}", f"ytsearch:{query_or_url}"]
=======
        'playlistend': 1,
        'noplaylist': True,
    }

    # Если это Spotify — извлекаем название и ищем на YouTube
    if 'spotify.com' in query_or_url:
        spotify_query = extract_spotify_query(query_or_url)
        if spotify_query:
            sources = [f"ytsearch:{spotify_query}", f"scsearch:{spotify_query}"]
        else:
            return None

    # Pinterest — там нет аудио
    elif 'pinterest.com' in query_or_url or 'pin.it' in query_or_url:
        return {'error': 'pinterest'}

    # Прямые ссылки (YouTube, TikTok, SoundCloud)
    elif is_url(query_or_url):
        sources = [query_or_url]

    # Текстовый запрос — сначала SoundCloud (быстрее), потом YouTube
    else:
        sources = [
            f"scsearch:{query_or_url}",
            f"ytsearch:{query_or_url}",
        ]
>>>>>>> 2486404 (.)

    for source in sources:
        for attempt in range(2):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(source, download=True)
                    entry = info['entries'][0] if 'entries' in info else info
                    return {
                        'type': 'audio',
                        'title': entry.get('title', query_or_url),
                        'duration': entry.get('duration', 0) or 0,
                        'uploader': entry.get('uploader', ''),
                        'source': entry.get('extractor', ''),
                        'file': f'song_{pid}.mp3',
                    }
            except Exception as e:
                if 'timed out' in str(e).lower() and attempt == 0:
                    continue
                break

    return None

def download_video(url: str) -> dict | None:
    """Скачивает MP4 (Pinterest и другие видео-ссылки)."""
    pid = os.getpid()
    ydl_opts = {
        **BASE_OPTS,
        # Берём видео до 720p и не больше 100MB — быстро и не огромное
        'format': 'bestvideo[height<=720][filesize<100M]+bestaudio/best[height<=720]/best',
        'outtmpl': f'video_{pid}.%(ext)s',
        'merge_output_format': 'mp4',
    }
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                entry = info['entries'][0] if 'entries' in info else info
<<<<<<< HEAD
                # ищем скачанный файл
                for ext in ['mp4', 'mkv', 'webm', 'mov']:
                    path = f'video_{pid}.{ext}'
                    if os.path.exists(path):
                        return {
                            'type': 'video',
                            'title': entry.get('title', 'video'),
                            'duration': entry.get('duration', 0) or 0,
                            'uploader': entry.get('uploader', ''),
                            'source': entry.get('extractor', ''),
                            'file': path,
                        }
        except Exception as e:
            if 'timed out' in str(e).lower() and attempt == 0:
                continue
            break
=======
                return {
                    'title': entry.get('title', query_or_url),
                    'duration': entry.get('duration', 0) or 0,
                    'uploader': entry.get('uploader', ''),
                    'source': entry.get('extractor', ''),
                }
        except Exception:
            continue
>>>>>>> 2486404 (.)

    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    url_match = is_url(text)
    starts_with_find = text.lower().startswith("найти ")

    if not url_match and not starts_with_find:
<<<<<<< HEAD
        return

    # Определяем тип запроса
    is_video_url = url_match and is_pinterest(text)

    if url_match:
        query = text
        display = "видео с Pinterest" if is_video_url else "по ссылке"
    else:
        query = text[6:].strip()
        display = f"<b>{query}</b>"

    # --- Проверяем кэш ---
    ck = cache_key(query)
    if ck in cache:
        cached = cache[ck]
        cached_file = cached.get('file', '')
        if os.path.exists(cached_file):
            msg = await update.message.reply_text("⚡️ Из кэша, отправляю...", parse_mode="HTML")
            try:
                if cached['type'] == 'audio':
                    with open(cached_file, 'rb') as f:
                        await update.message.reply_audio(f, title=cached['title'], performer=cached['uploader'])
                else:
                    with open(cached_file, 'rb') as f:
                        await update.message.reply_video(f, caption=f"🎬 <b>{cached['title']}</b>", parse_mode="HTML")
                await msg.delete()
            except Exception:
                await msg.edit_text("😔 Кэш устарел, ищу заново...")
                del cache[ck]
            else:
                return

    msg = await update.message.reply_text(
        f"{'🎬' if is_video_url else '🔍'} Ищу {display}...",
        parse_mode="HTML"
    )

    loop = asyncio.get_event_loop()

    try:
        if is_video_url:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, download_video, query),
                timeout=120
            )
        else:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, download_audio, query),
                timeout=90
            )

        if result is None or not os.path.exists(result.get('file', '')):
            await msg.edit_text(
                "😔 Не удалось скачать.\n"
                "Попробуй уточнить запрос или повтори через несколько секунд."
            )
=======
        await update.message.reply_text(
            "💡 Чтобы найти песню, напиши:\n"
            "  • <b>найти</b> название песни\n"
            "  • Или просто пришли ссылку:\n"
            "    YouTube, TikTok, SoundCloud, Spotify\n\n"
            "<i>Пример: найти Imagine Dragons Believer</i>",
            parse_mode="HTML"
        )
        return

    if url_match:
        query = text
        display = "по ссылке"
    else:
        query = text[6:].strip()  # убираем "найти "
        display = f"<b>{query}</b>"

    msg = await update.message.reply_text(f"🔍 Ищу {display}...", parse_mode="HTML")

    loop = asyncio.get_event_loop()
    mp3_path = f"song_{os.getpid()}.mp3"
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, download_song, query),
            timeout=60
        )

        if result and result.get('error') == 'pinterest':
            await msg.edit_text(
                "📌 Pinterest не содержит аудио.\n"
                "Напиши название песни: <b>найти [название]</b>",
                parse_mode="HTML"
            )
            return

        if result is None or not os.path.exists(mp3_path):
            await msg.edit_text("😔 Не удалось найти песню. Попробуй уточнить запрос.")
>>>>>>> 2486404 (.)
            return

        duration = int(result['duration'])
        src = result['source'].lower().split(':')[0]
        source_label = {
            'youtube': '▶️ YouTube',
            'soundcloud': '🔊 SoundCloud',
            'tiktok': '🎵 TikTok',
<<<<<<< HEAD
            'pinterest': '📌 Pinterest',
        }.get(src, f"🌐 {result['source']}")
=======
        }.get(src, f"🌐 {result['source']}")

        await msg.edit_text(
            f"✅ Нашёл: <b>{result['title']}</b>\n"
            f"👤 {result['uploader']}  •  {source_label}\n"
            f"⏱️ {duration // 60}:{duration % 60:02d}\n\n"
            "📤 Отправляю...",
            parse_mode="HTML"
        )
>>>>>>> 2486404 (.)

        await msg.edit_text(
            f"✅ Нашёл: <b>{result['title']}</b>\n"
            f"👤 {result['uploader']}  •  {source_label}\n"
            f"⏱ {duration // 60}:{duration % 60:02d}\n\n"
            "📤 Отправляю...",
            parse_mode="HTML"
        )
        with open(result['file'], 'rb') as f:
            if result['type'] == 'audio':
                await update.message.reply_audio(f, title=result['title'], performer=result['uploader'])
            else:
                await update.message.reply_video(f, caption=f"🎬 <b>{result['title']}</b>", parse_mode="HTML")

        # Сохраняем в кэш
        if len(cache) >= CACHE_MAX:
            oldest = next(iter(cache))
            old_file = cache[oldest].get('file', '')
            if os.path.exists(old_file):
                os.remove(old_file)
            del cache[oldest]
        cache[ck] = result

        await msg.delete()

    except asyncio.TimeoutError:
        await msg.edit_text("⏳ Сервер не ответил вовремя.\nПопробуй ещё раз через несколько секунд.")
    except Exception as e:
        await msg.edit_text(f"❌ ОшиББка: {e}")
        pid = os.getpid()
        for f in [f'song_{pid}.mp3', f'video_{pid}.mp4']:
            if os.path.exists(f):
                os.remove(f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я музыкальный бот.\n\n"
        "🔍 <b>Поиск аудио по названию:</b>\n"
        "  найти Imagine Dragons Believer\n\n"
        "🔗 <b>Поиск по ссылке (аудио):</b>\n"
        "  ▶️ YouTube  •  🎵 TikTok\n"
        "  🔊 SoundCloud  •  🎧 Spotify\n\n"
        "📌 <b>Скачать видео с Pinterest:</b>\n"
        "  Просто пришли ссылку pinterest.com или pin.it\n\n"
        "⚡️ Повторные запросы — мгновенно (кэш)",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 Чтобы найти песню, напиши:\n"
        "  • <b>найти</b> название песни\n"
        "  • Или просто пришли ссылку:\n"
        "    YouTube, TikTok, SoundCloud, Spotify\n\n"
        "🎬 Чтобы скачать видео с Pinterest:\n"
        "  • Просто пришли ссылку pinterest.com",
        parse_mode="HTML"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я музыкальный бот.\n\n"
        "🔍 <b>Поиск по названию:</b>\n"
        "  найти Imagine Dragons Believer\n\n"
        "🔗 <b>Поиск по ссылке:</b>\n"
        "  Просто пришли ссылку из:\n"
        "  ▶️ YouTube  •  🎵 TikTok\n"
        "  🔊 SoundCloud  •  🎧 Spotify\n\n"
        "📌 Pinterest — только картинки, аудио не поддерживается.",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Напиши <b>найти</b> + название:\n"
        "   <i>найти Coldplay Yellow</i>\n\n"
        "2️⃣ Или пришли ссылку:\n"
        "   • youtube.com/watch?v=...\n"
        "   • tiktok.com/@.../video/...\n"
        "   • soundcloud.com/...\n"
        "   • open.spotify.com/track/...\n\n"
        "⚡️ Поиск занимает 5–20 секунд.",
        parse_mode="HTML"
    )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен... ✅")
app.run_polling()