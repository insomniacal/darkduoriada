import os, re, asyncio, hashlib, logging, unicodedata, urllib.request, urllib.parse, json
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
from shazamio import Shazam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ── Настройки ─────────────────────────────────────────────────────────────────
TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"
TMDB_TOKEN = ""   # th

TEMP_DIR = "/tmp/musicbot"
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=8)
cache: dict = {}
CACHE_MAX = 30
_url_store: dict = {}
_trim_state: dict = {}  # {user_id: {'file': ..., 'title': ...}}

URL_PATTERN = re.compile(
    r'https?://(www\.|vm\.|vt\.)?'
    r'(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com'
    r'|pin\.it|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

# ── Утилиты ───────────────────────────────────────────────────────────────────
def is_url(t): return bool(URL_PATTERN.search(t))
def is_pinterest(t): return 'pinterest.com' in t or 'pin.it' in t
def is_tiktok(t): return 'tiktok.com' in t
def is_spotify(t): return 'spotify.com' in t
def cache_key(q): return hashlib.md5(q.lower().strip().encode()).hexdigest()

def store_url(v):
    k = hashlib.md5(v.encode()).hexdigest()[:16]
    _url_store[k] = v
    return k

def get_stored(k): return _url_store.get(k, k)
def get_cookie_opts(): return {'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt') else {}

def fmt_dur(s):
    s = int(s or 0)
    return f"{s//60}:{s%60:02d}"

def src_emoji(s):
    s = s.lower()
    if 'youtube' in s: return '▶️ YouTube'
    if 'soundcloud' in s: return '🔊 SoundCloud'
    if 'tiktok' in s: return '🎵 TikTok'
    if 'pinterest' in s: return '📌 Pinterest'
    return '🌐 Web'

def clean_q(text):
    r = []
    for ch in text:
        cp = ord(ch)
        if 0x1D400 <= cp <= 0x1D7FF:
            n = unicodedata.normalize('NFKD', ch).encode('ascii','ignore').decode('ascii')
            r.append(n)
        else:
            r.append(ch)
    c = ' '.join(''.join(r).split()).strip()
    return c if c else text

def resolve_url(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp: return resp.url
    except: return url

def parse_time(s):
    s = s.strip()
    parts = s.split(':')
    try:
        if len(parts) == 1: return int(parts[0])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except: pass
    return None

def save_cache(ck, result):
    global cache
    if len(cache) >= CACHE_MAX:
        old = cache.pop(next(iter(cache)))
        f = old.get('file', '')
        if f and os.path.exists(f):
            try: os.remove(f)
            except: pass
    cache[ck] = result

def tmpfile(name): return os.path.join(TEMP_DIR, name)

# ── Безопасная отправка ───────────────────────────────────────────────────────
async def safe_edit(msg, text, **kw):
    for _ in range(3):
        try: await msg.edit_text(text, **kw); return
        except RetryAfter as e: await asyncio.sleep(e.retry_after + 1)
        except (BadRequest, TimedOut, NetworkError) as e: log.warning(f"safe_edit: {e}"); return

async def safe_reply(update, text, **kw):
    for _ in range(3):
        try: return await update.message.reply_text(text, **kw)
        except RetryAfter as e: await asyncio.sleep(e.retry_after + 1)
        except (BadRequest, TimedOut, NetworkError) as e: log.warning(f"safe_reply: {e}"); return None
    return None

# ── yt-dlp настройки ──────────────────────────────────────────────────────────
BASE_OPTS = {
    'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'retries': 5,
    'fragment_retries': 5, 'http_chunk_size': 10*1024*1024, 'extractor_retries': 3,
    'noplaylist': True, 'concurrent_fragment_downloads': 4,
    'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
}

# ── TMDB ──────────────────────────────────────────────────────────────────────
def tmdb_search(query):
    if not TMDB_TOKEN: return None
    headers = {'Authorization': f'Bearer {TMDB_TOKEN}', 'accept': 'application/json'}
    results_all = []
    for mt in ['movie', 'tv']:
        url = f'https://api.themoviedb.org/3/search/{mt}?query={urllib.parse.quote(query)}&language=ru-RU&page=1'
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for item in data.get('results', [])[:3]:
                    item['_mt'] = mt
                    results_all.append(item)
        except Exception as ex: log.warning(f"TMDB {mt}: {ex}")
    if not results_all: return None
    best = max(results_all, key=lambda x: x.get('popularity', 0))
    mt = best.get('_mt', 'movie')
    title = best.get('title') or best.get('name', '')
    orig = best.get('original_title') or best.get('original_name', '')
    overview = (best.get('overview', '') or 'Описание недоступно')[:350]
    if len(best.get('overview', '')) > 350: overview += '...'
    rating = best.get('vote_average', 0)
    votes = best.get('vote_count', 0)
    date = best.get('release_date') or best.get('first_air_date', '')
    year = date[:4] if date else '?'
    poster = best.get('poster_path', '')
    poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None
    tmdb_id = best.get('id')
    genre_ids = best.get('genre_ids', [])
    origin = best.get('origin_country', [])
    is_anime = (16 in genre_ids and 'JP' in origin)
    type_label = {'movie': '🎬 Фильм', 'tv': '📺 Сериал'}.get(mt, '🎬')
    if is_anime: type_label = '🌸 Аниме'
    genres = []
    try:
        req = urllib.request.Request(f'https://api.themoviedb.org/3/{mt}/{tmdb_id}?language=ru-RU', headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            detail = json.loads(resp.read())
            genres = [g['name'] for g in detail.get('genres', [])[:3]]
    except: pass
    return {
        'title': title, 'original_title': orig, 'type': type_label, 'year': year,
        'rating': rating, 'vote_count': votes, 'overview': overview,
        'poster_url': poster_url, 'genres': ', '.join(genres)
    }

def tmdb_search_by_image_url(image_url):
    """Пытается определить контент по URL изображения через reverse-поиск названия."""
    # Получаем текст из URL (часто содержит название)
    path = urllib.parse.urlparse(image_url).path
    name_part = os.path.basename(path).replace('-', ' ').replace('_', ' ')
    name_clean = re.sub(r'\.[a-z]{2,4}$', '', name_part, flags=re.I).strip()
    if len(name_clean) > 3:
        return tmdb_search(name_clean)
    return None

# ── Скачивание ────────────────────────────────────────────────────────────────
def _get_spotify_query(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            t = info.get('title', ''); a = info.get('artist') or info.get('uploader', '')
            return f"{a} {t}".strip() or None
    except: return None

def _get_track_meta(url):
    try:
        opts = {**BASE_OPTS, **get_cookie_opts(), 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            e = info['entries'][0] if 'entries' in info else info
            track = e.get('track') or e.get('music_title') or e.get('music') or ''
            artist = e.get('artist') or e.get('music_author') or e.get('creator') or e.get('uploader', '')
            vtitle = e.get('title', '')
            name = track or vtitle
            if name:
                return {'title': clean_q(name), 'artist': clean_q(artist),
                        'query': f"{clean_q(artist)} {clean_q(name)}".strip(), 'video_title': vtitle}
    except Exception as ex: log.warning(f"_get_track_meta: {ex}")
    return None

def _get_video_title(url):
    """Получает название видео для TMDB поиска."""
    try:
        opts = {**BASE_OPTS, **get_cookie_opts(), 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            e = info['entries'][0] if 'entries' in info else info
            return e.get('title', '')
    except: return ''

def _shazam_identify_tiktok(tiktok_url):
    import asyncio as _a
    pid = os.getpid()
    tmp = tmpfile(f'shazam_tt_{pid}.mp3')
    opts = {
        **BASE_OPTS, **get_cookie_opts(), 'format': 'bestaudio/best',
        'outtmpl': tmpfile(f'shazam_tt_{pid}.%(ext)s'),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
        'postprocessor_args': ['-t', '30'],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.extract_info(tiktok_url, download=True)
        if not os.path.exists(tmp): return None
        loop = _a.new_event_loop()
        try:
            shazam = Shazam()
            result = loop.run_until_complete(shazam.recognize(tmp))
        finally: loop.close()
        if not result.get('matches'): return None
        track = result.get('track', {})
        t = track.get('title', ''); a = track.get('subtitle', '')
        return f"{a} {t}".strip() if t else None
    except Exception as ex: log.warning(f"_shazam_tiktok: {ex}")
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass
    return None

def _download_audio(query_or_url):
    pid = os.getpid()
    out = tmpfile(f'audio_{pid}')
    opts = {
        **BASE_OPTS, **get_cookie_opts(),
        'format': 'bestaudio[filesize<50M]/bestaudio/best',
        'outtmpl': f'{out}.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
    }
    if is_spotify(query_or_url):
        sq = _get_spotify_query(query_or_url)
        sources = [f"ytsearch:{sq}", f"scsearch:{sq}"] if sq else []
    elif is_url(query_or_url): sources = [query_or_url]
    else:
        q = clean_q(query_or_url)
        sources = [f"scsearch:{q}", f"ytsearch:{q}"]
    for source in sources:
        for attempt in range(2):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(source, download=True)
                    e = info['entries'][0] if 'entries' in info else info
                    file = f'{out}.mp3'
                    if os.path.exists(file):
                        return {'type': 'audio', 'title': e.get('title', query_or_url),
                                'duration': e.get('duration', 0) or 0, 'uploader': e.get('uploader', ''),
                                'source': e.get('extractor', ''), 'file': file}
            except Exception as ex:
                err = str(ex).lower()
                if ('timed out' in err or 'timeout' in err) and attempt == 0: continue
                log.warning(f"_download_audio: {ex}"); break
    return None

def _download_video(url):
    pid = os.getpid()
    out = tmpfile(f'video_{pid}')
    opts = {
        **BASE_OPTS, **get_cookie_opts(),
        'format': 'bestvideo[height<=720][filesize<90M]+bestaudio/best[height<=720]/best',
        'outtmpl': f'{out}.%(ext)s', 'merge_output_format': 'mp4',
    }
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                e = info['entries'][0] if 'entries' in info else info
                for ext in ['mp4', 'mkv', 'webm', 'mov']:
                    path = f'{out}.{ext}'
                    if os.path.exists(path):
                        return {'type': 'video', 'title': e.get('title', 'video'),
                                'duration': e.get('duration', 0) or 0, 'uploader': e.get('uploader', ''),
                                'source': e.get('extractor', ''), 'file': path}
        except Exception as ex:
            err = str(ex).lower()
            if ('timed out' in err or 'timeout' in err) and attempt == 0: continue
            log.warning(f"_download_video: {ex}"); break
    return None

def _search_similar_tracks(query, max_results=5):
    """Ищет похожие треки / треки исполнителя через SoundCloud и YouTube."""
    results = []
    for source in [f"scsearch{max_results}:{query}", f"ytsearch{max_results}:{query}"]:
        try:
            opts = {**BASE_OPTS, 'skip_download': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False)
                entries = info.get('entries', [])
                for e in entries:
                    if not e: continue
                    title = e.get('title', '')
                    url = e.get('url') or e.get('webpage_url', '')
                    dur = e.get('duration', 0) or 0
                    uploader = e.get('uploader', '') or e.get('channel', '')
                    if title and url:
                        results.append({'title': title, 'url': url, 'duration': dur, 'uploader': uploader})
                    if len(results) >= max_results:
                        break
        except Exception as ex: log.warning(f"_search_similar: {ex}")
        if len(results) >= max_results:
            break
    # Убираем дубли по названию
    seen = set()
    unique = []
    for r in results:
        key = r['title'].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:max_results]

def _extract_audio_for_shazam(video_path):
    out = video_path + '_shazam.mp3'
    ret = os.system(f'ffmpeg -y -i "{video_path}" -t 30 -vn -ar 44100 -ac 2 -b:a 128k "{out}" -loglevel quiet')
    return out if ret == 0 and os.path.exists(out) else None

def _trim_audio(src, start_sec, end_sec):
    """Обрезает mp3: start_sec→end_sec (end_sec=None → до конца)."""
    out = src.replace('.mp3', f'_trim_{start_sec}_{end_sec or "end"}.mp3')
    if end_sec is not None:
        cmd = f'ffmpeg -y -i "{src}" -ss {start_sec} -t {end_sec - start_sec} -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
    else:
        cmd = f'ffmpeg -y -i "{src}" -ss {start_sec} -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
    ret = os.system(cmd)
    return out if ret == 0 and os.path.exists(out) else None

async def _recognize_shazam(file_path):
    try:
        shazam = Shazam()
        result = await shazam.recognize(file_path)
        if not result.get('matches'): return None
        track = result.get('track', {})
        t = track.get('title', ''); a = track.get('subtitle', '')
        if t: return {'title': t, 'artist': a, 'query': f"{a} {t}".strip()}
    except Exception as ex: log.warning(f"Shazam: {ex}")
    return None

# ── Кэш: отправка ─────────────────────────────────────────────────────────────
async def _send_cached(update, cached):
    f = cached.get('file', '')
    if not os.path.exists(f): return False
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
    except: return False

# ── Вспомогательные функции отправки ──────────────────────────────────────────
async def send_tmdb_result(update, result):
    """Отправляет карточку фильма/сериала/аниме с постером."""
    orig_line = f"\n🔤 <i>{result['original_title']}</i>" if result['original_title'] != result['title'] else ''
    genres_line = f"\n🏷 {result['genres']}" if result['genres'] else ''
    caption = (
        f"{result['type']}  •  {result['year']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>{result['title']}</b>{orig_line}{genres_line}\n"
        f"⭐ {result['rating']:.1f}/10  ({result['vote_count']} голосов)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {result['overview']}"
    )
    if result['poster_url']:
        try:
            await update.message.reply_photo(photo=result['poster_url'], caption=caption, parse_mode="HTML")
            return
        except: pass
    await safe_reply(update, caption, parse_mode="HTML")

async def send_audio_result(update, result, uid):
    """Отправляет аудио и сохраняет в trim_state."""
    with open(result['file'], 'rb') as f:
        await update.message.reply_audio(f, title=result['title'], performer=result['uploader'])
    _trim_state[uid] = {'file': result['file'], 'title': result['title'], 'uploader': result['uploader']}

# ── Команды ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"🎵 <b>Добро пожаловать, {name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Что умею:</b>\n\n"
        f"🔗 <b>Ссылка</b> — просто отправь:\n"
        f"    TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
        f"🔍 <b>Поиск музыки:</b>\n"
        f"    <code>найти The Weeknd Blinding Lights</code>\n\n"
        f"🎭 <b>Найти фильм/сериал/аниме:</b>\n"
        f"    <code>фильм Inception</code>  <code>сериал Breaking Bad</code>\n"
        f"    — или просто пришли фото/постер!\n\n"
        f"✂️ <b>Обрезать музыку</b> (после скачивания):\n"
        f"    <code>обрезать 0:30 0:45</code> — конкретный отрезок\n"
        f"    <code>обрезать до 1:00</code> — первая минута\n"
        f"    <code>обрезать с 1:00</code> — с 1 мин до конца\n\n"
        f"🎬 <b>Распознать трек</b> — пришли видео до 20MB\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ Повторные запросы — мгновенно",
        parse_mode="HTML"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Инструкция</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔗 TikTok / Pinterest → выбери Аудио или Видео\n"
        "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
        "🔍 <code>найти [исполнитель трек]</code>\n\n"
        "🎭 <code>фильм [название]</code> / <code>сериал</code> / <code>аниме</code>\n"
        "    Или пришли фото/постер — найду сам!\n\n"
        "✂️ После скачивания трека:\n"
        "    <code>обрезать 0:30 0:45</code> — с 30 до 45 сек\n"
        "    <code>обрезать до 1:30</code> — первые 1:30\n"
        "    <code>обрезать с 0:30</code> — с 30 сек до конца\n\n"
        "🎬 Пришли видеофайл до 20MB → Shazam распознает\n\n"
        "🎵 После скачивания трека:\n"
        "    Кнопки [Похожие треки] [Треки исполнителя]",
        parse_mode="HTML"
    )

# ── Обработчик фото ───────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь прислал фото — пробуем определить фильм/сериал/аниме."""
    caption = (update.message.caption or '').strip().lower()

    # Если есть подпись с командой найти — ищем по подписи
    search_query = None
    if caption.startswith('найти '):
        search_query = update.message.caption.strip()[6:]
    elif caption:
        search_query = update.message.caption.strip()

    if not TMDB_TOKEN:
        await safe_reply(update,
            "⚠️ Для распознавания по фото нужен TMDB_TOKEN.\n"
            "Добавь его в настройки бота.",
            parse_mode="HTML")
        return

    msg = await safe_reply(update, "🔍 <b>Ищу в базе фильмов...</b>", parse_mode="HTML")
    if not msg: return

    loop = asyncio.get_event_loop()

    if search_query:
        result = await loop.run_in_executor(executor, tmdb_search, search_query)
    else:
        # Нет текста — пробуем получить file_path и угадать по URL
        try:
            photo = update.message.photo[-1]  # самое большое фото
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
            result = await loop.run_in_executor(executor, tmdb_search_by_image_url, file_path)
        except Exception:
            result = None

    try: await msg.delete()
    except: pass

    if not result:
        await safe_reply(update,
            "😔 <b>Не смог определить</b>\n\n"
            "Пришли фото с подписью — название фильма или сериала:\n"
            "<code>фильм Inception</code>",
            parse_mode="HTML")
        return

    await send_tmdb_result(update, result)

# ── Обработчик текста ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    loop = asyncio.get_event_loop()
    lower = text.lower()

    # ── Обрезка ───────────────────────────────────────────────────────────────
    m_range = re.match(r'^обрезать\s+(\S+)\s+(\S+)\s*$', lower)
    m_to    = re.match(r'^обрезать\s+до\s+(\S+)\s*$', lower)
    m_from  = re.match(r'^обрезать\s+с\s+(\S+)\s*$', lower)

    if m_range or m_to or m_from:
        state = _trim_state.get(uid)
        if not state or not os.path.exists(state.get('file', '')):
            await safe_reply(update,
                "⚠️ Нет трека для обрезки.\n"
                "Сначала скачай музыку, потом напиши:\n"
                "<code>обрезать 0:30 0:45</code>", parse_mode="HTML")
            return
        if m_range:
            start_sec = parse_time(m_range.group(1))
            end_sec   = parse_time(m_range.group(2))
        elif m_to:
            start_sec = 0
            end_sec   = parse_time(m_to.group(1))
        else:
            start_sec = parse_time(m_from.group(1))
            end_sec   = None
        if start_sec is None:
            await safe_reply(update, "❌ Неверный формат. Пример: <code>обрезать 0:30 0:45</code>", parse_mode="HTML")
            return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, "❌ Конец должен быть больше начала.", parse_mode="HTML")
            return
        msg = await safe_reply(update, "✂️ <b>Обрезаю...</b>", parse_mode="HTML")
        trimmed = await loop.run_in_executor(executor, _trim_audio, state['file'], start_sec, end_sec)
        if not trimmed:
            await safe_edit(msg, "❌ Не удалось обрезать. Убедись что ffmpeg установлен.", parse_mode="HTML")
            return
        s_fmt = fmt_dur(start_sec)
        e_fmt = fmt_dur(end_sec) if end_sec else "конец"
        await safe_edit(msg, f"✅ Готово! ⏱ {s_fmt} → {e_fmt}\n📤 Отправляю...", parse_mode="HTML")
        with open(trimmed, 'rb') as f:
            await update.message.reply_audio(f, title=f"{state['title']} [{s_fmt}-{e_fmt}]",
                                              performer=state.get('uploader', ''))
        try: await msg.delete()
        except: pass
        try: os.remove(trimmed)
        except: pass
        return

    # ── Фильм/сериал/аниме по тексту ─────────────────────────────────────────
    media_m = re.match(r'^(фильм|сериал|аниме|кино)\s+(.+)$', lower)
    if media_m:
        query = text[len(media_m.group(1)):].strip()
        msg = await safe_reply(update, "🔍 <b>Ищу в TMDB...</b>", parse_mode="HTML")
        if not msg: return
        if not TMDB_TOKEN:
            await safe_edit(msg, "⚠️ TMDB_TOKEN не задан. Получи бесплатный ключ на themoviedb.org", parse_mode="HTML")
            return
        result = await loop.run_in_executor(executor, tmdb_search, query)
        try: await msg.delete()
        except: pass
        if not result:
            await safe_reply(update, "😔 Ничего не найдено. Попробуй уточнить название.", parse_mode="HTML")
            return
        await send_tmdb_result(update, result)
        return

    # ── Музыка ────────────────────────────────────────────────────────────────
    url_match = is_url(text)
    search_match = lower.startswith("найти ")
    if not url_match and not search_match: return

    # ── TikTok ────────────────────────────────────────────────────────────────
    if url_match and is_tiktok(text):
        msg = await safe_reply(update, "⏳ <b>Обрабатываю...</b>", parse_mode="HTML")
        if not msg: return
        resolved = await loop.run_in_executor(executor, resolve_url, text)
        tiktok_url = resolved if 'tiktok.com' in resolved else text
        await safe_edit(msg, "🎵 <b>Определяю трек через Shazam...</b>", parse_mode="HTML")
        try:
            shazam_q = await asyncio.wait_for(
                loop.run_in_executor(executor, _shazam_identify_tiktok, tiktok_url), timeout=45)
        except asyncio.TimeoutError: shazam_q = None
        vid_key = store_url(tiktok_url)
        if shazam_q:
            aud_key = store_url(shazam_q)
            track_line = f"\n\n🎵 <b>{shazam_q}</b>"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"),
                InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"),
            ]])
        else:
            try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, tiktok_url), timeout=20)
            except: meta = None
            if meta and meta.get('query'):
                aud_key = store_url(meta['query'])
                track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"),
                    InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"),
                ]])
            else:
                track_line = ""
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{vid_key}"),
                    InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"),
                ]])
        await safe_edit(msg, f"📱 <b>TikTok</b>{track_line}\n\n━━━━━━━━━━━━━━━━━━━━━━\nВыбери формат:",
                        parse_mode="HTML", reply_markup=kb)
        return

    # ── Pinterest ─────────────────────────────────────────────────────────────
    if url_match and is_pinterest(text):
        msg = await safe_reply(update, "⏳ <b>Обрабатываю...</b>", parse_mode="HTML")
        if not msg: return
        try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, text), timeout=30)
        except: meta = None
        vid_key = store_url(text); buttons = []; track_line = ""
        if meta and meta.get('query'):
            track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
            buttons.append(InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{store_url(meta['query'])}"))
        buttons.append(InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"))
        await safe_edit(msg, f"📌 <b>Pinterest</b>{track_line}\n\n━━━━━━━━━━━━━━━━━━━━━━\nВыбери формат:",
                        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([buttons]))
        return

    # ── YouTube / SoundCloud / Spotify / текстовый поиск ─────────────────────
    query = text if url_match else text[6:].strip()
    ck = cache_key(query)
    if ck in cache:
        if await _send_cached(update, cache[ck]): return
        del cache[ck]

    display = "по ссылке" if url_match else f"«<b>{query}</b>»"
    msg = await safe_reply(update, f"🔍 Ищу {display}...", parse_mode="HTML")
    if not msg: return

    # Если это YouTube/другая видеоссылка — получим название для TMDB параллельно
    video_title_future = None
    if url_match and not is_spotify(text):
        video_title_future = loop.run_in_executor(executor, _get_video_title, text)

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, _download_audio, query), timeout=90)
    except asyncio.TimeoutError:
        await safe_edit(msg, "⚠️ Превышено время ожидания. Попробуй ещё раз.", parse_mode="HTML"); return

    if not result or not os.path.exists(result.get('file', '')):
        await safe_edit(msg, "😔 Ничего не найдено. Попробуй уточнить запрос.", parse_mode="HTML"); return

    try:
        # Строим кнопки: похожие треки + треки исполнителя
        uploader = result['uploader']
        title = result['title']
        similar_key = store_url(f"{uploader} {title}")
        artist_key  = store_url(uploader)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔀 Похожие треки", callback_data=f"similar|{similar_key}"),
            InlineKeyboardButton(f"🎤 Ещё от исполнителя", callback_data=f"artist|{artist_key}"),
        ]])

        await safe_edit(
            msg,
            f"✅ <b>Нашёл!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>{title}</b>\n"
            f"👤 {uploader}\n"
            f"⏱ {fmt_dur(result['duration'])}  •  {src_emoji(result['source'])}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📤 Отправляю...",
            parse_mode="HTML"
        )
        with open(result['file'], 'rb') as f:
            await update.message.reply_audio(f, title=title, performer=uploader, reply_markup=kb)

        _trim_state[uid] = {'file': result['file'], 'title': title, 'uploader': uploader}
        save_cache(ck, result)
        try: await msg.delete()
        except: pass

        # Если ссылка на видео — покажем TMDB карточку
        if video_title_future and TMDB_TOKEN:
            try:
                vtitle = await asyncio.wait_for(asyncio.wrap_future(video_title_future), timeout=10)
                if vtitle:
                    tmdb_result = await loop.run_in_executor(executor, tmdb_search, vtitle)
                    if tmdb_result:
                        await send_tmdb_result(update, tmdb_result)
            except: pass

    except Exception as ex:
        log.error(f"handle_message send: {ex}")
        await safe_edit(msg, f"⚠️ Ошибка: <code>{ex}</code>", parse_mode="HTML")

