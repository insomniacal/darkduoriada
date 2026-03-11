from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import yt_dlp
import os
import asyncio
import re
import hashlib
from concurrent.futures import ThreadPoolExecutor
from shazamio import Shazam

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

executor = ThreadPoolExecutor(max_workers=8)
cache: dict = {}
CACHE_MAX = 20

URL_PATTERN = re.compile(
    r'https?://(www\.|vm\.)?(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com'
    r'|pin\.it|soundcloud\.com|open\.spotify\.com|vt\.tiktok\.com)',
    re.IGNORECASE
)

# ── Вспомогательные функции ───────────────────────────────────────────────────

def is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))

def is_pinterest(text: str) -> bool:
    return 'pinterest.com' in text or 'pin.it' in text

def is_tiktok(text: str) -> bool:
    return 'tiktok.com' in text or 'vt.tiktok.com' in text

def cache_key(query: str) -> str:
    return hashlib.md5(query.lower().strip().encode()).hexdigest()

def get_cookie_opts() -> dict:
    if os.path.exists('cookies.txt'):
        return {'cookiefile': 'cookies.txt'}
    return {}

def get_source_label(src: str, raw: str) -> str:
    return {
        'youtube': '▶️ YouTube',
        'soundcloud': '🔊 SoundCloud',
        'tiktok': '🎵 TikTok',
        'pinterest': '📌 Pinterest',
    }.get(src, f"🌐 {raw}")

def save_to_cache(ck: str, result: dict):
    global cache
    if len(cache) >= CACHE_MAX:
        oldest = next(iter(cache))
        old_file = cache[oldest].get('file', '')
        if os.path.exists(old_file):
            os.remove(old_file)
        del cache[oldest]
    cache[ck] = result

# ── Настройки yt-dlp ──────────────────────────────────────────────────────────

BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'socket_timeout': 30,
    'retries': 5,
    'fragment_retries': 5,
    'http_chunk_size': 10485760,
    'extractor_retries': 3,
    'playlistend': 1,
    'noplaylist': True,
    'concurrent_fragment_downloads': 4,
    'http_headers': {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    },
}

# ── Загрузка и поиск ──────────────────────────────────────────────────────────

def extract_spotify_query(url: str) -> str | None:
    try:
        opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            artist = info.get('artist') or info.get('uploader', '')
            return f"{artist} {title}".strip() if title else None
    except Exception:
        return None

def get_track_info(url: str) -> dict | None:
    """Извлекает метаданные трека из TikTok / Pinterest без скачивания."""
    try:
        opts = {**BASE_OPTS, 'skip_download': True}  # ИСПРАВЛЕНО: было {BASE_OPTS, ...}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entry = info['entries'][0] if 'entries' in info else info
            music_title = (
                entry.get('track')
                or entry.get('music_title')
                or entry.get('music')
                or ''
            )
            music_artist = (
                entry.get('artist')
                or entry.get('music_author')
                or entry.get('creator')
                or entry.get('uploader', '')
            )
            video_title = entry.get('title', '')
            if music_title:
                return {
                    'track_title': music_title,'track_artist': music_artist,
                    'track_query': f"{music_artist} {music_title}".strip(),
                    'video_title': video_title,
                }
            elif video_title:
                return {
                    'track_title': video_title,
                    'track_artist': music_artist,
                    'track_query': f"{music_artist} {video_title}".strip(),
                    'video_title': video_title,
                }
    except Exception:
        pass
    return None

