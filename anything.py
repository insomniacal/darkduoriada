import os
import re
import asyncio
import hashlib
import logging
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from shazamio import Shazam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ── Настройки ─────────────────────────────────────────────────────────────────

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=8)
cache: dict = {}
CACHE_MAX = 30

# Хранилище длинных URL (чтобы не превышать 64 байта в callback_data)
_url_store: dict = {}

URL_PATTERN = re.compile(
    r'https?://(www\.|vm\.|vt\.)?'
    r'(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com'
    r'|pin\.it|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

# ── Утилиты ───────────────────────────────────────────────────────────────────

def is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))

def is_pinterest(text: str) -> bool:
    return 'pinterest.com' in text or 'pin.it' in text

def is_tiktok(text: str) -> bool:
    return 'tiktok.com' in text

def is_spotify(text: str) -> bool:
    return 'spotify.com' in text

def cache_key(q: str) -> str:
    return hashlib.md5(q.lower().strip().encode()).hexdigest()

def store_url(value: str) -> str:
    """Сохраняет длинное значение и возвращает короткий ключ для callback_data."""
    key = hashlib.md5(value.encode()).hexdigest()[:16]
    _url_store[key] = value
    return key

def get_stored(key: str) -> str:
    """Возвращает оригинальное значение по ключу."""
    return _url_store.get(key, key)

def get_cookie_opts() -> dict:
    return {'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt') else {}

def fmt_duration(secs) -> str:
    secs = int(secs or 0)
    return f"{secs // 60}:{secs % 60:02d}"

def source_emoji(src: str) -> str:
    src = src.lower()
    if 'youtube' in src: return '▶️ YouTube'
    if 'soundcloud' in src: return '🔊 SoundCloud'
    if 'tiktok' in src: return '🎵 TikTok'
    if 'pinterest' in src: return '📌 Pinterest'
    if 'spotify' in src: return '🎧 Spotify'
    return '🌐 Web'

def clean_query(text: str) -> str:
    """
    Превращает декоративные юникод-буквы (𝓵→l, 𝔂→y и т.д.) в обычные ASCII,
    при этом сохраняет кириллицу, арабский, китайский и другие обычные символы.
    Если после очистки строка пустая — возвращает оригинал.
    """
    result = []
    for ch in text:
        cp = ord(ch)
        # Математические/декоративные буквы Unicode (U+1D400–U+1D7FF)
        if 0x1D400 <= cp <= 0x1D7FF:
            normalized = unicodedata.normalize('NFKD', ch)
            ascii_ch = normalized.encode('ascii', 'ignore').decode('ascii')
            result.append(ascii_ch if ascii_ch else '')
        else:
            result.append(ch)
    cleaned = ' '.join(''.join(result).split()).strip()
    return cleaned if cleaned else text  # фолбэк на оригинал если всё исчезло

