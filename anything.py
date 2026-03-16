import os, re, asyncio, hashlib, logging, unicodedata, urllib.request, urllib.parse, json
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
from shazamio import Shazam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ── Переводы ──────────────────────────────────────────────────────────────────
STRINGS = {
    'ru': {
        'choose_lang':        "🌐 Выбери язык / Choose language:",
        'lang_set':           "✅ Язык установлен: <b>Русский</b>",
        'welcome':            "🎵 <b>Добро пожаловать, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<b>Что умею:</b>\n\n🔗 <b>Ссылка</b> — просто отправь:\n    TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n🔍 <b>Поиск музыки:</b>\n    <code>найти The Weeknd Blinding Lights</code>\n\n✂️ <b>Обрезать трек</b> (после скачивания):\n    <code>обрезать 0:30 0:45</code>\n\n📁 <b>Библиотека</b> — /library\n    Сохраняй треки в папки\n\n🎬 <b>Распознать трек</b> — пришли видео до 20MB\n\n━━━━━━━━━━━━━━━━━━━━━━\n⚡️ Повторные запросы — мгновенно",
        'help':               "📖 <b>Инструкция</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n🔗 TikTok / Pinterest → выбери Аудио или Видео\n▶️ YouTube / SoundCloud / Spotify → mp3\n\n🔍 <code>найти [исполнитель трек]</code>\n\n✂️ После скачивания трека:\n    <code>обрезать 0:30 0:45</code> — с 30 до 45 сек\n    <code>обрезать до 1:30</code> — первые 1:30\n    <code>обрезать с 0:30</code> — с 30 сек до конца\n\n📁 /library — личная библиотека треков\n\n🎬 Пришли видеофайл до 20MB — найду трек",
        'processing':         "⏳ <b>Обрабатываю...</b>",
        'searching_track':    "🎵 <b>Ищу трек...</b>",
        'choose_action':      "Выбери действие:",
        'choose_format':      "Выбери формат:",
        'found':              "✅ <b>Нашёл!</b>",
        'not_found':          "😔 Ничего не найдено. Попробуй уточнить запрос.",
        'timeout':            "⚠️ Превышено время ожидания.",
        'sending':            "📤 Отправляю...",
        'track_identified':   "✅ <b>Трек определён!</b>",
        'track_not_found':    "😔 <b>Трек не распознан</b>\n\nПопробуй видео с более чёткой музыкой.",
        'shazam_timeout':     "⚠️ Shazam не ответил.",
        'file_too_big':       "⚠️ Файл больше 20MB.",
        'video_received':     "🎬 <b>Видео получено</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nЧто хочешь сделать?",
        'find_track':         "🔍 Найти трек",
        'trim':               "✂️ Обрезать",
        'trim_title':         "✂️ <b>Обрезка видео</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nНапиши время:\n<code>начало конец</code>\n\nПримеры:\n  <code>0:05 0:10</code> — с 5 по 10 сек\n  <code>5 10</code> — то же самое",
        'trim_confirm':       "✂️ <b>Обрежу:</b> {s} → {e}\n\nВ каком формате отправить?",
        'as_audio':           "🎵 Как аудио (mp3)",
        'as_video':           "🎬 Как видео (mp4)",
        'back':               "◀️ Назад",
        'change':             "◀️ Изменить",
        'trim_done':          "✅ <b>Готово!</b>  ✂️ {s} → {e}\n📤 Отправляю...",
        'trim_error':         "⚠️ Не удалось обрезать. Убедись что ffmpeg установлен.",
        'file_not_found':     "❌ Файл не найден, пришли видео заново",
        'trim_bad_format':    "❌ Неверный формат.\n\nПример: <code>0:05 0:10</code> или <code>5 10</code>",
        'trim_bad_time':      "❌ Конец должен быть больше начала.",
        'trim_bad_time2':     "❌ Неверный формат времени. Пример: <code>0:05 0:10</code>",
        'lib_title':          "🎵 <b>Моя библиотека</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n",
        'lib_folders':        "📂 Папок: <b>{n}</b>\n\nВыбери папку:",
        'lib_empty':          "Библиотека пуста.\nСоздай папку и добавляй треки!",
        'lib_new_folder':     "➕ Создать папку",
        'lib_folder_empty':   "Папка пустая.\n\nПосле скачивания трека нажми кнопку\n<b>📁 Сохранить в библиотеку</b>",
        'lib_tracks':         "Треков: <b>{n}</b>\n\nНажми на трек — отправлю:",
        'lib_del_folder':     "🗑 Удалить папку",
        'lib_save_btn':       "📁 Сохранить в библиотеку",
        'lib_saved':          "✅ Сохранено в <b>{folder}</b>",
        'lib_duplicate':      "⚠️ Этот трек уже есть в папке.",
        'lib_no_folders':     "❌ Нет папок. Сначала создай папку в /library",
        'lib_ask_folder':     "📁 В какую папку сохранить?",
        'lib_ask_name':       "📁 Напиши название новой папки:",
        'lib_created':        "✅ Папка <b>«{name}»</b> создана!\n\nТеперь скачай трек и нажми <b>📁 Сохранить в библиотеку</b>",
        'lib_name_too_long':  "❌ Название слишком длинное (макс. 50 символов).",
        'search_prefix':      'найти ',
        'trim_prefix':        'обрезать ',
        'similar':            "🔀 Похожие",
        'by_artist':          "🎤 Ещё от исполнителя",
        'download_full':      "⬇️ Скачать полную версию",
        'language_cmd':       "🌐 Выбери язык:",
    },
    'en': {
        'choose_lang':        "🌐 Choose language / Выбери язык:",
        'lang_set':           "✅ Language set: <b>English</b>",
        'welcome':            "🎵 <b>Welcome, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<b>What I can do:</b>\n\n🔗 <b>Link</b> — just send:\n    TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n🔍 <b>Search music:</b>\n    <code>find The Weeknd Blinding Lights</code>\n\n✂️ <b>Trim track</b> (after download):\n    <code>trim 0:30 0:45</code>\n\n📁 <b>Library</b> — /library\n    Save tracks to folders\n\n🎬 <b>Identify track</b> — send video up to 20MB\n\n━━━━━━━━━━━━━━━━━━━━━━\n⚡️ Repeated requests — instant",
        'help':               "📖 <b>Instructions</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n🔗 TikTok / Pinterest → choose Audio or Video\n▶️ YouTube / SoundCloud / Spotify → mp3\n\n🔍 <code>find [artist track]</code>\n\n✂️ After downloading:\n    <code>trim 0:30 0:45</code> — from 30 to 45 sec\n    <code>trim to 1:30</code> — first 1:30\n    <code>trim from 0:30</code> — from 30 sec to end\n\n📁 /library — personal track library\n\n🎬 Send video up to 20MB — I'll find the track",
        'processing':         "⏳ <b>Processing...</b>",
        'searching_track':    "🎵 <b>Searching track...</b>",
        'choose_action':      "Choose action:",
        'choose_format':      "Choose format:",
        'found':              "✅ <b>Found!</b>",
        'not_found':          "😔 Nothing found. Try a more specific query.",
        'timeout':            "⚠️ Request timed out.",
        'sending':            "📤 Sending...",
        'track_identified':   "✅ <b>Track identified!</b>",
        'track_not_found':    "😔 <b>Track not recognized</b>\n\nTry a video with clearer music.",
        'shazam_timeout':     "⚠️ Recognition timed out.",
        'file_too_big':       "⚠️ File is larger than 20MB.",
        'video_received':     "🎬 <b>Video received</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nWhat do you want to do?",
        'find_track':         "🔍 Find track",
        'trim':               "✂️ Trim",
        'trim_title':         "✂️ <b>Trim video</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nWrite time:\n<code>start end</code>\n\nExamples:\n  <code>0:05 0:10</code> — from 5 to 10 sec\n  <code>5 10</code> — same thing",
        'trim_confirm':       "✂️ <b>Will trim:</b> {s} → {e}\n\nWhat format to send?",
        'as_audio':           "🎵 As audio (mp3)",
        'as_video':           "🎬 As video (mp4)",
        'back':               "◀️ Back",
        'change':             "◀️ Change",
        'trim_done':          "✅ <b>Done!</b>  ✂️ {s} → {e}\n📤 Sending...",
        'trim_error':         "⚠️ Failed to trim. Make sure ffmpeg is installed.",
        'file_not_found':     "❌ File not found, send video again",
        'trim_bad_format':    "❌ Wrong format.\n\nExample: <code>0:05 0:10</code> or <code>5 10</code>",
        'trim_bad_time':      "❌ End must be greater than start.",
        'trim_bad_time2':     "❌ Wrong time format. Example: <code>0:05 0:10</code>",
        'lib_title':          "🎵 <b>My library</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n",
        'lib_folders':        "📂 Folders: <b>{n}</b>\n\nChoose a folder:",
        'lib_empty':          "Library is empty.\nCreate a folder and add tracks!",
        'lib_new_folder':     "➕ Create folder",
        'lib_folder_empty':   "Folder is empty.\n\nAfter downloading a track press\n<b>📁 Save to library</b>",
        'lib_tracks':         "Tracks: <b>{n}</b>\n\nTap a track — I'll send it:",
        'lib_del_folder':     "🗑 Delete folder",
        'lib_save_btn':       "📁 Save to library",
        'lib_saved':          "✅ Saved to <b>{folder}</b>",
        'lib_duplicate':      "⚠️ This track is already in the folder.",
        'lib_no_folders':     "❌ No folders. Create one in /library first",
        'lib_ask_folder':     "📁 Which folder to save to?",
        'lib_ask_name':       "📁 Write a name for the new folder:",
        'lib_created':        "✅ Folder <b>«{name}»</b> created!\n\nNow download a track and press <b>📁 Save to library</b>",
        'lib_name_too_long':  "❌ Name is too long (max 50 characters).",
        'search_prefix':      'find ',
        'trim_prefix':        'trim ',
        'similar':            "🔀 Similar",
        'by_artist':          "🎤 More by artist",
        'download_full':      "⬇️ Download full version",
        'language_cmd':       "🌐 Choose language:",
    }
}