def download_audio(query_or_url: str) -> dict | None:
    pid = os.getpid()
    opts = {
        **BASE_OPTS,           # ИСПРАВЛЕНО: было {BASE_OPTS, get_cookie_opts(), ...}
        **get_cookie_opts(),
        'format': 'bestaudio[filesize<50M]/bestaudio/best',
        'outtmpl': f'song_{pid}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    if 'spotify.com' in query_or_url:
        sq = extract_spotify_query(query_or_url)
        sources = [f"ytsearch:{sq}", f"scsearch:{sq}"] if sq else []
    elif is_url(query_or_url):
        sources = [query_or_url]
    else:
        sources = [f"scsearch:{query_or_url}", f"ytsearch:{query_or_url}"]

    for source in sources:
        for attempt in range(2):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
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
                err = str(e).lower()
                if ('timed out' in err or 'timeout' in err) and attempt == 0:
                    continue
                break
    return None

def download_video(url: str) -> dict | None:
    pid = os.getpid()
    opts = {
        **BASE_OPTS,           # ИСПРАВЛЕНО: было {BASE_OPTS, get_cookie_opts(), ...}
        **get_cookie_opts(),
        'format': 'bestvideo[height<=720][filesize<100M]+bestaudio/best[height<=720]/best',
        'outtmpl': f'video_{pid}.%(ext)s',
        'merge_output_format': 'mp4',
    }
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                entry = info['entries'][0] if 'entries' in info else info
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
            err = str(e).lower()
            if ('timed out' in err or 'timeout' in err) and attempt == 0:
                continue
            break
    return None

def extract_audio_from_video(video_path: str) -> str | None:
    """Извлекает аудио из видеофайла для распознавания через Shazam."""
    audio_path = video_path + '_shazam.mp3'
    try:
        ret = os.system(
            f'ffmpeg -y -i "{video_path}" -t 30 -vn -ar 44100 -ac 2 -b:a 128k "{audio_path}" -loglevel quiet'
        )
        if ret == 0 and os.path.exists(audio_path):
            return audio_path
    except Exception:
        pass
    return
Noneasync
def recognize_track(file_path: str) -> dict | None:
    """Распознаёт трек через Shazam."""
    try:
        shazam = Shazam()
        result = shazam.recognize(file_path)
        matches = result.get('matches', [])
        if not matches:
            return None
        track = result.get('track', {})
        title = track.get('title', '')
        artist = track.get('subtitle', '')
        if title:
            return {
                'title': title,
                'artist': artist,
                'query': f"{artist} {title}".strip(),
                'cover': track.get('images', {}).get('coverarthq', ''),
            }
    except Exception:
        pass
    return None

# ── Кэш ──────────────────────────────────────────────────────────────────────

async def send_cached(update: Update, cached: dict) -> bool:
    cached_file = cached.get('file', '')
    if not os.path.exists(cached_file):
        return False
    try:
        msg = await update.message.reply_text("⚡️ Из кэша, отправляю...")
        if cached['type'] == 'audio':
            with open(cached_file, 'rb') as f:
                await update.message.reply_audio(f, title=cached['title'], performer=cached['uploader'])
        else:
            with open(cached_file, 'rb') as f:
                await update.message.reply_video(f, caption=f"🎬 <b>{cached['title']}</b>", parse_mode="HTML")
        await msg.delete()
        return True
    except Exception:
        return False

# ── Обработчики сообщений ─────────────────────────────────────────────────────

async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь прислал видеофайл — распознаём трек через Shazam."""
    video = update.message.video or update.message.document
    if not video:
        return

    # Проверяем размер — Telegram позволяет скачивать до 20MB через Bot API
    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "⚠️ Файл слишком большой (максимум 20MB).\n"
            "Попробуй обрезать видео до нужного момента и прислать снова."
        )
        return

    msg = await update.message.reply_text("🎵 Скачиваю видео для распознавания...")

    video_path = f"recognize_{update.message.message_id}.mp4"
    audio_path = None

    try:
        # Скачиваем файл
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(video_path)

        await msg.edit_text("🔍 Распознаю трек через Shazam...")

        # Извлекаем аудио (первые 30 секунд)
        loop = asyncio.get_event_loop()
        audio_path = await loop.run_in_executor(executor, extract_audio_from_video, video_path)

        if not audio_path:
            await msg.edit_text("❌ Не удалось извлечь аудио из видео. Убедись что ffmpeg установлен.")
            return

        # Распознаём
        track = await asyncio.wait_for(recognize_track(audio_path), timeout=30)

        if not track:
            await msg.edit_text(
                "😔 Не удалось распознать трек.\n"
                "Попробуй видео с более чёткой музыкой."
            )
            return

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🎵 Скачать этот трек (mp3)",
                callback_data=f"audio|{track['query']}"
            )
        ]])

        await msg.edit_text(
            f"✅ Распознано через Shazam:\n\n"
            f"🎵 <b>{track['artist']} — {track['title']}</b>\n\n"
            "Нажми кнопку чтобы скачать:",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    except asyncio.TimeoutError:
        await msg.edit_text("⏳ Shazam не ответил вовремя. Попробуй ещё раз.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        for path in [video_path, audio_path]:
            if path and os.path.exists(path):
                os.remove(path)
                async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            text = update.message.text.strip()
    url_match = is_url(text)
    starts_with_find = text.lower().startswith("найти ")

    if not url_match and not starts_with_find:
        return

    loop = asyncio.get_event_loop()

    # ── TikTok ────────────────────────────────────────────────────────────────
    if url_match and is_tiktok(text):
        msg = await update.message.reply_text("🎵 Получаю информацию о видео...")
        track_info = await asyncio.wait_for(
            loop.run_in_executor(executor, get_track_info, text),
            timeout=30
        )
        if track_info and track_info.get('track_title'):
            artist = track_info['track_artist']
            title = track_info['track_title']
            query = track_info['track_query']
            track_line = f"\n🎵 Трек: <b>{artist} — {title}</b>"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎵 Аудио (mp3)", callback_data=f"audio|{query}"),
                InlineKeyboardButton("🎬 Видео (mp4)", callback_data=f"video|{text}"),
            ]])
        else:
            track_line = ""
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎵 Аудио (mp3)", callback_data=f"audio_url|{text}"),
                InlineKeyboardButton("🎬 Видео (mp4)", callback_data=f"video|{text}"),
            ]])
        await msg.edit_text(
            f"📱 <b>TikTok видео</b>{track_line}\n\nЧто скачать?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return

    # ── Pinterest ─────────────────────────────────────────────────────────────
    if url_match and is_pinterest(text):
        msg = await update.message.reply_text("📌 Получаю информацию о видео...")
        track_info = await asyncio.wait_for(
            loop.run_in_executor(executor, get_track_info, text),
            timeout=30
        )
        buttons = []
        track_line = ""
        if track_info and track_info.get('track_title'):
            artist = track_info['track_artist']
            title = track_info['track_title']
            query = track_info['track_query']
            track_line = f"\n🎵 Трек: <b>{artist} — {title}</b>"
            buttons.append(InlineKeyboardButton("🎵 Скачать трек (mp3)", callback_data=f"audio|{query}"))
        buttons.append(InlineKeyboardButton("🎬 Скачать видео (mp4)", callback_data=f"video|{text}"))
        await msg.edit_text(
            f"📌 <b>Pinterest видео</b>{track_line}\n\nЧто скачать?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([buttons])
        )
        return

    # ── Обычная ссылка или "найти ..." ────────────────────────────────────────
    query = text if url_match else text[6:].strip()
    display = "по ссылке" if url_match else f"<b>{query}</b>"

    ck = cache_key(query)
    if ck in cache:
        if await send_cached(update, cache[ck]):
            return
        del cache[ck]

    msg = await update.message.reply_text(f"🔍 Ищу {display}...", parse_mode="HTML")
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, download_audio, query),
            timeout=90
        )
        if result is None or not os.path.exists(result.get('file', '')):
            await msg.edit_text("😔 Не удалось найти. Попробуй уточнить запрос.")
            return
        duration = int(result['duration'])
        src = result['source'].lower().split(':')[0]
        lbl = get_source_label(src, result['source'])
        await msg.edit_text(
            f"✅ Нашёл: <b>{result['title']}</b>\n"
            f"👤 {result['uploader']}  •  {lbl}\n"
            f"⏱️ {duration // 60}:{duration % 60:02d}\n\n"
            "📤 Отправляю...",parse_mode="HTML"
        )
        with open(result['file'], 'rb') as f:
            await update.message.reply_audio(f, title=result['title'], performer=result['uploader'])
        save_to_cache(ck, result)
        await msg.delete()
    except asyncio.TimeoutError:
        await msg.edit_text("⏳ Сервер не ответил вовремя. Попробуй ещё раз.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    loop = asyncio.get_event_loop()

    if '|' not in data:
        return

    action, value = data.split('|', 1)
    await query.edit_message_text(
        f"{'🎵' if 'audio' in action else '🎬'} Скачиваю..."
    )
    try:
        if action == 'video':
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, download_video, value),
                timeout=120
            )
        else:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, download_audio, value),
                timeout=90
            )
        if result is None or not os.path.exists(result.get('file', '')):
            await query.edit_message_text("😔 Не удалось скачать. Попробуй ещё раз.")
            return
        duration = int(result['duration'])
        src = result['source'].lower().split(':')[0]
        lbl = get_source_label(src, result['source'])
        await query.edit_message_text(
            f"✅ <b>{result['title']}</b>\n"
            f"👤 {result['uploader']}  •  {lbl}\n"
            f"⏱️ {duration // 60}:{duration % 60:02d}\n\n"
            "📤 Отправляю...",
            parse_mode="HTML"
        )
        with open(result['file'], 'rb') as f:
            if result['type'] == 'audio':
                await query.message.reply_audio(f, title=result['title'], performer=result['uploader'])
            else:
                await query.message.reply_video(f, caption=f"🎬 <b>{result['title']}</b>", parse_mode="HTML")
        save_to_cache(cache_key(value), result)
        await query.delete_message()
    except asyncio.TimeoutError:
        await query.edit_message_text("⏳ Сервер не ответил вовремя. Попробуй ещё раз.")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я музыкальный бот.\n\n"
        "🔍 <b>Поиск аудио по названию:</b>\n"
        "  найти Imagine Dragons Believer\n\n"
        "🔗 <b>Ссылки — просто пришли:</b>\n"
        "  🎵 TikTok — покажу трек + кнопки аудио/видео\n"
        "  📌 Pinterest — покажу трек + кнопки\n"
        "  ▶️ YouTube  •  🔊 SoundCloud  •  🎧 Spotify\n\n"
        "🎬 <b>Распознать трек из видео:</b>\n"
        "  Пришли видеофайл (до 20MB) — распознаю через Shazam\n\n"
        "⚡️ Повторные запросы — мгновенно (кэш)",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 Чтобы найти песню, напиши:\n"
        "  • <b>найти</b> название песни\n"
        "  • Или просто пришли ссылку:\n"
        "    YouTube, TikTok, SoundCloud, Spotify\n\n"
        "🎬 TikTok / Pinterest ссылка:\n"
        "  Бот покажет название трека и кнопки:\n"
        "  [🎵 Скачать аудио]  [🎬 Скачать видео]\n\n"
        "🔎 <b>Распознать трек из видео:</b>\n"
        "  Пришли видеофайл (mp4, mov и др.) до 20MB\n"
        "  Бот распознает трек через Shazam и предложит скачать",
        parse_mode="HTML"
    )


# ── Запуск ────────────────────────────────────────────────────────────────────

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(handle_callback))

# Текстовые сообщения
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))# Видеофайлы — для распознавания через Shazam
app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video_file))

print("Бот запущен... ✅")
if not os.path.exists('cookies.txt'):
    print("⚠️  cookies.txt не найден — YouTube может блокировать запросы.")

app.run_polling()