# ── Callback кнопок ───────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    await cb.answer()
    uid = update.effective_user.id
    if '|' not in cb.data: return
    action, key = cb.data.split('|', 1)
    value = get_stored(key)
    loop = asyncio.get_event_loop()

    # ── Похожие треки / треки исполнителя ────────────────────────────────────
    if action in ('similar', 'artist'):
        label = "похожие треки" if action == 'similar' else f"треки «{value}»"
        try: await cb.edit_message_text(f"🔍 Ищу {label}...", parse_mode="HTML")
        except: pass

        search_q = value if action == 'similar' else f"{value} best songs"
        tracks = await loop.run_in_executor(executor, _search_similar_tracks, search_q)

        if not tracks:
            try: await cb.edit_message_text("😔 Ничего не нашёл. Попробуй позже.")
            except: pass
            return

        # Строим список с кнопками
        buttons = []
        lines = []
        for i, t in enumerate(tracks, 1):
            dur = fmt_dur(t['duration']) if t['duration'] else '?'
            lines.append(f"{i}. <b>{t['title']}</b> — {t['uploader']} ⏱{dur}")
            t_key = store_url(t['url'])
            buttons.append([InlineKeyboardButton(f"⬇️ {i}. {t['title'][:30]}", callback_data=f"audio|{t_key}")])

        header = "🔀 <b>Похожие треки:</b>" if action == 'similar' else f"🎤 <b>Треки исполнителя:</b>"
        text = header + "\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
        try:
            await cb.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as ex:
            log.warning(f"similar edit: {ex}")
        return

    # ── Скачать аудио / видео ─────────────────────────────────────────────────
    emoji = '🎵' if 'audio' in action else '🎬'
    try: await cb.edit_message_text(f"{emoji} <b>Загружаю...</b>", parse_mode="HTML")
    except: pass

    try:
        if action == 'video':
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _download_video, value), timeout=120)
            # Если скачали видео — попробуем найти в TMDB по названию
            if result and TMDB_TOKEN:
                vtitle = result.get('title', '')
                if vtitle:
                    tmdb_r = await loop.run_in_executor(executor, tmdb_search, vtitle)
                    if tmdb_r:
                        # Добавим подпись с названием фильма/сериала
                        result['tmdb'] = tmdb_r
        else:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _download_audio, value), timeout=90)
    except asyncio.TimeoutError:
        try: await cb.edit_message_text("⚠️ Превышено время ожидания.", parse_mode="HTML")
        except: pass
        return

    if not result or not os.path.exists(result.get('file', '')):
        try: await cb.edit_message_text("😔 Не удалось скачать.", parse_mode="HTML")
        except: pass
        return

    try:
        title = result['title']
        uploader = result['uploader']
        try:
            await cb.edit_message_text(
                f"✅ <b>{title}</b>\n"
                f"👤 {uploader}  •  {src_emoji(result['source'])}\n"
                f"⏱ {fmt_dur(result['duration'])}\n"
                f"📤 Отправляю...",
                parse_mode="HTML"
            )
        except: pass

        if result['type'] == 'audio':
            # Кнопки для аудио
            similar_key = store_url(f"{uploader} {title}")
            artist_key  = store_url(uploader)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔀 Похожие", callback_data=f"similar|{similar_key}"),
                InlineKeyboardButton("🎤 Ещё от исполнителя", callback_data=f"artist|{artist_key}"),
            ]])
            with open(result['file'], 'rb') as f:
                await cb.message.reply_audio(f, title=title, performer=uploader, reply_markup=kb)
            _trim_state[uid] = {'file': result['file'], 'title': title, 'uploader': uploader}
        else:
            # Видео — добавляем TMDB подпись если нашли
            tmdb_r = result.get('tmdb')
            if tmdb_r:
                cap = (
                    f"🎬 <b>{result['title']}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{tmdb_r['type']}  •  {tmdb_r['year']}\n"
                    f"⭐ {tmdb_r['rating']:.1f}/10\n"
                    f"📝 {tmdb_r['overview'][:200]}..."
                )
            else:
                cap = f"🎬 <b>{result['title']}</b>"
            with open(result['file'], 'rb') as f:
                await cb.message.reply_video(f, caption=cap, parse_mode="HTML")

        save_cache(cache_key(value), result)
        try: await cb.delete_message()
        except: pass
    except Exception as ex:
        log.error(f"handle_callback send: {ex}")
        try: await cb.edit_message_text(f"❌ {ex}")
        except: pass