# ── Настройки ─────────────────────────────────────────────────────────────────
TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

TEMP_DIR = "/tmp/musicbot"
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=8)
cache: dict = {}
CACHE_MAX = 30
_url_store: dict = {}
_trim_state: dict = {}
_user_state: dict = {}  # {user_id: {'action': 'create_folder'|'choose_folder', ...}}

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
def get_cookie_opts():
    for path in ['cookies.txt', '/app/cookies.txt', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')]:
        if os.path.exists(path):
            return {'cookiefile': path}
    return {}

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

# ── Библиотека (SQLite) ───────────────────────────────────────────────────────
import psycopg2
from psycopg2.extras import RealDictCursor

# ── База данных (PostgreSQL / Supabase) ───────────────────────────────────────
DB_URL = "postgresql://postgres.yhxxgohuznubzaqebiyu:.rep.1417228@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def _db():
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id SERIAL PRIMARY KEY,
            uid BIGINT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(uid, name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id SERIAL PRIMARY KEY,
            folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
            title TEXT, artist TEXT, duration INTEGER, file_id TEXT,
            UNIQUE(folder_id, file_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid BIGINT PRIMARY KEY,
            lang TEXT NOT NULL DEFAULT 'ru'
        )
    """)
    con.commit()
    return con

# Кэш языков чтобы не дёргать БД на каждое сообщение
_lang_cache: dict = {}

def get_lang(uid: int) -> str:
    if uid in _lang_cache: return _lang_cache[uid]
    try:
        con = _db()
        cur = con.cursor()
        cur.execute("SELECT lang FROM users WHERE uid=%s", (uid,))
        row = cur.fetchone()
        con.close()
        lang = row[0] if row else 'ru'
        _lang_cache[uid] = lang
        return lang
    except: return 'ru'

def set_lang(uid: int, lang: str):
    _lang_cache[uid] = lang
    try:
        con = _db()
        cur = con.cursor()
        cur.execute("INSERT INTO users (uid, lang) VALUES (%s,%s) ON CONFLICT (uid) DO UPDATE SET lang=%s", (uid, lang, lang))
        con.commit()
        con.close()
    except: pass

def t(uid: int, key: str, **kwargs) -> str:
    """Получить перевод строки для пользователя."""
    lang = get_lang(uid)
    s = STRINGS.get(lang, STRINGS['ru']).get(key, STRINGS['ru'].get(key, key))
    return s.format(**kwargs) if kwargs else s

def lib_get_user(uid: int) -> dict:
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM folders WHERE uid=%s ORDER BY id", (uid,))
        folders = cur.fetchall()
        result = {}
        for fid, fname in folders:
            cur.execute(
                "SELECT title, artist, duration, file_id FROM tracks WHERE folder_id=%s ORDER BY id",
                (fid,)
            )
            result[fname] = [
                {'title': t[0], 'artist': t[1], 'duration': t[2], 'file_id': t[3]}
                for t in cur.fetchall()
            ]
        return result
    finally:
        con.close()

def lib_create_folder(uid: int, folder: str):
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("INSERT INTO folders (uid, name) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, folder))
        con.commit()
    finally:
        con.close()

def lib_add_track(uid: int, folder: str, track: dict) -> bool:
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id FROM folders WHERE uid=%s AND name=%s", (uid, folder))
        row = cur.fetchone()
        if not row: return False
        fid = row[0]
        cur.execute(
            "INSERT INTO tracks (folder_id, title, artist, duration, file_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (fid, track.get('title',''), track.get('artist',''), track.get('duration',0), track.get('file_id',''))
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()

def lib_delete_folder(uid: int, folder: str):
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM folders WHERE uid=%s AND name=%s", (uid, folder))
        con.commit()
    finally:
        con.close()

def lib_delete_track(uid: int, folder: str, track_idx: int):
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id FROM folders WHERE uid=%s AND name=%s", (uid, folder))
        row = cur.fetchone()
        if not row: return
        fid = row[0]
        cur.execute("SELECT id FROM tracks WHERE folder_id=%s ORDER BY id", (fid,))
        tracks = cur.fetchall()
        if 0 <= track_idx < len(tracks):
            cur.execute("DELETE FROM tracks WHERE id=%s", (tracks[track_idx][0],))
            con.commit()
    finally:
        con.close()

# ── Отображение библиотеки ────────────────────────────────────────────────────

async def show_library(update_or_query, uid: int, edit=False):
    """Показывает главный экран библиотеки со списком папок."""
    folders = lib_get_user(uid)
    buttons = []

    if folders:
        for fname in folders:
            count = len(folders[fname])
            buttons.append([InlineKeyboardButton(
                f"📁 {fname}  ({count} тр.)",
                callback_data=f"lib_folder|{store_url(fname)}"
            )])
    else:
        pass  # покажем пустое состояние

    buttons.append([InlineKeyboardButton(t(uid, 'lib_new_folder'), callback_data="lib_new_folder")])

    text = t(uid, 'lib_title')
    if folders:
        text += t(uid, 'lib_folders', n=len(folders))
    else:
        text += t(uid, 'lib_empty')

    kb = InlineKeyboardMarkup(buttons)

    if edit:
        try:
            await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass
    else:
        await update_or_query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def show_folder(query, uid: int, folder: str):
    """Показывает содержимое папки."""
    folders = lib_get_user(uid)
    tracks = folders.get(folder, [])
    buttons = []

    for i, tr in enumerate(tracks):
        dur = fmt_dur(tr.get('duration', 0))
        label = f"🎵 {tr['title'][:28]}  {dur}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"lib_play|{store_url(folder)}|{i}"),
            InlineKeyboardButton("🗑", callback_data=f"lib_del_track|{store_url(folder)}|{i}"),
        ])

    buttons.append([
        InlineKeyboardButton(t(uid, 'lib_del_folder'), callback_data=f"lib_del_folder|{store_url(folder)}"),
        InlineKeyboardButton(t(uid, 'back'), callback_data="lib_back"),
    ])

    text = f"📁 <b>{folder}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    if tracks:
        text += t(uid, 'lib_tracks', n=len(tracks))
    else:
        text += t(uid, 'lib_folder_empty')

    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except:
        pass

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

# Логируем где нашли куки
_cookie_paths = ['cookies.txt', '/app/cookies.txt', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')]
_found_cookie = next((p for p in _cookie_paths if os.path.exists(p)), None)
log.info(f"cookies.txt: {_found_cookie or 'NOT FOUND — YouTube may block requests'}")

# Ищем ffmpeg: сначала imageio-ffmpeg, потом системный
try:
    import imageio_ffmpeg as _iff
    import shutil
    _ffmpeg_bin = _iff.get_ffmpeg_exe()
    # Копируем ffmpeg и ffprobe в /tmp где есть права на запись
    _tmp_ffmpeg = '/tmp/ffmpeg'
    _tmp_ffprobe = '/tmp/ffprobe'
    if not os.path.exists(_tmp_ffmpeg):
        shutil.copy2(_ffmpeg_bin, _tmp_ffmpeg)
        os.chmod(_tmp_ffmpeg, 0o755)
    if not os.path.exists(_tmp_ffprobe):
        shutil.copy2(_ffmpeg_bin, _tmp_ffprobe)
        os.chmod(_tmp_ffprobe, 0o755)
    BASE_OPTS['ffmpeg_location'] = '/tmp'
    os.environ['PATH'] = '/tmp:' + os.environ.get('PATH', '')
    log.info(f"ffmpeg ready at /tmp, ffprobe exists: {os.path.exists(_tmp_ffprobe)}")
except Exception as _ex:
    log.warning(f"imageio_ffmpeg not found: {_ex}")


# ── Скачивание ────────────────────────────────────────────────────────────────
def _get_spotify_query(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', ''); artist = info.get('artist') or info.get('uploader', '')
            return f"{artist} {title}".strip() or None
    except: return None

def _get_track_meta(url):
    try:
        opts = {**BASE_OPTS, **get_cookie_opts(), 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            e = info['entries'][0] if 'entries' in info else info
            # TikTok специфичные поля — самые точные
            music_track  = e.get('track') or e.get('music_track') or e.get('music_title') or ''
            music_artist = e.get('artist') or e.get('music_author') or e.get('creator') or e.get('uploader', '')
            vtitle = e.get('title', '')
            # Если есть музыкальные метаданные — используем их
            if music_track and music_artist and 'originalton' not in music_track.lower() and 'original sound' not in music_track.lower():
                return {
                    'title': clean_q(music_track),
                    'artist': clean_q(music_artist),
                    'query': f"{clean_q(music_artist)} {clean_q(music_track)}".strip(),
                    'video_title': vtitle
                }
            # Фолбэк на заголовок видео
            if vtitle and 'originalton' not in vtitle.lower():
                return {
                    'title': clean_q(vtitle),
                    'artist': clean_q(music_artist),
                    'query': clean_q(vtitle).strip(),
                    'video_title': vtitle
                }
    except Exception as ex: log.warning(f"_get_track_meta: {ex}")
    return None

def _get_video_title(url):
    try:
        opts = {**BASE_OPTS, **get_cookie_opts(), 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            e = info['entries'][0] if 'entries' in info else info
            return e.get('title', '')
    except: return ''

def _ffmpeg_to_wav(input_file, output_file):
    """Конвертирует аудио в wav через ffmpeg для Shazam"""
    try:
        import imageio_ffmpeg as _iff
        import subprocess
        ffmpeg = '/tmp/ffmpeg'
        if not os.path.exists(ffmpeg):
            ffmpeg = _iff.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, '-y', '-i', input_file, '-t', '30', '-ar', '44100', '-ac', '1', '-f', 'wav', output_file],
            capture_output=True, timeout=30, check=False
        )
        return os.path.exists(output_file) and os.path.getsize(output_file) > 0
    except Exception as ex:
        log.warning(f"_ffmpeg_to_wav: {ex}")
        return False

def _shazam_identify_tiktok(tiktok_url):
    import asyncio as _a, glob, uuid
    uid_str = uuid.uuid4().hex[:12]
    base = tmpfile(f'shazam_tt_{uid_str}')
    opts = {
        **BASE_OPTS, **get_cookie_opts(), 'format': 'bestaudio/best',
        'outtmpl': f'{base}.%(ext)s',
    }
    tmp = None
    wav = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.extract_info(tiktok_url, download=True)
        files = glob.glob(f'{base}.*')
        if not files: return None
        tmp = files[0]
        if not os.path.exists(tmp): return None
        # Конвертируем в wav для надёжного распознавания Shazam
        wav = f'{base}_shazam.wav'
        shazam_input = wav if _ffmpeg_to_wav(tmp, wav) else tmp
        loop = _a.new_event_loop()
        try:
            shazam = Shazam()
            result = loop.run_until_complete(shazam.recognize(shazam_input))
        finally: loop.close()
        if not result.get('matches'): return None
        track = result.get('track', {})
        title = track.get('title', ''); artist = track.get('subtitle', '')
        return f"{artist} {title}".strip() if title else None
    except Exception as ex: log.warning(f"_shazam_tiktok: {ex}")
    finally:
        for _cleanup in [tmp, wav]:
            if _cleanup and os.path.exists(_cleanup):
                try: os.remove(_cleanup)
                except: pass
    return None

def _download_audio(query_or_url):
    import glob, shutil, uuid
    # Уникальный ID на каждый вызов — никаких конфликтов файлов между параллельными запросами
    uid_str = uuid.uuid4().hex[:12]
    out = tmpfile(f'audio_{uid_str}')
    cookie_opts = get_cookie_opts()

    if is_spotify(query_or_url):
        sq = _get_spotify_query(query_or_url)
        sources = [f"scsearch:{sq}", f"ytsearch:{sq}"] if sq else []
    elif is_url(query_or_url):
        sources = [query_or_url]
    else:
        q = clean_q(query_or_url)
        sources = [f"scsearch:{q}", f"ytsearch:{q}"]

    for source in sources:
        # Чистим перед каждой попыткой чтобы не подобрать файл от предыдущего источника
        for _old in glob.glob(f'{out}.*'):
            try: os.remove(_old)
            except: pass

        log.info(f"_download_audio trying: {source}")
        is_sc = source.startswith('scsearch:')
        opts = {
            **BASE_OPTS,
            **(cookie_opts if not is_sc else {}),
            # Только аудио форматы, максимум 50MB
            'format': 'bestaudio[filesize<50M]/bestaudio/best[filesize<50M]',
            'outtmpl': f'{out}.%(ext)s',
            'ignoreerrors': True,
            'match_filter': yt_dlp.utils.match_filter_func('duration < 1800'),  # max 30 минут
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=True)

            if not info or not isinstance(info, dict):
                log.warning(f"_download_audio [{source}]: no info dict")
                continue

            entries = info.get('entries', None)
            if entries is not None:
                entries = [e for e in entries if e and isinstance(e, dict)]
                if not entries:
                    log.warning(f"_download_audio [{source}]: empty entries")
                    continue
                e = entries[0]
            else:
                e = info

            files = glob.glob(f'{out}.*')
            if not files:
                log.warning(f"_download_audio [{source}]: no file after download")
                continue

            file = files[0]
            if not file.endswith('.mp3'):
                new_file = f'{out}.mp3'
                shutil.move(file, new_file)
                file = new_file

            title = e.get('title') or query_or_url
            uploader = e.get('uploader') or e.get('channel') or e.get('uploader_id') or ''
            log.info(f"_download_audio OK: {title} | {uploader}")
            return {
                'type': 'audio', 'title': title,
                'duration': e.get('duration', 0) or 0,
                'uploader': uploader,
                'source': e.get('extractor', ''),
                'file': file
            }

        except Exception as ex:
            log.warning(f"_download_audio [{source}]: {ex}")
            for _old in glob.glob(f'{out}.*'):
                try: os.remove(_old)
                except: pass

    return None

def _download_video(url):
    import uuid
    uid_str = uuid.uuid4().hex[:12]
    out = tmpfile(f'video_{uid_str}')
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
    results = []
    for source in [f"scsearch{max_results}:{query}", f"ytsearch{max_results}:{query}"]:
        try:
            opts = {**BASE_OPTS, 'skip_download': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False)
                for e in info.get('entries', []):
                    if not e: continue
                    title = e.get('title', '')
                    url = e.get('url') or e.get('webpage_url', '')
                    dur = e.get('duration', 0) or 0
                    uploader = e.get('uploader', '') or e.get('channel', '')
                    if title and url:
                        results.append({'title': title, 'url': url, 'duration': dur, 'uploader': uploader})
                    if len(results) >= max_results: break
        except Exception as ex: log.warning(f"_search_similar: {ex}")
        if len(results) >= max_results: break
    seen = set(); unique = []
    for r in results:
        k = r['title'].lower()
        if k not in seen:
            seen.add(k); unique.append(r)
    return unique[:max_results]

def _extract_audio_for_shazam(video_path):
    out = video_path + '_shazam.mp3'
    ret = os.system(f'/tmp/ffmpeg -y -i "{video_path}" -t 30 -vn -ar 44100 -ac 2 -b:a 128k "{out}" -loglevel quiet')
    return out if ret == 0 and os.path.exists(out) else None

def _trim_audio(src, start_sec, end_sec):
    out = src.replace('.mp3', f'_trim_{start_sec}_{end_sec or "end"}.mp3')
    if end_sec is not None:
        cmd = f'/tmp/ffmpeg -y -i "{src}" -ss {start_sec} -t {end_sec - start_sec} -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
    else:
        cmd = f'/tmp/ffmpeg -y -i "{src}" -ss {start_sec} -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
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
# ── Команды ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name or "friend"
    # Если язык ещё не выбран — показываем выбор
    lang = get_lang(uid)
    if not _lang_cache.get(uid) and lang == 'ru':
        # Проверяем есть ли запись в БД
        try:
            con = _db()
            cur = con.cursor()
            cur.execute("SELECT lang FROM users WHERE uid=%s", (uid,))
            row = cur.fetchone()
            con.close()
            if not row:
                # Первый раз — показываем выбор языка
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang|ru"),
                    InlineKeyboardButton("🇬🇧 English", callback_data="setlang|en"),
                ]])
                await update.message.reply_text(STRINGS['ru']['choose_lang'], reply_markup=kb)
                return
        except: pass
    await update.message.reply_text(t(uid, 'welcome', name=name), parse_mode="HTML")

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang|ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="setlang|en"),
    ]])
    await update.message.reply_text(t(uid, 'language_cmd'), reply_markup=kb)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(t(uid, 'help'), parse_mode="HTML")

async def cmd_library(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await show_library(update, uid)

# ── Обработчик текста ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    loop = asyncio.get_event_loop()
    lower = text.lower()

    # ── Ожидаем название новой папки ─────────────────────────────────────────
    state = _user_state.get(uid, {})
    if state.get('action') == 'create_folder':
        folder_name = text.strip()
        if len(folder_name) > 50:
            await safe_reply(update, t(uid, 'lib_name_too_long'), parse_mode="HTML")
            return
        lib_create_folder(uid, folder_name)
        _user_state.pop(uid, None)
        await safe_reply(update, t(uid, 'lib_created', name=folder_name), parse_mode="HTML")
        await show_library(update, uid)
        return

    # ── Ожидаем время обрезки видео ──────────────────────────────────────────
    if state.get('action') == 'trim_input':
        vid_path = state.get('vid_path', '')
        vid_dur = state.get('vid_dur', 0)

        if not os.path.exists(vid_path):
            _user_state.pop(uid, None)
            await safe_reply(update, "❌ Файл не найден. Пришли видео заново.", parse_mode="HTML")
            return

        # Парсим ввод: "0:05 0:10" или "5 10"
        parts = text.strip().split()
        if len(parts) != 2:
            await safe_reply(update,
                "❌ Неверный формат.\n\nПример: <code>0:05 0:10</code> или <code>5 10</code>",
                parse_mode="HTML")
            return

        start_sec = parse_time(parts[0])
        end_raw = parts[1].lower()
        end_sec = None if end_raw in ('конец', 'end') else parse_time(end_raw)

        if start_sec is None:
            await safe_reply(update, "❌ Неверный формат времени. Пример: <code>0:05 0:10</code>", parse_mode="HTML")
            return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, "❌ Конец должен быть больше начала.", parse_mode="HTML")
            return
        if end_sec is not None and vid_dur and end_sec > vid_dur:
            end_sec = vid_dur

        s_str = fmt_dur(start_sec)
        e_str = fmt_dur(end_sec) if end_sec is not None else "конец"
        vid_key = store_url(vid_path)
        start_key = str(start_sec)
        end_key = str(end_sec) if end_sec is not None else 'end'

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t(uid, 'as_audio'), callback_data=f"vid_trim_fmt|{vid_key}|{start_key}|{end_key}|audio"),
                InlineKeyboardButton(t(uid, 'as_video'), callback_data=f"vid_trim_fmt|{vid_key}|{start_key}|{end_key}|video"),
            ],
            [InlineKeyboardButton(t(uid, 'change'), callback_data=f"vid_trim|{vid_key}")]
        ])

        await safe_reply(
            update,
            f"✂️ <b>Обрежу:</b> {s_str} → {e_str}\n\n"
            f"В каком формате отправить?",
            parse_mode="HTML",
            reply_markup=kb
        )
        return



    # ── Обрезка ───────────────────────────────────────────────────────────────
    m_range = re.match(r'^(обрезать|trim)\s+(\S+)\s+(\S+)\s*$', lower)
    m_to    = re.match(r'^(обрезать\s+до|trim\s+to)\s+(\S+)\s*$', lower)
    m_from  = re.match(r'^(обрезать\s+с|trim\s+from)\s+(\S+)\s*$', lower)

    if m_range or m_to or m_from:
        state = _trim_state.get(uid)
        if not state or not os.path.exists(state.get('file', '')):
            await safe_reply(update,
                "⚠️ No track to trim.\nDownload music first, then write:\n"
                "<code>trim 0:30 0:45</code>  /  <code>обрезать 0:30 0:45</code>", parse_mode="HTML")
            return
        if m_range:
            start_sec = parse_time(m_range.group(2))
            end_sec   = parse_time(m_range.group(3))
        elif m_to:
            start_sec = 0
            end_sec   = parse_time(m_to.group(2))
        else:
            start_sec = parse_time(m_from.group(2))
            end_sec   = None
        if start_sec is None:
            await safe_reply(update, t(uid, 'trim_bad_format'), parse_mode="HTML")
            return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, t(uid, 'trim_bad_time'), parse_mode="HTML")
            return
        msg = await safe_reply(update, "✂️ <b>Обрезаю...</b>", parse_mode="HTML")
        trimmed = await loop.run_in_executor(executor, _trim_audio, state['file'], start_sec, end_sec)
        if not trimmed:
            await safe_edit(msg, t(uid, 'trim_error'), parse_mode="HTML")
            return
        s_fmt = fmt_dur(start_sec)
        e_fmt = fmt_dur(end_sec) if end_sec else ("конец" if get_lang(uid) == 'ru' else "end")
        await safe_edit(msg, t(uid, 'trim_done', s=s_fmt, e=e_fmt), parse_mode="HTML")
        with open(trimmed, 'rb') as f:
            await update.message.reply_audio(f, title=f"{state['title']} [{s_fmt}-{e_fmt}]",
                                              performer=state.get('uploader', ''))
        try: await msg.delete()
        except: pass
        try: os.remove(trimmed)
        except: pass
        return

    # ── Музыка ────────────────────────────────────────────────────────────────
    url_match = is_url(text)
    search_match = lower.startswith("найти ") or lower.startswith("find ")
    if not url_match and not search_match: return

    # ── TikTok ────────────────────────────────────────────────────────────────
    if url_match and is_tiktok(text):
        msg = await safe_reply(update, t(uid, 'processing'), parse_mode="HTML")
        if not msg: return
        resolved = await loop.run_in_executor(executor, resolve_url, text)
        tiktok_url = resolved if 'tiktok.com' in resolved else text

        # Параллельно: Shazam + метаданные TikTok
        await safe_edit(msg, t(uid, 'searching_track'), parse_mode="HTML")
        try:
            shazam_q = await asyncio.wait_for(
                loop.run_in_executor(executor, _shazam_identify_tiktok, tiktok_url), timeout=45)
        except asyncio.TimeoutError: shazam_q = None

        try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, tiktok_url), timeout=20)
        except: meta = None

        vid_key = store_url(tiktok_url)

        def _build_kb(row1_buttons, extra_rows=None):
            rows = [row1_buttons]
            if extra_rows:
                rows.extend(extra_rows)
            return InlineKeyboardMarkup(rows)

        if shazam_q:
            aud_key = store_url(shazam_q)
            track_line = f"\n\n🎵 <b>{shazam_q}</b>"
            extra = []
            # Если метаданные TikTok отличаются от Shazam — предлагаем альтернативу
            if meta and meta.get('query') and meta['query'].lower() != shazam_q.lower():
                alt_key = store_url(meta['query'])
                extra.append([InlineKeyboardButton(f"🔄 {meta['artist']} — {meta['title']}", callback_data=f"audio|{alt_key}")])
            kb = _build_kb([
                InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"),
                InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"),
            ], extra)
        elif meta and meta.get('query'):
            aud_key = store_url(meta['query'])
            track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
            kb = _build_kb([
                InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"),
                InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"),
            ])
        else:
            track_line = ""
            kb = _build_kb([
                InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{vid_key}"),
                InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"),
            ])
        await safe_edit(msg, f"📱 <b>TikTok</b>{track_line}\n\n━━━━━━━━━━━━━━━━━━━━━━\n{t(uid, 'choose_action')}",
                        parse_mode="HTML", reply_markup=kb)
        return

    # ── Pinterest ─────────────────────────────────────────────────────────────
    if url_match and is_pinterest(text):
        msg = await safe_reply(update, t(uid, 'processing'), parse_mode="HTML")
        if not msg: return
        try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, text), timeout=30)
        except: meta = None
        vid_key = store_url(text); buttons = []; track_line = ""
        if meta and meta.get('query'):
            track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
            buttons.append(InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{store_url(meta['query'])}"))
        buttons.append(InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"))
        rows = [buttons]
        await safe_edit(msg, f"📌 <b>Pinterest</b>{track_line}\n\n━━━━━━━━━━━━━━━━━━━━━━\nВыбери действие:",
                        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
        return

    # ── YouTube / SoundCloud / Spotify / поиск ────────────────────────────────
    if search_match:
        if lower.startswith("найти "):
            query = text[6:].strip()
        else:
            query = text[5:].strip()  # "find "
    else:
        query = text
    ck = cache_key(query)
    if ck in cache:
        if await _send_cached(update, cache[ck]): return
        del cache[ck]

    display = "по ссылке" if url_match else f"«<b>{query}</b>»"
    msg = await safe_reply(update, f"🔍 Ищу {display}...", parse_mode="HTML")
    if not msg: return

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, _download_audio, query), timeout=90)
    except asyncio.TimeoutError:
        await safe_edit(msg, t(uid, 'timeout'), parse_mode="HTML"); return

    if not result or not os.path.exists(result.get('file', '')):
        await safe_edit(msg, t(uid, 'not_found'), parse_mode="HTML"); return

    try:
        title = result['title']
        uploader = result['uploader']
        similar_key = store_url(f"{uploader} {title}")
        artist_key  = store_url(uploader)
        save_key = store_url(json.dumps({'title': title, 'artist': uploader,
                                          'duration': result['duration']}, ensure_ascii=False))
        rows = [
            [
                InlineKeyboardButton(t(uid, 'similar'), callback_data=f"similar|{similar_key}"),
                InlineKeyboardButton(t(uid, 'by_artist'), callback_data=f"artist|{artist_key}"),
            ],
            [InlineKeyboardButton(t(uid, 'lib_save_btn'), callback_data=f"lib_save|{save_key}")],
        ]
        kb = InlineKeyboardMarkup(rows)

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
        sent = None
        with open(result['file'], 'rb') as f:
            from telegram import InputFile
            sent = await update.message.reply_audio(
                InputFile(f, filename='audio.mp3'),
                title=title, performer=uploader,
                caption=f"🎵 <b>{title}</b>\n👤 {uploader}  •  {src_emoji(result['source'])}\n⏱ {fmt_dur(result['duration'])}",
                parse_mode="HTML",
                reply_markup=kb)

        # Сохраняем file_id для библиотеки
        if sent and sent.audio:
            _trim_state[uid] = {
                'file': result['file'], 'title': title, 'uploader': uploader,
                'file_id': sent.audio.file_id, 'duration': result['duration']
            }

        # Удаляем временный файл
        try: os.remove(result['file'])
        except: pass

        save_cache(ck, result)
        try: await msg.delete()
        except: pass


    except Exception as ex:
        log.error(f"handle_message send: {ex}")
        await safe_edit(msg, f"⚠️ Ошибка: <code>{ex}</code>", parse_mode="HTML")

# ── Callback кнопок ───────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    await cb.answer()
    uid = update.effective_user.id
    data = cb.data
    loop = asyncio.get_event_loop()

    # ── Выбор языка ───────────────────────────────────────────────────────────
    if data.startswith("setlang|"):
        lang = data.split("|", 1)[1]
        set_lang(uid, lang)
        name = cb.from_user.first_name or "friend"
        try: await cb.delete_message()
        except: pass
        await cb.message.reply_text(t(uid, 'lang_set'), parse_mode="HTML")
        await cb.message.reply_text(t(uid, 'welcome', name=name), parse_mode="HTML")
        return
    if data.startswith("vid_shazam|"):
        vid_path = get_stored(data.split("|", 1)[1])
        if not os.path.exists(vid_path):
            await cb.answer(t(uid, 'file_not_found'), show_alert=True)
            return
        try:
            await cb.edit_message_text(t(uid, 'searching_track'), parse_mode="HTML")
        except: pass

        loop = asyncio.get_event_loop()
        aud_path = await loop.run_in_executor(executor, _extract_audio_for_shazam, vid_path)
        if not aud_path:
            try: await cb.edit_message_text("⚠️ ffmpeg не найден или ошибка извлечения аудио.", parse_mode="HTML")
            except: pass
            return

        try:
            track = await asyncio.wait_for(_recognize_shazam(aud_path), timeout=30)
        except asyncio.TimeoutError:
            track = None
        finally:
            if os.path.exists(aud_path):
                try: os.remove(aud_path)
                except: pass

        # Удаляем видеофайл
        if os.path.exists(vid_path):
            try: os.remove(vid_path)
            except: pass
        _user_state.pop(uid, None)

        if not track:
            # Shazam не нашёл — пробуем SoundCloud/YouTube по имени файла
            # Берём caption сообщения или имя файла как запрос
            state = _user_state.get(uid, {})
            fallback_query = state.get('vid_caption') or state.get('vid_filename') or ''
            fallback_query = fallback_query.strip()

            if fallback_query:
                try: await cb.edit_message_text(f"🔍 <b>Shazam не нашёл, ищу в SoundCloud/YouTube...</b>", parse_mode="HTML")
                except: pass

                loop2 = asyncio.get_event_loop()
                result = await loop2.run_in_executor(executor, _download_audio, fallback_query)

                if result and result.get('file') and os.path.exists(result['file']):
                    try: await cb.edit_message_text(f"📤 <b>Отправляю...</b>", parse_mode="HTML")
                    except: pass
                    title = result.get('title', '')
                    uploader = result.get('uploader', '')
                    q_key = store_url(fallback_query)
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton(t(uid, 'lib_save_btn'), callback_data=f"lib_save|{q_key}")
                    ]])
                    try:
                        from telegram import InputFile as _IF
                        with open(result['file'], 'rb') as fp:
                            await context.bot.send_audio(
                                chat_id=cb.message.chat_id,
                                audio=_IF(fp, filename='audio.mp3'),
                                title=title, performer=uploader,
                                caption=f"🎵 <b>{title}</b>\n👤 {uploader}",
                                parse_mode="HTML", reply_markup=kb
                            )
                        try: await cb.message.delete()
                        except: pass
                    except Exception as ex:
                        log.error(f"vid_shazam fallback send: {ex}")
                        try: await cb.edit_message_text("⚠️ Не удалось отправить файл.", parse_mode="HTML")
                        except: pass
                    finally:
                        try: os.remove(result['file'])
                        except: pass
                else:
                    try: await cb.edit_message_text(t(uid, 'track_not_found'), parse_mode="HTML")
                    except: pass
            else:
                try: await cb.edit_message_text(t(uid, 'track_not_found'), parse_mode="HTML")
                except: pass
            return

        q_key = store_url(track['query'])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(uid, 'download_full'), callback_data=f"audio|{q_key}")
        ]])
        try:
            await cb.edit_message_text(
                f"✅ <b>Трек определён!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎵 <b>{track['artist']} — {track['title']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML", reply_markup=kb
            )
        except: pass
        return

    if data.startswith("vid_trim|"):
        vid_path = get_stored(data.split("|", 1)[1])
        if not os.path.exists(vid_path):
            await cb.answer(t(uid, 'file_not_found'), show_alert=True)
            return

        state = _user_state.get(uid, {})
        vid_dur = state.get('vid_dur', 0)
        dur_str = fmt_dur(vid_dur) if vid_dur else "?"

        _user_state[uid] = {
            'action': 'trim_input',
            'vid_path': vid_path,
            'vid_dur': vid_dur,
        }

        try:
            await cb.edit_message_text(
                f"✂️ <b>Обрезка видео</b>  ⏱ {dur_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Напиши время в формате:\n"
                f"<code>начало конец</code>\n\n"
                f"Примеры:\n"
                f"  <code>0:05 0:10</code> — с 5 по 10 секунду\n"
                f"  <code>5 10</code> — то же самое\n"
                f"  <code>0 5</code> — первые 5 секунд\n\n"
                f"Или просто <code>0 конец</code> — всё видео целиком",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(uid, 'back'), callback_data=f"vid_back|{store_url(vid_path)}")
                ]])
            )
        except: pass
        return

    if data.startswith("vid_back|"):
        vid_path = get_stored(data.split("|", 1)[1])
        state = _user_state.get(uid, {})
        vid_dur = state.get('vid_dur', 0)
        dur_str = fmt_dur(vid_dur) if vid_dur else "?"
        vid_key = store_url(vid_path)
        _user_state[uid] = {'action': 'video_menu', 'vid_path': vid_path, 'vid_dur': vid_dur}
        try:
            await cb.edit_message_text(
                f"🎬 <b>Видео</b>  ⏱ {dur_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\nЧто хочешь сделать?",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(uid, 'find_track'), callback_data=f"vid_shazam|{vid_key}"),
                    InlineKeyboardButton(t(uid, 'trim'), callback_data=f"vid_trim|{vid_key}"),
                ]])
            )
        except: pass
        return

    if data.startswith("vid_trim_fmt|"):
        # vid_trim_fmt|vid_key|start|end|format  (audio/video)
        parts = data.split("|")
        vid_path = get_stored(parts[1])
        start_sec = int(parts[2])
        end_sec = int(parts[3]) if parts[3] != 'end' else None
        fmt = parts[4]  # 'audio' or 'video'

        if not os.path.exists(vid_path):
            await cb.answer("❌ Файл не найден", show_alert=True)
            return

        try: await cb.edit_message_text(f"✂️ <b>Обрезаю и конвертирую...</b>", parse_mode="HTML")
        except: pass

        loop = asyncio.get_event_loop()

        def _do_trim():
            s = start_sec
            e = end_sec
            dur_arg = f"-t {e - s}" if e is not None else ""
            if fmt == 'audio':
                out = tmpfile(f"trim_{uid}_{s}_{e or 'end'}.mp3")
                cmd = f'/tmp/ffmpeg -y -i "{vid_path}" -ss {s} {dur_arg} -vn -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
            else:
                out = tmpfile(f"trim_{uid}_{s}_{e or 'end'}.mp4")
                cmd = f'/tmp/ffmpeg -y -i "{vid_path}" -ss {s} {dur_arg} -c:v libx264 -c:a aac -preset fast "{out}" -loglevel quiet'
            ret = os.system(cmd)
            return out if ret == 0 and os.path.exists(out) else None

        out_path = await loop.run_in_executor(executor, _do_trim)

        # Удаляем исходное видео
        if os.path.exists(vid_path):
            try: os.remove(vid_path)
            except: pass
        _user_state.pop(uid, None)

        if not out_path:
            try: await cb.edit_message_text(t(uid, 'trim_error'), parse_mode="HTML")
            except: pass
            return

        s_str = fmt_dur(start_sec)
        e_str = fmt_dur(end_sec) if end_sec is not None else "конец"

        try:
            await cb.edit_message_text(
                f"✅ <b>Готово!</b>  ✂️ {s_str} → {e_str}\n📤 Отправляю...",
                parse_mode="HTML"
            )
        except: pass

        try:
            with open(out_path, 'rb') as f:
                if fmt == 'audio':
                    await cb.message.reply_audio(f, title=f"Обрезка {s_str}-{e_str}")
                else:
                    await cb.message.reply_video(f, caption=f"✂️ {s_str} → {e_str}")
        except Exception as ex:
            log.error(f"vid_trim send: {ex}")

        try: os.remove(out_path)
        except: pass
        try: await cb.delete_message()
        except: pass
        return

    # ── Библиотека ────────────────────────────────────────────────────────────
    if data == "lib_back":
        await show_library(cb, uid, edit=True)
        return

    if data == "lib_new_folder":
        _user_state[uid] = {'action': 'create_folder'}
        try:
            await cb.edit_message_text(
                "📁 <b>Создание папки</b>\n\n"
                "Напиши название новой папки:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="lib_back")
                ]])
            )
        except: pass
        return

    if data.startswith("lib_folder|"):
        folder = get_stored(data.split("|", 1)[1])
        await show_folder(cb, uid, folder)
        return

    if data.startswith("lib_play|"):
        _, folder_key, idx_str = data.split("|")
        folder = get_stored(folder_key)
        idx = int(idx_str)
        folders = lib_get_user(uid)
        tracks = folders.get(folder, [])
        if idx >= len(tracks):
            try: await cb.answer("Трек не найден", show_alert=True)
            except: pass
            return
        track = tracks[idx]
        try:
            await cb.answer("📤 Отправляю...")
            await cb.message.reply_audio(
                audio=track['file_id'],
                title=track['title'],
                performer=track.get('artist', '')
            )
        except Exception as ex:
            log.error(f"lib_play: {ex}")
            await cb.answer("❌ Не удалось отправить", show_alert=True)
        return

    if data.startswith("lib_del_track|"):
        _, folder_key, idx_str = data.split("|")
        folder = get_stored(folder_key)
        idx = int(idx_str)
        lib_delete_track(uid, folder, idx)
        await cb.answer("🗑 Удалено")
        await show_folder(cb, uid, folder)
        return

    if data.startswith("lib_del_folder|"):
        folder = get_stored(data.split("|", 1)[1])
        lib_delete_folder(uid, folder)
        await cb.answer(f"🗑 Папка удалена")
        await show_library(cb, uid, edit=True)
        return

    if data.startswith("lib_save|"):
        # Показываем список папок для выбора
        track_key = data.split("|", 1)[1]
        folders = lib_get_user(uid)
        if not folders:
            try:
                await cb.edit_message_text(
                    "📁 <b>У тебя нет папок</b>\n\nСначала создай папку через /library",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📁 Открыть библиотеку", callback_data="lib_back")
                    ]])
                )
            except: pass
            return

        buttons = []
        for fname in folders:
            count = len(folders[fname])
            fkey = store_url(fname)
            buttons.append([InlineKeyboardButton(
                f"📁 {fname} ({count} тр.)",
                callback_data=f"lib_save_to|{fkey}|{track_key}"
            )])
        buttons.append([InlineKeyboardButton("◀️ Отмена", callback_data="lib_cancel_save")])

        try:
            await cb.edit_message_text(
                "📁 <b>Выбери папку:</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except: pass
        return

    if data == "lib_cancel_save":
        try: await cb.delete_message()
        except: pass
        return

    if data.startswith("lib_save_to|"):
        _, folder_key, track_key = data.split("|")
        folder = get_stored(folder_key)
        track_meta_str = get_stored(track_key)

        # Получаем file_id из trim_state
        state = _trim_state.get(uid, {})
        file_id = state.get('file_id')

        if not file_id:
            await cb.answer("❌ file_id не найден. Скачай трек заново.", show_alert=True)
            return

        try:
            track_meta = json.loads(track_meta_str)
        except:
            track_meta = {'title': 'Неизвестно', 'artist': '', 'duration': 0}

        track = {
            'title': track_meta.get('title', 'Неизвестно'),
            'artist': track_meta.get('artist', ''),
            'duration': track_meta.get('duration', 0),
            'file_id': file_id,
        }

        added = lib_add_track(uid, folder, track)
        if added:
            await cb.answer(f"✅ Сохранено в «{folder}»")
        else:
            await cb.answer(f"ℹ️ Уже есть в папке «{folder}»")

        try: await cb.delete_message()
        except: pass
        return

    # ── Похожие треки / треки исполнителя ────────────────────────────────────
    if '|' not in data: return
    action, key = data.split('|', 1)
    value = get_stored(key)

    if action in ('similar', 'artist'):
        label = "похожие треки" if action == 'similar' else f"треки «{value}»"
        try: await cb.edit_message_text(f"🔍 Ищу {label}...", parse_mode="HTML")
        except: pass

        search_q = value if action == 'similar' else f"{value} best songs"
        tracks = await loop.run_in_executor(executor, _search_similar_tracks, search_q)

        if not tracks:
            try: await cb.edit_message_text("😔 Ничего не нашёл.")
            except: pass
            return

        buttons = []
        lines = []
        for i, tr in enumerate(tracks, 1):
            dur = fmt_dur(tr['duration']) if tr['duration'] else '?'
            lines.append(f"{i}. <b>{tr['title']}</b> — {tr['uploader']} ⏱{dur}")
            t_key = store_url(tr['url'])
            buttons.append([InlineKeyboardButton(f"⬇️ {i}. {tr['title'][:30]}", callback_data=f"audio|{t_key}")])

        header = "🔀 <b>Похожие треки:</b>" if action == 'similar' else f"🎤 <b>Треки исполнителя:</b>"
        text = header + "\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
        try:
            await cb.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as ex: log.warning(f"similar edit: {ex}")
        return

    # ── Скачать аудио / видео ─────────────────────────────────────────────────
    emoji = '🎵' if 'audio' in action else '🎬'
    try: await cb.edit_message_text(f"{emoji} <b>Загружаю...</b>", parse_mode="HTML")
    except: pass

    try:
        if action == 'video':
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _download_video, value), timeout=120)
        else:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _download_audio, value), timeout=90)
    except asyncio.TimeoutError:
        try: await cb.edit_message_text(t(uid, 'timeout'), parse_mode="HTML")
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
            similar_key = store_url(f"{uploader} {title}")
            artist_key  = store_url(uploader)
            save_key = store_url(json.dumps({'title': title, 'artist': uploader,
                                              'duration': result['duration']}, ensure_ascii=False))
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(t(uid, 'similar'), callback_data=f"similar|{similar_key}"),
                    InlineKeyboardButton(t(uid, 'by_artist'), callback_data=f"artist|{artist_key}"),
                ],
                [InlineKeyboardButton(t(uid, 'lib_save_btn'), callback_data=f"lib_save|{save_key}")],
            ])
            sent = None
            with open(result['file'], 'rb') as f:
                from telegram import InputFile
                sent = await cb.message.reply_audio(
                    InputFile(f, filename='audio.mp3'),
                    title=title, performer=uploader,
                    caption=f"🎵 <b>{title}</b>\n👤 {uploader}  •  {src_emoji(result['source'])}\n⏱ {fmt_dur(result['duration'])}",
                    parse_mode="HTML",
                    reply_markup=kb)

            if sent and sent.audio:
                _trim_state[uid] = {
                    'file': result['file'], 'title': title, 'uploader': uploader,
                    'file_id': sent.audio.file_id, 'duration': result['duration']
                }

            try: os.remove(result['file'])
            except: pass

        else:
            cap = f"🎬 <b>{result['title']}</b>"
            with open(result['file'], 'rb') as f:
                await cb.message.reply_video(f, caption=cap, parse_mode="HTML")
            try: os.remove(result['file'])
            except: pass

        try: await cb.delete_message()
        except: pass

    except Exception as ex:
        log.error(f"handle_callback send: {ex}")
        try: await cb.edit_message_text(f"❌ {ex}")
        except: pass

# ── Видеофайл → выбор действия ───────────────────────────────────────────────
async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.animation: return
    video = update.message.video or update.message.document
    if not video: return
    dur = getattr(video, 'duration', None)
    if dur is not None and dur == 0: return
    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(t(uid, 'file_too_big')); return

    uid = update.effective_user.id
    msg = await safe_reply(update, "⏳ <b>Получаю файл...</b>", parse_mode="HTML")
    if not msg: return

    vid_path = tmpfile(f"video_{uid}_{update.message.message_id}.mp4")

    try:
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(vid_path)
    except Exception as ex:
        log.error(f"handle_video_file download: {ex}")
        await safe_edit(msg, f"⚠️ Не удалось скачать файл.", parse_mode="HTML")
        return

    # Сохраняем путь к видео в состоянии пользователя
    vid_dur = getattr(video, 'duration', 0) or 0
    # Для fallback поиска если Shazam не найдёт
    vid_caption = update.message.caption or ''
    vid_filename = getattr(video, 'file_name', '') or ''
    # Убираем расширение из имени файла
    if vid_filename:
        vid_filename = os.path.splitext(vid_filename)[0]
    _user_state[uid] = {
        'action': 'video_menu',
        'vid_path': vid_path,
        'vid_dur': vid_dur,
        'vid_caption': vid_caption,
        'vid_filename': vid_filename,
    }

    vid_key = store_url(vid_path)
    dur_str = fmt_dur(vid_dur) if vid_dur else "?"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(uid, 'find_track'), callback_data=f"vid_shazam|{vid_key}"),
        InlineKeyboardButton(t(uid, 'trim'), callback_data=f"vid_trim|{vid_key}"),
    ]])

    await safe_edit(
        msg,
        f"🎬 <b>Видео получено</b>  ⏱ {dur_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Что хочешь сделать?",
        parse_mode="HTML",
        reply_markup=kb
    )

# ── Запуск ────────────────────────────────────────────────────────────────────

# Автоматически найти ffmpeg из imageio-ffmpeg если системный не найден
try:
    import imageio_ffmpeg
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ['PATH'] = os.path.dirname(ffmpeg_path) + os.pathsep + os.environ.get('PATH', '')
    log.info(f"ffmpeg найден: {ffmpeg_path}")
except Exception:
    pass

# Сбрасываем старую сессию при старте чтобы не было конфликта
try:
    import urllib.request as _ur
    _ur.urlopen(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
except Exception:
    pass
async def post_init(application):
    await application.bot.set_my_commands([
        ("start",    "🎵 Начать / Start"),
        ("library",  "📁 Библиотека / Library"),
        ("language", "🌐 Язык / Language"),
        ("help",     "📖 Помощь / Help"),
    ])

app = ApplicationBuilder().token(TOKEN).post_init(post_init).connect_timeout(30).read_timeout(60).write_timeout(120).build()
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("help", cmd_help))
app.add_handler(CommandHandler("library", cmd_library))
app.add_handler(CommandHandler("language", cmd_language))
app.add_handler(CallbackQueryHandler(handle_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler((filters.VIDEO | filters.Document.VIDEO) & ~filters.ANIMATION, handle_video_file))

log.info("Бот запущен ✅")
if not os.path.exists('cookies.txt'): log.warning("cookies.txt не найден.")

app.run_polling(drop_pending_updates=True)