def resolve_url(url: str) -> str:
    """Раскрывает короткие ссылки (vt.tiktok.com и др.) через редирект."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.url
    except Exception:
        return url

def save_cache(ck: str, result: dict):
    global cache
    if len(cache) >= CACHE_MAX:
        oldest = next(iter(cache))
        old = cache.pop(oldest)
        f = old.get('file', '')
        if f and os.path.exists(f):
            try: os.remove(f)
            except: pass
    cache[ck] = result

# ── Безопасная отправка (обход FloodControl и мёртвых сообщений) ──────────────

async def safe_edit(msg, text: str, **kwargs):
    for attempt in range(3):
        try:
            await msg.edit_text(text, **kwargs)
            return
        except RetryAfter as e:
            log.warning(f"FloodControl edit, жду {e.retry_after}s")
            await asyncio.sleep(e.retry_after + 1)
        except (BadRequest, TimedOut, NetworkError) as e:
            log.warning(f"safe_edit: {e}")
            return
    log.error("safe_edit: не удалось после 3 попыток")

async def safe_reply(update: Update, text: str, **kwargs):
    for attempt in range(3):
        try:
            return await update.message.reply_text(text, **kwargs)
        except RetryAfter as e:
            log.warning(f"FloodControl reply, жду {e.retry_after}s")
            await asyncio.sleep(e.retry_after + 1)
        except (BadRequest, TimedOut, NetworkError) as e:
            log.warning(f"safe_reply: {e}")
            return None
    return None

# ── yt-dlp базовые настройки ──────────────────────────────────────────────────

BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'socket_timeout': 30,
    'retries': 5,
    'fragment_retries': 5,
    'http_chunk_size': 10 * 1024 * 1024,
    'extractor_retries': 3,
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

# ── Скачивание ────────────────────────────────────────────────────────────────

def _get_spotify_query(url: str) -> str | None:
    try:
        opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            artist = info.get('artist') or info.get('uploader', '')
            return f"{artist} {title}".strip() or None
    except Exception:
        return None

def _get_track_meta(url: str) -> dict | None:
    """Метаданные трека из TikTok/Pinterest без скачивания."""
    try:
        opts = {**BASE_OPTS, **get_cookie_opts(), 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            e = info['entries'][0] if 'entries' in info else info
            track = e.get('track') or e.get('music_title') or e.get('music') or ''
            artist = (e.get('artist') or e.get('music_author')
                      or e.get('creator') or e.get('uploader', ''))
            vtitle = e.get('title', '')
            name = track or vtitle
            if name:
                clean_name = clean_query(name)
                clean_artist = clean_query(artist)
                return {
                    'title': clean_name,
                    'artist': clean_artist,
                    'query': f"{clean_artist} {clean_name}".strip(),
                    'video_title': vtitle,
                }
    except Exception as ex:
        log.warning(f"_get_track_meta: {ex}")
    return None

def _shazam_identify_tiktok(tiktok_url: str) -> str | None:
    """
    Скачивает первые 30 секунд аудио с TikTok и распознаёт трек через Shazam.
    Возвращает строку 'Artist - Title' для дальнейшего поиска, или None.
    """
    import asyncio as _asyncio
    pid = os.getpid()
    tmp_audio = f'shazam_tt_{pid}.mp3'
    opts = {
        **BASE_OPTS,
        **get_cookie_opts(),
        'format': 'bestaudio/best',
        'outtmpl': f'shazam_tt_{pid}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'postprocessor_args': ['-t', '30'],  # только первые 30 секунд
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(tiktok_url, download=True)

        if not os.path.exists(tmp_audio):
            return None

        # Запускаем Shazam в новом event loop (мы в потоке executor)
        loop = _asyncio.new_event_loop()
        try:
            shazam = Shazam()
            result = loop.run_until_complete(shazam.recognize(tmp_audio))
        finally:
            loop.close()

        matches = result.get('matches', [])
        if not matches:
            return None
        track = result.get('track', {})
        title = track.get('title', '')
        artist = track.get('subtitle', '')
        if title:
            return f"{artist} {title}".strip()
    except Exception as ex:
        log.warning(f"_shazam_identify_tiktok: {ex}")
    finally:
        if os.path.exists(tmp_audio):
            try: os.remove(tmp_audio)
            except: pass
    return None

def _download_audio(query_or_url: str) -> dict | None:
    pid = os.getpid()
    out = f'audio_{pid}'
    opts = {
        **BASE_OPTS,
        **get_cookie_opts(),
        'format': 'bestaudio[filesize<50M]/bestaudio/best',
        'outtmpl': f'{out}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    if is_spotify(query_or_url):
        sq = _get_spotify_query(query_or_url)
        sources = [f"ytsearch:{sq}", f"scsearch:{sq}"] if sq else []
    elif is_url(query_or_url):
        sources = [query_or_url]
    else:
        q = clean_query(query_or_url)
        sources = [f"scsearch:{q}", f"ytsearch:{q}"]

    for source in sources:
        for attempt in range(2):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(source, download=True)
                    e = info['entries'][0] if 'entries' in info else info
                    file = f'{out}.mp3'
                    if os.path.exists(file):
                        return {
                            'type': 'audio',
                            'title': e.get('title', query_or_url),
                            'duration': e.get('duration', 0) or 0,
                            'uploader': e.get('uploader', ''),
                            'source': e.get('extractor', ''),
                            'file': file,
                        }
            except Exception as ex:
                err = str(ex).lower()
                if ('timed out' in err or 'timeout' in err) and attempt == 0:
                    continue
                log.warning(f"_download_audio [{source}]: {ex}")
                break
    return None

def _download_video(url: str) -> dict | None:
    pid = os.getpid()
    out = f'video_{pid}'
    opts = {
        **BASE_OPTS,
        **get_cookie_opts(),
        'format': 'bestvideo[height<=720][filesize<90M]+bestaudio/best[height<=720]/best',
        'outtmpl': f'{out}.%(ext)s',
        'merge_output_format': 'mp4',
    }
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                e = info['entries'][0] if 'entries' in info else info
                for ext in ['mp4', 'mkv', 'webm', 'mov']:
                    path = f'{out}.{ext}'
                    if os.path.exists(path):
                        return {
                            'type': 'video',
                            'title': e.get('title', 'video'),
                            'duration': e.get('duration', 0) or 0,
                            'uploader': e.get('uploader', ''),
                            'source': e.get('extractor', ''),
                            'file': path,
                        }
        except Exception as ex:
            err = str(ex).lower()
            if ('timed out' in err or 'timeout' in err) and attempt == 0:
                continue
            log.warning(f"_download_video: {ex}")
            break
    return None

def _extract_audio_for_shazam(video_path: str) -> str | None:
    out = video_path + '_shazam.mp3'
    ret = os.system(
        f'ffmpeg -y -i "{video_path}" -t 30 -vn -ar 44100 -ac 2 -b:a 128k "{out}" -loglevel quiet'
    )
    return out if ret == 0 and os.path.exists(out) else None

async def _recognize_shazam(file_path: str) -> dict | None:
    try:
        shazam = Shazam()
        result = await shazam.recognize(file_path)
        if not result.get('matches'):
            return None
        track = result.get('track', {})
        title = track.get('title', '')
        artist = track.get('subtitle', '')
        if title:
            return {
                'title': title,
                'artist': artist,
                'query': f"{artist} {title}".strip(),
            }
    except Exception as ex:
        log.warning(f"Shazam: {ex}")
    return None

# ── Кэш: отправка ─────────────────────────────────────────────────────────────

async def _send_cached(update: Update, cached: dict) -> bool:
    f = cached.get('file', '')
    if not os.path.exists(f):
        return False
    try:
        msg = await safe_reply(update, "⚡️ <b>Мгновенно из кэша!</b>", parse_mode="HTML")
        with open(f, 'rb') as fp:
            if cached['type'] == 'audio':
                await update.message.reply_audio(fp, title=cached['title'], performer=cached['uploader'])
            else:
                await update.message.reply_video(fp, caption=f"🎬 <b>{cached['title']}</b>", parse_mode="HTML")
        if msg:
            try: await msg.delete()
            except: pass
        return True
    except Exception:
        return False

# ── Хендлеры ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"🎵 <b>Добро пожаловать, {name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Я помогу скачать музыку и видео\n"
        f"с любой платформы — быстро и качественно.\n\n"
        f"<b>Что умею:</b>\n\n"
        f"🔗 <b>Ссылка</b> — просто отправь:\n"
        f"    TikTok · Pinterest · YouTube\n"
        f"    SoundCloud · Spotify\n\n"
        f"🔍 <b>Поиск</b> — напиши название:\n"
        f"    <code>найти The Weeknd Blinding Lights</code>\n\n"
        f"🎬 <b>Распознать трек</b> — пришли видео до 20MB\n"
        f"    Определю песню через Shazam\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ Повторные запросы отдаю мгновенно",
        parse_mode="HTML"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Инструкция</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔗 <b>TikTok / Pinterest</b>\n"
        "    Отправь ссылку → выбери Аудио или Видео\n"
        "    Трек определяется автоматически\n\n"
        "▶️ <b>YouTube / SoundCloud / Spotify</b>\n"
        "    Отправь ссылку → получи mp3\n\n"
        "🔍 <b>Поиск по названию</b>\n"
        "    <code>найти [исполнитель — трек]</code>\n\n"
        "🎬 <b>Распознать из видео</b>\n"
        "    Пришли видеофайл до 20MB\n"
        "    Shazam определит трек и предложит скачать\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Качество аудио — 192 kbps mp3",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    url_match = is_url(text)
    search_match = text.lower().startswith("найти ")

    if not url_match and not search_match:
        return

    loop = asyncio.get_event_loop()

    # ── TikTok ────────────────────────────────────────────────────────────────
    if url_match and is_tiktok(text):
        msg = await safe_reply(update, "⏳ <b>Обрабатываю ссылку...</b>", parse_mode="HTML")
        if not msg:
            return

        resolved = await loop.run_in_executor(executor, resolve_url, text)
        tiktok_url = resolved if 'tiktok.com' in resolved else text

        await safe_edit(msg, "🎵 <b>Определяю трек через Shazam...</b>", parse_mode="HTML")

        # Пробуем распознать через Shazam — получим реальное название
        shazam_query = await asyncio.wait_for(
            loop.run_in_executor(executor, _shazam_identify_tiktok, tiktok_url),
            timeout=45
        )

        vid_key = store_url(tiktok_url)

        if shazam_query:
            aud_key = store_url(shazam_query)
            track_line = f"\n\n🎵 <b>{shazam_query}</b>"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("⬇️ Скачать mp3", callback_data=f"audio|{aud_key}"),
                InlineKeyboardButton("🎬 Скачать видео", callback_data=f"video|{vid_key}"),
            ]])
            await safe_edit(
                msg,
                f"📌 <b>TikTok</b>{track_line}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Выбери формат:",
                parse_mode="HTML",
                reply_markup=kb
            )
        else:
            try:
                meta = await asyncio.wait_for(
                    loop.run_in_executor(executor, _get_track_meta, tiktok_url), timeout=20
                )
            except asyncio.TimeoutError:
                meta = None

            if meta and meta.get('query'):
                aud_key = store_url(meta['query'])
                track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ Скачать mp3", callback_data=f"audio|{aud_key}"),
                    InlineKeyboardButton("🎬 Скачать видео", callback_data=f"video|{vid_key}"),
                ]])
            else:
                track_line = ""
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ Скачать mp3", callback_data=f"audio|{vid_key}"),
                    InlineKeyboardButton("🎬 Скачать видео", callback_data=f"video|{vid_key}"),
                ]])
            await safe_edit(
                msg,
                f"📌 <b>TikTok</b>{track_line}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Выбери формат:",
                parse_mode="HTML",
                reply_markup=kb
            )
        return

    # ── Pinterest ─────────────────────────────────────────────────────────────
    if url_match and is_pinterest(text):
        msg = await safe_reply(update, "⏳ <b>Обрабатываю ссылку...</b>", parse_mode="HTML")
        if not msg:
            return
        try:
            meta = await asyncio.wait_for(
                loop.run_in_executor(executor, _get_track_meta, text), timeout=30
            )
        except asyncio.TimeoutError:
            meta = None

        vid_key = store_url(text)
        buttons = []
        track_line = ""
        if meta and meta.get('query'):
            track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
            aud_key = store_url(meta['query'])
            buttons.append(InlineKeyboardButton("⬇️ Скачать mp3", callback_data=f"audio|{aud_key}"))
        buttons.append(InlineKeyboardButton("🎬 Скачать видео", callback_data=f"video|{vid_key}"))
        await safe_edit(
            msg,
            f"📌 <b>Pinterest</b>{track_line}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Выбери формат:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([buttons])
        )
        return

    # ── YouTube / SoundCloud / Spotify / текстовый поиск ─────────────────────
    query = text if url_match else text[6:].strip()
    ck = cache_key(query)

    if ck in cache:
        if await _send_cached(update, cache[ck]):
            return
        del cache[ck]

    display = "по ссылке" if url_match else f"«<b>{query}</b>»"
    msg = await safe_reply(update, f"🔍 Ищу {display}...", parse_mode="HTML")
    if not msg:
        return

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, _download_audio, query), timeout=90
        )
    except asyncio.TimeoutError:
        await safe_edit(msg, "⚠️ <b>Превышено время ожидания</b>\n\nСервер не отвечает. Попробуй ещё раз.", parse_mode="HTML")
        return

    if not result or not os.path.exists(result.get('file', '')):
        await safe_edit(msg, "😔 <b>Ничего не найдено</b>\n\nПопробуй уточнить запрос или проверь ссылку.", parse_mode="HTML")
        return

    try:
        duration = fmt_duration(result['duration'])
        src = source_emoji(result['source'])
        await safe_edit(
            msg,
            f"✅ <b>Нашёл!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>{result['title']}</b>\n"
            f"👤 {result['uploader']}\n"
            f"⏱ {duration}  •  {src}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📤 Отправляю...",
            parse_mode="HTML"
        )
        with open(result['file'], 'rb') as f:
            await update.message.reply_audio(f, title=result['title'], performer=result['uploader'])
        save_cache(ck, result)
        try: await msg.delete()
        except: pass
    except Exception as ex:
        log.error(f"handle_message send: {ex}")
        await safe_edit(msg, f"⚠️ <b>Ошибка при отправке</b>\n\n<code>{ex}</code>", parse_mode="HTML")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    await cb.answer()
    data = cb.data
    if '|' not in data:
        return

    action, key = data.split('|', 1)
    # Восстанавливаем оригинальное значение из хранилища
    value = get_stored(key)

    loop = asyncio.get_event_loop()
    emoji = '🎵' if 'audio' in action else '🎬'
    try:
        await cb.edit_message_text(f"{emoji} <b>Загружаю...</b>", parse_mode="HTML")
    except Exception:
        pass

    try:
        if action == 'video':
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _download_video, value), timeout=120
            )
        else:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _download_audio, value), timeout=90
            )
    except asyncio.TimeoutError:
        try: await cb.edit_message_text("⚠️ <b>Превышено время ожидания</b>\n\nПопробуй ещё раз.", parse_mode="HTML")
        except: pass
        return

    if not result or not os.path.exists(result.get('file', '')):
        try: await cb.edit_message_text("😔 <b>Не удалось скачать</b>\n\nПопробуй ещё раз.", parse_mode="HTML")
        except: pass
        return

    try:
        duration = fmt_duration(result['duration'])
        src = source_emoji(result['source'])
        try:
            await cb.edit_message_text(
                f"✅ <b>Готово!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎵 <b>{result['title']}</b>\n"
                f"👤 {result['uploader']}\n"
                f"⏱ {duration}  •  {src}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 Отправляю...",
                parse_mode="HTML"
            )
        except Exception:
            pass

        with open(result['file'], 'rb') as f:
            if result['type'] == 'audio':
                await cb.message.reply_audio(f, title=result['title'], performer=result['uploader'])
            else:
                await cb.message.reply_video(f, caption=f"🎬 <b>{result['title']}</b>", parse_mode="HTML")

        save_cache(cache_key(value), result)
        try: await cb.delete_message()
        except: pass

    except Exception as ex:
        log.error(f"handle_callback send: {ex}")
        try: await cb.edit_message_text(f"❌ Ошибка при отправке: {ex}")
        except: pass


async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видеофайл → Shazam → предложить скачать трек."""
    # Гифки приходят как animation — игнорируем
    if update.message.animation:
        return

    video = update.message.video or update.message.document
    if not video:
        return

    # Дополнительная защита: видео без длительности — скорее всего гифка
    duration = getattr(video, 'duration', None)
    if duration is not None and duration == 0:
        return

    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("⚠️ Файл больше 20MB. Обрежь и пришли снова.")
        return

    msg = await safe_reply(update, "⏳ <b>Получаю файл...</b>", parse_mode="HTML")
    if not msg:
        return

    vid_path = f"shazam_{update.message.message_id}.mp4"
    aud_path = None

    try:
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(vid_path)

        await safe_edit(msg, "🎵 <b>Определяю трек...</b>", parse_mode="HTML")

        loop = asyncio.get_event_loop()
        aud_path = await loop.run_in_executor(executor, _extract_audio_for_shazam, vid_path)

        if not aud_path:
            await safe_edit(msg, "⚠️ <b>Не удалось извлечь аудио</b>\n\nУбедись что ffmpeg установлен.", parse_mode="HTML")
            return

        track = await asyncio.wait_for(_recognize_shazam(aud_path), timeout=30)

        if not track:
            await safe_edit(msg, "😔 <b>Трек не распознан</b>\n\nПопробуй видео с более чёткой музыкой.", parse_mode="HTML")
            return

        q_key = store_url(track['query'])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⬇️ Скачать полную версию", callback_data=f"audio|{q_key}")
        ]])
        await safe_edit(
            msg,
            f"✅ <b>Трек определён!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>{track['artist']} — {track['title']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=kb
        )

    except asyncio.TimeoutError:
        await safe_edit(msg, "⚠️ <b>Shazam не ответил</b>\n\nПопробуй ещё раз.", parse_mode="HTML")
    except Exception as ex:
        log.error(f"handle_video_file: {ex}")
        await safe_edit(msg, f"⚠️ <b>Что-то пошло не так</b>\n\n<code>{ex}</code>", parse_mode="HTML")
    finally:
        for p in [vid_path, aud_path]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass


# ── Запуск ────────────────────────────────────────────────────────────────────

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("help", cmd_help))
app.add_handler(CallbackQueryHandler(handle_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler((filters.VIDEO | filters.Document.VIDEO) & ~filters.ANIMATION, handle_video_file))

log.info("Бот запущен ✅")
if not os.path.exists('cookies.txt'):
    log.warning("cookies.txt не найден — YouTube может блокировать запросы.")

app.run_polling(drop_pending_updates=True)