# ── Видеофайл → Shazam ───────────────────────────────────────────────────────
async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.animation: return
    video = update.message.video or update.message.document
    if not video: return
    dur = getattr(video, 'duration', None)
    if dur is not None and dur == 0: return
    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("⚠️ Файл больше 20MB."); return

    msg = await safe_reply(update, "⏳ <b>Получаю файл...</b>", parse_mode="HTML")
    if not msg: return

    vid_path = tmpfile(f"shazam_{update.message.message_id}.mp4")
    aud_path = None
    try:
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(vid_path)
        await safe_edit(msg, "🎵 <b>Определяю трек...</b>", parse_mode="HTML")
        loop = asyncio.get_event_loop()
        aud_path = await loop.run_in_executor(executor, _extract_audio_for_shazam, vid_path)
        if not aud_path:
            await safe_edit(msg, "⚠️ Не удалось извлечь аудио. Убедись что ffmpeg установлен.", parse_mode="HTML")
            return
        track = await asyncio.wait_for(_recognize_shazam(aud_path), timeout=30)
        if not track:
            await safe_edit(msg, "😔 Трек не распознан. Попробуй видео с более чёткой музыкой.", parse_mode="HTML")
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
            parse_mode="HTML", reply_markup=kb
        )
    except asyncio.TimeoutError:
        await safe_edit(msg, "⚠️ Shazam не ответил. Попробуй ещё раз.", parse_mode="HTML")
    except Exception as ex:
        log.error(f"handle_video_file: {ex}")
        await safe_edit(msg, f"⚠️ Ошибка: <code>{ex}</code>", parse_mode="HTML")
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
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler((filters.VIDEO | filters.Document.VIDEO) & ~filters.ANIMATION, handle_video_file))

log.info("Бот запущен ✅")
if not TMDB_TOKEN: log.warning("TMDB_TOKEN не задан — поиск фильмов и распознавание по фото недоступны.")
if not os.path.exists('cookies.txt'): log.warning("cookies.txt не найден — YouTube может блокировать запросы.")

app.run_polling(drop_pending_updates=True)