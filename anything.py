import os, re, asyncio, hashlib, logging, unicodedata, urllib.request, urllib.parse, json
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
from shazamio import Shazam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import psycopg2

# ── Настройки ─────────────────────────────────────────────────────────────────
TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"
DB_URL = "postgresql://postgres.yhxxgohuznubzaqebiyu:.rep.1417228@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
TMDB_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJjZDBlZjI5NGIyYTIwZDllMmFjZmM3ZGI3NTIwYjBjMCIsIm5iZiI6MTc3MzI5NzMxMy4wNDYwMDAyLCJzdWIiOiI2OWIyNWVhMWQ5YWVlY2JjYjA2ODVhZjIiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.a9yQrtM93kLHa7LUnQViWKgvmIO_B-J2UKHBH0AFGeA"

TEMP_DIR = "/tmp/musicbot"
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=8)
_url_store: dict = {}
_url_store_counter = [0]
_trim_state: dict = {}
_user_state: dict = {}

URL_PATTERN = re.compile(
    r'https?://(www\.|vm\.|vt\.|api\.)?'
    r'(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com'
    r'|pin\.it|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

def is_url(tx): return bool(URL_PATTERN.search(tx)) or tx.startswith('https://') or tx.startswith('http://')

# ── Переводы ──────────────────────────────────────────────────────────────────
LANGS = {
    'ru': ('🇷🇺', 'Русский'),
    'en': ('🇬🇧', 'English'),
    'uz': ('🇺🇿', "O'zbek"),
    'ua': ('🇺🇦', 'Українська'),
    'ar': ('🇸🇦', 'العربية'),
    'tr': ('🇹🇷', 'Türkçe'),
}

T = {
    'welcome_new': {
        'ru': "👋 <b>Привет, {name}!</b>\n\nВыбери язык:",
        'en': "👋 <b>Hello, {name}!</b>\n\nChoose your language:",
        'uz': "👋 <b>Salom, {name}!</b>\n\nTilni tanlang:",
        'ua': "👋 <b>Привіт, {name}!</b>\n\nОберіть мову:",
        'ar': "👋 <b>مرحباً، {name}!</b>\n\nاختر لغتك:",
        'tr': "👋 <b>Merhaba, {name}!</b>\n\nDil seçin:",
    },
    'lang_set': {
        'ru': "✅ Язык: 🇷🇺 Русский",
        'en': "✅ Language: 🇬🇧 English",
        'uz': "✅ Til: 🇺🇿 O'zbek",
        'ua': "✅ Мова: 🇺🇦 Українська",
        'ar': "✅ اللغة: 🇸🇦 العربية",
        'tr': "✅ Dil: 🇹🇷 Türkçe",
    },
    'start_main': {
        'ru': (
            "🎵 <b>С возвращением, {name}!</b>\n\n"
            "🔗 Ссылка — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n"
            "🔍 Поиск: <code>найти The Weeknd Blinding Lights</code>\n"
            "✂️ Обрезка: <code>обрезать 0:30 0:45</code>\n"
            "📁 Библиотека — /library\n"
            "🎬 Распознать трек — пришли видео до 20MB\n"
            "🌐 Язык — /lang"
        ),
        'en': (
            "🎵 <b>Welcome back, {name}!</b>\n\n"
            "🔗 Link — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n"
            "🔍 Search: <code>find The Weeknd Blinding Lights</code>\n"
            "✂️ Trim: <code>trim 0:30 0:45</code>\n"
            "📁 Library — /library\n"
            "🎬 Recognize track — send video up to 20MB\n"
            "🌐 Language — /lang"
        ),
        'uz': (
            "🎵 <b>Xush kelibsiz, {name}!</b>\n\n"
            "🔗 Havola — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n"
            "🔍 Qidirish: <code>topish The Weeknd Blinding Lights</code>\n"
            "✂️ Kesish: <code>kesish 0:30 0:45</code>\n"
            "📁 Kutubxona — /library\n"
            "🎬 Trekni aniqlash — 20MB gacha video yuboring\n"
            "🌐 Til — /lang"
        ),
        'ua': (
            "🎵 <b>З поверненням, {name}!</b>\n\n"
            "🔗 Посилання — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n"
            "🔍 Пошук: <code>знайти The Weeknd Blinding Lights</code>\n"
            "✂️ Обрізка: <code>обрізати 0:30 0:45</code>\n"
            "📁 Бібліотека — /library\n"
            "🎬 Розпізнати трек — надішли відео до 20MB\n"
            "🌐 Мова — /lang"
        ),
        'ar': (
            "🎵 <b>مرحباً بعودتك، {name}!</b>\n\n"
            "🔗 رابط — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n"
            "🔍 بحث: <code>ابحث The Weeknd Blinding Lights</code>\n"
            "✂️ قص: <code>قص 0:30 0:45</code>\n"
            "📁 المكتبة — /library\n"
            "🎬 التعرف على الأغنية — أرسل فيديو حتى 20MB\n"
            "🌐 اللغة — /lang"
        ),
        'tr': (
            "🎵 <b>Tekrar hoş geldin, {name}!</b>\n\n"
            "🔗 Bağlantı — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n"
            "🔍 Arama: <code>bul The Weeknd Blinding Lights</code>\n"
            "✂️ Kırp: <code>kırp 0:30 0:45</code>\n"
            "📁 Kütüphane — /library\n"
            "🎬 Parçayı tanı — 20MB'a kadar video gönder\n"
            "🌐 Dil — /lang"
        ),
    },
    'not_found': {
        'ru': '😔 Ничего не найдено. Попробуй уточнить запрос.',
        'en': '😔 Nothing found. Try a more specific query.',
        'uz': "😔 Hech narsa topilmadi. So'rovni aniqlashtiring.",
        'ua': '😔 Нічого не знайдено. Спробуй уточнити запит.',
        'ar': '😔 لم يتم العثور على شيء.',
        'tr': '😔 Hiçbir şey bulunamadı.',
    },
    'timeout': {
        'ru': '⚠️ Превышено время ожидания. Попробуй ещё раз.',
        'en': '⚠️ Request timed out. Please try again.',
        'uz': "⚠️ Vaqt tugadi. Qayta urinib ko'ring.",
        'ua': '⚠️ Час очікування вичерпано. Спробуй ще раз.',
        'ar': '⚠️ انتهت مهلة الطلب.',
        'tr': '⚠️ İstek zaman aşımına uğradı.',
    },
    'processing': {
        'ru': '⏳ <b>Обрабатываю...</b>',
        'en': '⏳ <b>Processing...</b>',
        'uz': '⏳ <b>Ishlanmoqda...</b>',
        'ua': '⏳ <b>Обробляю...</b>',
        'ar': '⏳ <b>جاري المعالجة...</b>',
        'tr': '⏳ <b>İşleniyor...</b>',
    },
    'shazam_detecting': {
        'ru': '🎵 <b>Определяю трек...</b>',
        'en': '🎵 <b>Detecting track...</b>',
        'uz': '🎵 <b>Trek aniqlanmoqda...</b>',
        'ua': '🎵 <b>Визначаю трек...</b>',
        'ar': '🎵 <b>جاري التعرف على الأغنية...</b>',
        'tr': '🎵 <b>Parça tespit ediliyor...</b>',
    },
    'choose_format': {
        'ru': 'Выбери формат:',
        'en': 'Choose format:',
        'uz': 'Formatni tanlang:',
        'ua': 'Обери формат:',
        'ar': 'اختر التنسيق:',
        'tr': 'Format seçin:',
    },
    'btn_save_lib': {
        'ru': '📁 Сохранить в библиотеку',
        'en': '📁 Save to library',
        'uz': '📁 Kutubxonaga saqlash',
        'ua': '📁 Зберегти до бібліотеки',
        'ar': '📁 حفظ في المكتبة',
        'tr': '📁 Kütüphaneye kaydet',
    },
    'trim_no_track': {
        'ru': '⚠️ Нет трека для обрезки. Сначала скачай музыку.',
        'en': '⚠️ No track to trim. Download a track first.',
        'uz': "⚠️ Kesish uchun trek yo'q.",
        'ua': '⚠️ Немає треку для обрізки.',
        'ar': '⚠️ لا يوجد مقطع للقص.',
        'tr': '⚠️ Kırpılacak parça yok.',
    },
    'trimming': {
        'ru': '✂️ <b>Обрезаю...</b>',
        'en': '✂️ <b>Trimming...</b>',
        'uz': '✂️ <b>Kesilmoqda...</b>',
        'ua': '✂️ <b>Обрізаю...</b>',
        'ar': '✂️ <b>جاري القص...</b>',
        'tr': '✂️ <b>Kırpılıyor...</b>',
    },
    'trim_done': {
        'ru': '✅ Готово! ⏱ {s} → {e}\n📤 Отправляю...',
        'en': '✅ Done! ⏱ {s} → {e}\n📤 Sending...',
        'uz': '✅ Tayyor! ⏱ {s} → {e}',
        'ua': '✅ Готово! ⏱ {s} → {e}',
        'ar': '✅ تم! ⏱ {s} → {e}',
        'tr': '✅ Bitti! ⏱ {s} → {e}',
    },
    'lib_title': {
        'ru': '🎵 <b>Моя библиотека</b>\n\n',
        'en': '🎵 <b>My Library</b>\n\n',
        'uz': '🎵 <b>Mening kutubxonam</b>\n\n',
        'ua': '🎵 <b>Моя бібліотека</b>\n\n',
        'ar': '🎵 <b>مكتبتي</b>\n\n',
        'tr': '🎵 <b>Kütüphanem</b>\n\n',
    },
    'lib_empty': {
        'ru': 'Библиотека пуста.\nСоздай папку и добавляй треки!',
        'en': 'Library is empty.\nCreate a folder and add tracks!',
        'uz': "Kutubxona bo'sh.",
        'ua': 'Бібліотека порожня.',
        'ar': 'المكتبة فارغة.',
        'tr': 'Kütüphane boş.',
    },
    'lib_folders_count': {
        'ru': '📂 Папок: <b>{n}</b>\n\nВыбери папку:',
        'en': '📂 Folders: <b>{n}</b>\n\nChoose a folder:',
        'uz': '📂 Papkalar: <b>{n}</b>',
        'ua': '📂 Папок: <b>{n}</b>',
        'ar': '📂 المجلدات: <b>{n}</b>',
        'tr': '📂 Klasörler: <b>{n}</b>',
    },
    'btn_new_folder': {
        'ru': '➕ Создать папку',
        'en': '➕ Create folder',
        'uz': '➕ Papka yaratish',
        'ua': '➕ Створити папку',
        'ar': '➕ إنشاء مجلد',
        'tr': '➕ Klasör oluştur',
    },
    'btn_back': {
        'ru': '◀️ Назад',
        'en': '◀️ Back',
        'uz': '◀️ Orqaga',
        'ua': '◀️ Назад',
        'ar': '◀️ رجوع',
        'tr': '◀️ Geri',
    },
    'create_folder_prompt': {
        'ru': '📁 <b>Создание папки</b>\n\nНапиши название:',
        'en': '📁 <b>Create folder</b>\n\nEnter the name:',
        'uz': '📁 <b>Papka yaratish</b>\n\nNomini kiriting:',
        'ua': '📁 <b>Створення папки</b>\n\nНапиши назву:',
        'ar': '📁 <b>إنشاء مجلد</b>\n\nأدخل الاسم:',
        'tr': '📁 <b>Klasör oluştur</b>\n\nAdı girin:',
    },
    'folder_created': {
        'ru': '✅ Папка <b>«{name}»</b> создана!',
        'en': '✅ Folder <b>«{name}»</b> created!',
        'uz': '✅ <b>«{name}»</b> papkasi yaratildi!',
        'ua': '✅ Папку <b>«{name}»</b> створено!',
        'ar': '✅ تم إنشاء المجلد <b>«{name}»</b>!',
        'tr': '✅ <b>«{name}»</b> klasörü oluşturuldu!',
    },
    'video_received': {
        'ru': '🎬 <b>Видео получено</b>  ⏱ {dur}\n\nЧто хочешь сделать?',
        'en': '🎬 <b>Video received</b>  ⏱ {dur}\n\nWhat do you want to do?',
        'uz': '🎬 <b>Video qabul qilindi</b>  ⏱ {dur}',
        'ua': '🎬 <b>Відео отримано</b>  ⏱ {dur}',
        'ar': '🎬 <b>تم استلام الفيديو</b>  ⏱ {dur}',
        'tr': '🎬 <b>Video alındı</b>  ⏱ {dur}',
    },
    'btn_find_track': {
        'ru': '🔍 Найти трек',
        'en': '🔍 Find track',
        'uz': '🔍 Trek topish',
        'ua': '🔍 Знайти трек',
        'ar': '🔍 البحث عن الأغنية',
        'tr': '🔍 Parça bul',
    },
    'btn_trim_video': {
        'ru': '✂️ Обрезать',
        'en': '✂️ Trim',
        'uz': '✂️ Kesish',
        'ua': '✂️ Обрізати',
        'ar': '✂️ قص',
        'tr': '✂️ Kırp',
    },
    'track_detected': {
        'ru': '✅ <b>Трек определён!</b>\n\n🎵 <b>{artist} — {title}</b>',
        'en': '✅ <b>Track detected!</b>\n\n🎵 <b>{artist} — {title}</b>',
        'uz': '✅ <b>Trek aniqlandi!</b>\n\n🎵 <b>{artist} — {title}</b>',
        'ua': '✅ <b>Трек визначено!</b>\n\n🎵 <b>{artist} — {title}</b>',
        'ar': '✅ <b>تم التعرف!</b>\n\n🎵 <b>{artist} — {title}</b>',
        'tr': '✅ <b>Parça tespit edildi!</b>\n\n🎵 <b>{artist} — {title}</b>',
    },
    'btn_download_full': {
        'ru': '⬇️ Скачать',
        'en': '⬇️ Download',
        'uz': '⬇️ Yuklab olish',
        'ua': '⬇️ Завантажити',
        'ar': '⬇️ تنزيل',
        'tr': '⬇️ İndir',
    },
    'track_not_recognized': {
        'ru': '😔 <b>Трек не распознан</b>\n\nПопробуй видео с более чёткой музыкой.',
        'en': '😔 <b>Track not recognized</b>\n\nTry a video with clearer music.',
        'uz': '😔 <b>Trek aniqlanmadi</b>',
        'ua': '😔 <b>Трек не розпізнано</b>',
        'ar': '😔 <b>لم يتم التعرف على الأغنية</b>',
        'tr': '😔 <b>Parça tanınamadı</b>',
    },
    'choose_lang': {
        'ru': '🌐 <b>Выбери язык:</b>',
        'en': '🌐 <b>Choose language:</b>',
        'uz': '🌐 <b>Tilni tanlang:</b>',
        'ua': '🌐 <b>Оберіть мову:</b>',
        'ar': '🌐 <b>اختر اللغة:</b>',
        'tr': '🌐 <b>Dil seçin:</b>',
    },
    'search_keyword': {
        'ru': 'найти ',
        'en': 'find ',
        'uz': 'topish ',
        'ua': 'знайти ',
        'ar': 'ابحث ',
        'tr': 'bul ',
    },
    'trim_keyword': {
        'ru': 'обрезать',
        'en': 'trim',
        'uz': 'kesish',
        'ua': 'обрізати',
        'ar': 'قص',
        'tr': 'kırp',
    },
}

def t(key, lang, **kwargs):
    text = T.get(key, {}).get(lang) or T.get(key, {}).get('ru', '')
    if kwargs:
        try: text = text.format(**kwargs)
        except: pass
    return text

# ── База данных ───────────────────────────────────────────────────────────────
def _db():
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid BIGINT PRIMARY KEY,
            lang TEXT DEFAULT 'ru',
            is_new BOOLEAN DEFAULT TRUE
        )
    """)
    # Добавляем is_new если колонки нет (миграция старой БД)
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_new BOOLEAN DEFAULT TRUE
    """)
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
    con.commit()
    return con

def db_get_user(uid: int) -> dict:
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("SELECT lang, is_new FROM users WHERE uid=%s", (uid,))
        row = cur.fetchone()
        if row: return {'lang': row[0], 'is_new': row[1]}
        return {'lang': None, 'is_new': True}
    finally:
        con.close()

def db_set_lang(uid: int, lang: str):
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO users (uid, lang, is_new) VALUES (%s, %s, FALSE)
            ON CONFLICT (uid) DO UPDATE SET lang=EXCLUDED.lang, is_new=FALSE
        """, (uid, lang))
        con.commit()
    finally:
        con.close()

def get_user_lang(uid: int) -> str:
    info = db_get_user(uid)
    return info.get('lang') or 'ru'

def lib_get_user(uid: int) -> dict:
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM folders WHERE uid=%s ORDER BY id", (uid,))
        folders = cur.fetchall()
        result = {}
        for fid, fname in folders:
            cur.execute("SELECT title, artist, duration, file_id FROM tracks WHERE folder_id=%s ORDER BY id", (fid,))
            result[fname] = [{'title': r[0], 'artist': r[1], 'duration': r[2], 'file_id': r[3]} for r in cur.fetchall()]
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

def lib_delete_track(uid: int, folder: str, idx: int):
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id FROM folders WHERE uid=%s AND name=%s", (uid, folder))
        row = cur.fetchone()
        if not row: return
        fid = row[0]
        cur.execute("SELECT id FROM tracks WHERE folder_id=%s ORDER BY id", (fid,))
        tracks = cur.fetchall()
        if 0 <= idx < len(tracks):
            cur.execute("DELETE FROM tracks WHERE id=%s", (tracks[idx][0],))
            con.commit()
    finally:
        con.close()

# ── Утилиты ───────────────────────────────────────────────────────────────────
def is_pinterest(tx): return 'pinterest.com' in tx or 'pin.it' in tx
def is_tiktok(tx): return 'tiktok.com' in tx
def is_spotify(tx): return 'spotify.com' in tx

def store_url(v):
    _url_store_counter[0] += 1
    k = str(_url_store_counter[0])
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

def clean_search_query(text):
    """Убирает шумовые теги, восстанавливает цензурные слова."""
    q = re.sub(r'f\*+k', 'fuck', text, flags=re.IGNORECASE)
    q = re.sub(r's\*+t', 'shit', q, flags=re.IGNORECASE)
    q = re.sub(r'f\*+d', 'fucked', q, flags=re.IGNORECASE)
    q = re.sub(r'b\*+h', 'bitch', q, flags=re.IGNORECASE)
    q = re.sub(r'a\*+e', 'asshole', q, flags=re.IGNORECASE)
    noise = re.compile(
        r'\s*[\(\[\{][^\)\]\}]*(slowed|reverb|sped up|nightcore|instrumental|remix|edit|version|official|lyrics|video|hd|hq|4k|vevo|feat|ft\.)[^\)\]\}]*[\)\]\}]',
        re.IGNORECASE
    )
    q = noise.sub('', q)
    q = re.sub(r'\s*[\(\[\{][^\)\]\}]*$', '', q)
    q = re.sub(r'[*_|]+', '', q)
    q = ' '.join(q.split()).strip()
    return q if len(q) > 2 else text

def parse_time(s):
    s = s.strip()
    parts = s.split(':')
    try:
        if len(parts) == 1: return int(parts[0])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except: pass
    return None

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

# ── ffmpeg через imageio_ffmpeg (для Railway) ─────────────────────────────────
try:
    import imageio_ffmpeg as _iff, shutil as _shutil
    _ffmpeg_bin = _iff.get_ffmpeg_exe()
    _shutil.copy2(_ffmpeg_bin, '/tmp/ffmpeg'); os.chmod('/tmp/ffmpeg', 0o755)
    _shutil.copy2(_ffmpeg_bin, '/tmp/ffprobe'); os.chmod('/tmp/ffprobe', 0o755)
    BASE_OPTS['ffmpeg_location'] = '/tmp'
    BASE_OPTS['ffprobe_location'] = '/tmp/ffprobe'
    os.environ['PATH'] = '/tmp:' + os.environ.get('PATH', '')
    log.info(f"ffmpeg ready at /tmp, ffprobe exists: {os.path.exists('/tmp/ffprobe')}")
    log.info(f"ffmpeg найден: {_ffmpeg_bin}")
except Exception as _ex:
    log.warning(f"imageio_ffmpeg not found: {_ex}")

# ── Поиск куки ────────────────────────────────────────────────────────────────
_cookie_paths = ['cookies.txt', '/app/cookies.txt', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')]
_found_cookie = next((p for p in _cookie_paths if os.path.exists(p)), None)
log.info(f"cookies.txt: {_found_cookie or 'NOT FOUND'}")

# ── Скачивание ────────────────────────────────────────────────────────────────
def _get_spotify_query(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            tx = info.get('title', ''); a = info.get('artist') or info.get('uploader', '')
            return f"{a} {tx}".strip() or None
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

def _shazam_identify_tiktok(tiktok_url):
    import asyncio as _a, glob, uuid
    uid_str = uuid.uuid4().hex[:12]
    base = tmpfile(f'shazam_tt_{uid_str}')
    opts = {
        **BASE_OPTS, **get_cookie_opts(), 'format': 'bestaudio/best',
        'outtmpl': f'{base}.%(ext)s',
    }
    tmp = None; wav = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.extract_info(tiktok_url, download=True)
        files = glob.glob(f'{base}.*')
        if not files: return None
        tmp = files[0]
        wav = base + '_shazam.wav'
        import subprocess
        subprocess.run(['/tmp/ffmpeg', '-y', '-i', tmp, '-t', '30', '-ar', '44100', '-ac', '1', '-f', 'wav', wav],
                       capture_output=True, timeout=30)
        if not os.path.exists(wav) or os.path.getsize(wav) == 0: return None
        loop = _a.new_event_loop()
        try:
            shazam = Shazam()
            result = loop.run_until_complete(shazam.recognize(wav))
        finally: loop.close()
        if not result.get('matches'): return None
        track = result.get('track', {})
        tx = track.get('title', ''); a = track.get('subtitle', '')
        return f"{a} {tx}".strip() if tx else None
    except Exception as ex: log.warning(f"_shazam_tiktok: {ex}")
    finally:
        for f in [tmp, wav]:
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass
    return None

def _clean_title(title, filename, query):
    """Чистим title если это имя файла SC (подчёркивания, хэш) или URL."""
    # Если title это URL или мусор — берём из имени файла
    if not title or title.startswith('http') or re.search(r'_\d{6,}', title) or title.endswith('.mp3'):
        raw = re.sub(r'\.(mp3|mp4|wav|ogg|flac|m4a)$', '', filename or '', flags=re.IGNORECASE)
        raw = re.sub(r'_\d{6,}$', '', raw)
        raw = raw.replace('_', ' ').strip()
        if len(raw) > 2: return raw
        # Если и filename мусор — используем query но только если это не URL
        if query and not query.startswith('http'):
            return clean_search_query(clean_q(query))
    return title or ''

def _download_audio(query_or_url):
    import glob, shutil, uuid
    uid_str = uuid.uuid4().hex[:12]
    out = tmpfile(f'audio_{uid_str}')
    cookie_opts = get_cookie_opts()

    if is_spotify(query_or_url):
        sq = _get_spotify_query(query_or_url)
        sources = [f"scsearch:{sq}", f"dzsearch:{sq}"] if sq else []
    elif is_url(query_or_url):
        sources = [query_or_url]
    else:
        q = clean_q(query_or_url)
        q_clean = clean_search_query(q)
        sources = [f"scsearch:{q}", f"dzsearch:{q}"]
        if q_clean != q and len(q_clean) > 2:
            sources += [f"scsearch:{q_clean}", f"dzsearch:{q_clean}"]
        log.info(f"_download_audio clean query: '{q}' → '{q_clean}'")

    for source in sources:
        is_sc = source.startswith('scsearch:') or source.startswith('dzsearch:')
        opts = {
            **BASE_OPTS,
            **(cookie_opts if not is_sc else {}),
            'format': 'bestaudio/best',
            'outtmpl': f'{out}.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        }
        for f in glob.glob(f'{out}.*'):
            try: os.remove(f)
            except: pass
        log.info(f"_download_audio trying: {source}")
        try:
            info = {}
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(source, download=True) or {}
            except Exception as dl_ex:
                # SC иногда кидает JSON ошибку после успешного скачивания — проверяем файл
                files = glob.glob(f'{out}.*')
                if not files:
                    log.warning(f"_download_audio [{source}]: {dl_ex}"); continue
                log.warning(f"_download_audio [{source}] JSON err but file exists: {dl_ex}")
                # info пустой — попробуем получить метаданные отдельно ниже
            files = glob.glob(f'{out}.*')
            if not files:
                log.warning(f"_download_audio [{source}]: no file after download"); continue
            e = {}
            try:
                entries = info.get('entries', None)
                if entries is not None:
                    valid = [x for x in entries if x and isinstance(x, dict)]
                    e = valid[0] if valid else {}
                else:
                    e = info
            except: e = info
            # Если метаданные пустые — запрашиваем отдельно
            if not e.get('title'):
                try:
                    with yt_dlp.YoutubeDL({**BASE_OPTS, 'skip_download': True, 'quiet': True}) as ydl2:
                        meta = ydl2.extract_info(source, download=False)
                    if meta:
                        entries2 = meta.get('entries', None)
                        if entries2:
                            valid2 = [x for x in entries2 if x and isinstance(x, dict)]
                            if valid2: e = valid2[0]
                        elif meta.get('title'): e = meta
                except: pass

            file = files[0]
            if not file.endswith('.mp3'):
                new_file = f'{out}.mp3'
                shutil.move(file, new_file)
                file = new_file

            raw_title = e.get('title', '')
            uploader = e.get('uploader') or e.get('channel') or e.get('uploader_id') or ''
            # Чистим мусорное название файла SC
            title = _clean_title(raw_title, os.path.basename(file), query_or_url)
            # Убираем мусорный uploader (рандомные заглавные)
            if uploader and re.match(r'^[A-Z0-9]{10,}$', uploader): uploader = ''
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
            for f in glob.glob(f'{out}.*'):
                try: os.remove(f)
                except: pass
    return None

def _search_track_meta(query_or_url):
    """Ищет метаданные трека без скачивания."""
    cookie_opts = get_cookie_opts()
    if is_spotify(query_or_url):
        sq = _get_spotify_query(query_or_url)
        sources = [f"scsearch:{sq}", f"dzsearch:{sq}"] if sq else []
    elif is_url(query_or_url):
        sources = [query_or_url]
    else:
        q = clean_q(query_or_url)
        q_clean = clean_search_query(q)
        sources = [f"scsearch:{q}", f"dzsearch:{q}"]
        if q_clean != q and len(q_clean) > 2:
            sources += [f"scsearch:{q_clean}", f"dzsearch:{q_clean}"]
    for source in sources:
        is_sc = source.startswith('scsearch:') or source.startswith('dzsearch:')
        opts = {**BASE_OPTS, **(cookie_opts if not is_sc else {}), 'skip_download': True, 'quiet': True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False)
            if not info: continue
            entries = info.get('entries', None)
            e = (entries[0] if entries else None) if entries is not None else info
            if not e or not e.get('title'): continue
            return {
                'title': e.get('title', ''),
                'uploader': e.get('uploader') or e.get('channel') or '',
                'duration': e.get('duration', 0) or 0,
                'source': e.get('extractor', ''),
                'url': e.get('webpage_url') or e.get('url') or source,
            }
        except Exception as ex:
            log.warning(f"_search_track_meta [{source}]: {ex}")
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
        log.warning(f"_download_video: {ex}")
    return None

def _search_tracks_list(query, max_results=5):
    results = []
    q = clean_q(query)
    q_clean = clean_search_query(q)
    for source in [f"scsearch{max_results}:{q}", f"dzsearch{max_results}:{q_clean}"]:
        try:
            opts = {**BASE_OPTS, 'skip_download': True, 'extract_flat': True, 'quiet': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False)
                for e in (info.get('entries', []) if info else []):
                    if not e: continue
                    title = e.get('title', '')
                    url = e.get('webpage_url') or e.get('url', '')
                    # Убираем api.soundcloud.com — берём только нормальные URL
                    if 'api.soundcloud.com' in url:
                        url = e.get('webpage_url', '') or url
                    if title and url and len(results) < max_results:
                        results.append({'title': title, 'url': url,
                                        'duration': e.get('duration', 0) or 0,
                                        'uploader': e.get('uploader') or e.get('channel', '')})
        except Exception as ex: log.warning(f"_search_tracks_list [{source}]: {ex}")
        if len(results) >= max_results: break
    seen = set(); unique = []
    for r in results:
        k = r['title'].lower()[:40]
        if k not in seen: seen.add(k); unique.append(r)
    return unique[:max_results]

def _extract_audio_for_shazam(video_path):
    out = video_path + '_shazam.mp3'
    ret = os.system(f'/tmp/ffmpeg -y -i "{video_path}" -t 30 -vn -ar 44100 -ac 2 -b:a 128k "{out}" -loglevel quiet')
    return out if ret == 0 and os.path.exists(out) else None

def _extract_audio_segment(video_path, start_sec, duration=20):
    import uuid
    out = tmpfile(f'shazam_seg_{uuid.uuid4().hex[:8]}.mp3')
    ret = os.system(f'/tmp/ffmpeg -y -ss {start_sec} -i "{video_path}" -t {duration} -vn -ar 44100 -ac 2 -b:a 128k "{out}" -loglevel quiet')
    return out if ret == 0 and os.path.exists(out) and os.path.getsize(out) > 1000 else None

async def _recognize_shazam_best(video_path):
    import subprocess
    try:
        r = subprocess.run(['/tmp/ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path],
                           capture_output=True, text=True, timeout=10)
        duration = float(json.loads(r.stdout).get('format', {}).get('duration', 60))
    except: duration = 60
    starts = [0, int(duration * 0.25), int(duration * 0.5)]
    async def try_segment(start):
        seg = await asyncio.get_event_loop().run_in_executor(executor, _extract_audio_segment, video_path, start)
        if not seg: return None
        try:
            result = await asyncio.wait_for(Shazam().recognize(seg), timeout=20)
            if result.get('matches'):
                track = result.get('track', {})
                score = result['matches'][0].get('score', 0) if result.get('matches') else 0
                return {'title': track.get('title',''), 'artist': track.get('subtitle',''), 'score': score}
        except: pass
        finally:
            if os.path.exists(seg):
                try: os.remove(seg)
                except: pass
        return None
    results = await asyncio.gather(*[try_segment(s) for s in starts], return_exceptions=True)
    best = None
    for r in results:
        if isinstance(r, dict) and r.get('title'):
            if best is None or r.get('score', 0) > best.get('score', 0):
                best = r
    return best

async def _recognize_shazam(file_path):
    try:
        shazam = Shazam()
        result = await shazam.recognize(file_path)
        if not result.get('matches'): return None
        track = result.get('track', {})
        tx = track.get('title', ''); a = track.get('subtitle', '')
        if tx: return {'title': tx, 'artist': a, 'query': f"{a} {tx}".strip()}
    except Exception as ex: log.warning(f"Shazam: {ex}")
    return None

def _trim_audio(src, start_sec, end_sec):
    out = src.replace('.mp3', f'_trim_{start_sec}_{end_sec or "end"}.mp3')
    dur_arg = f"-t {end_sec - start_sec}" if end_sec is not None else ""
    cmd = f'/tmp/ffmpeg -y -i "{src}" -ss {start_sec} {dur_arg} -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
    ret = os.system(cmd)
    return out if ret == 0 and os.path.exists(out) else None

# ── TMDB поиск фильмов ────────────────────────────────────────────────────────
def _search_media_tmdb(query):
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
                    item['_mt'] = mt; results_all.append(item)
        except Exception as ex: log.warning(f"TMDB {mt}: {ex}")
    if not results_all: return None
    best = max(results_all, key=lambda x: x.get('popularity', 0))
    mt = best.get('_mt', 'movie')
    title = best.get('title') or best.get('name', '')
    orig = best.get('original_title') or best.get('original_name', '')
    overview = (best.get('overview', '') or '')[:300]
    if len(best.get('overview', '')) > 300: overview += '...'
    rating = best.get('vote_average', 0); votes = best.get('vote_count', 0)
    date = best.get('release_date') or best.get('first_air_date', '')
    year = date[:4] if date else '?'
    poster = best.get('poster_path', '')
    poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None
    is_anime = (16 in best.get('genre_ids', []) and 'JP' in best.get('origin_country', []))
    type_label = {'movie': '🎬 Фильм', 'tv': '📺 Сериал'}.get(mt, '🎬')
    if is_anime: type_label = '🌸 Аниме'
    return {'title': title, 'original_title': orig, 'type': type_label, 'year': year,
            'rating': rating, 'vote_count': votes, 'overview': overview, 'poster_url': poster_url}

async def _send_tmdb_result(message, result):
    orig_line = f"\n🔤 <i>{result['original_title']}</i>" if result['original_title'] != result['title'] else ''
    caption = (
        f"{result['type']}  •  {result['year']}\n"
        f"🎬 <b>{result['title']}</b>{orig_line}\n"
        f"⭐ {result['rating']:.1f}/10  ({result['vote_count']} голосов)\n\n"
        f"📝 {result['overview']}"
    )
    if result['poster_url']:
        try:
            await message.reply_photo(photo=result['poster_url'], caption=caption, parse_mode="HTML"); return
        except: pass
    await message.reply_text(caption, parse_mode="HTML")

# ── Библиотека UI ─────────────────────────────────────────────────────────────
async def show_library(update_or_query, uid, lang, edit=False):
    folders = lib_get_user(uid)
    buttons = []
    for fname in folders:
        count = len(folders[fname])
        buttons.append([InlineKeyboardButton(f"📁 {fname}  ({count})", callback_data=f"lib_folder|{store_url(fname)}")])
    buttons.append([InlineKeyboardButton(t('btn_new_folder', lang), callback_data="lib_new_folder")])
    text = t('lib_title', lang)
    text += t('lib_folders_count', lang, n=len(folders)) if folders else t('lib_empty', lang)
    kb = InlineKeyboardMarkup(buttons)
    if edit:
        try: await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except: pass
    else:
        await update_or_query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def show_folder(query, uid, lang, folder):
    folders = lib_get_user(uid)
    tracks = folders.get(folder, [])
    buttons = []
    for i, tr in enumerate(tracks):
        dur = fmt_dur(tr.get('duration', 0))
        buttons.append([
            InlineKeyboardButton(f"🎵 {tr['title'][:28]}  {dur}", callback_data=f"lib_play|{store_url(folder)}|{i}"),
            InlineKeyboardButton("🗑", callback_data=f"lib_del_track|{store_url(folder)}|{i}"),
        ])
    del_label = {'ru': 'Удалить папку', 'en': 'Delete folder', 'tr': 'Klasörü sil', 'uz': "O'chirish", 'ua': 'Видалити папку', 'ar': 'حذف المجلد'}.get(lang, 'Delete folder')
    buttons.append([
        InlineKeyboardButton(f"🗑 {del_label}", callback_data=f"lib_del_folder|{store_url(folder)}"),
        InlineKeyboardButton(t('btn_back', lang), callback_data="lib_back"),
    ])
    empty_hint = {'ru': 'Папка пустая.\nСкачай трек и нажми 📁 Сохранить', 'en': 'Folder is empty.\nDownload a track and tap 📁 Save'}.get(lang, 'Empty folder.')
    text = f"📁 <b>{folder}</b>\n\n"
    text += f"Треков: <b>{len(tracks)}</b>" if tracks else empty_hint
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except: pass

# ── Команды ───────────────────────────────────────────────────────────────────
def lang_keyboard():
    rows = []
    items = list(LANGS.items())
    for i in range(0, len(items), 3):
        row = []
        for code, (flag, name) in items[i:i+3]:
            row.append(InlineKeyboardButton(f"{flag} {name}", callback_data=f"setlang|{code}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name or "friend"
    user_info = db_get_user(uid)
    if user_info['is_new'] or user_info['lang'] is None:
        lang = user_info.get('lang') or 'ru'
        await update.message.reply_text(t('welcome_new', lang, name=name), parse_mode="HTML", reply_markup=lang_keyboard())
    else:
        lang = user_info['lang']
        await update.message.reply_text(t('start_main', lang, name=name), parse_mode="HTML")

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    await update.message.reply_text(t('choose_lang', lang), parse_mode="HTML", reply_markup=lang_keyboard())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    help_texts = {
        'ru': ("📖 <b>Инструкция</b>\n\n"
               "🔗 TikTok / Pinterest → Аудио или Видео\n"
               "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
               "🔍 <code>найти [исполнитель трек]</code>\n\n"
               "✂️ После скачивания:\n"
               "    <code>обрезать 0:30 0:45</code>\n\n"
               "📁 /library — библиотека\n"
               "🌐 /lang — язык\n\n"
               "🎬 Пришли видео до 20MB → Shazam распознает"),
        'en': ("📖 <b>Help</b>\n\n"
               "🔗 TikTok / Pinterest → Audio or Video\n"
               "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
               "🔍 <code>find [artist track]</code>\n\n"
               "✂️ After downloading:\n"
               "    <code>trim 0:30 0:45</code>\n\n"
               "📁 /library — library\n"
               "🌐 /lang — language\n\n"
               "🎬 Send video up to 20MB → Shazam recognizes"),
    }
    await update.message.reply_text(help_texts.get(lang, help_texts['ru']), parse_mode="HTML")

async def cmd_library(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    await show_library(update, uid, lang)

# ── Обработчик текста ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    loop = asyncio.get_event_loop()
    lower = text.lower()

    # ── Ожидаем название папки ────────────────────────────────────────────────
    state = _user_state.get(uid, {})
    if state.get('action') == 'create_folder':
        folder_name = text.strip()
        if len(folder_name) > 50:
            await safe_reply(update, "❌ Название слишком длинное (макс. 50 символов).")
            return
        lib_create_folder(uid, folder_name)
        _user_state.pop(uid, None)
        await safe_reply(update, t('folder_created', lang, name=folder_name), parse_mode="HTML")
        await show_library(update, uid, lang)
        return

    # ── Ожидаем время обрезки MP3 ─────────────────────────────────────────────
    if state.get('action') == 'mp3_trim_input':
        audio_path = state.get('audio_path', '')
        vid_dur = state.get('dur', 0)
        if not os.path.exists(audio_path):
            _user_state.pop(uid, None)
            await safe_reply(update, "❌ Файл не найден. Пришли mp3 снова.")
            return
        parts = text.strip().split()
        if len(parts) != 2:
            await safe_reply(update, "❌ Формат: <code>0:30 1:00</code>", parse_mode="HTML"); return
        start_sec = parse_time(parts[0])
        end_raw = parts[1].lower()
        end_sec = None if end_raw in ('конец', 'end') else parse_time(end_raw)
        if start_sec is None:
            await safe_reply(update, "❌ Неверный формат. Пример: <code>0:30 1:00</code>", parse_mode="HTML"); return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, "❌ Конец должен быть больше начала."); return
        msg = await safe_reply(update, "✂️ <b>Обрезаю...</b>", parse_mode="HTML")
        trimmed = await loop.run_in_executor(executor, _trim_audio, audio_path, start_sec, end_sec)
        if not trimmed:
            await safe_edit(msg, "❌ Ошибка обрезки.", parse_mode="HTML"); return
        s_fmt = fmt_dur(start_sec); e_fmt = fmt_dur(end_sec) if end_sec is not None else "конец"
        trim_info = _trim_state.get(uid, {})
        await safe_edit(msg, f"✅ Готово! ⏱ {s_fmt} → {e_fmt}", parse_mode="HTML")
        with open(trimmed, 'rb') as f:
            await update.message.reply_audio(f, title=f"{trim_info.get('title','track')} [{s_fmt}-{e_fmt}]",
                                              performer=trim_info.get('uploader', ''))
        _user_state.pop(uid, None)
        try: await msg.delete()
        except: pass
        try: os.remove(trimmed)
        except: pass
        return

    # ── Обрезка треков ────────────────────────────────────────────────────────
    trim_kw = t('trim_keyword', lang)
    m_range = re.match(rf'^{re.escape(trim_kw)}\s+(\S+)\s+(\S+)\s*$', lower)
    m_to    = re.match(rf'^{re.escape(trim_kw)}\s+(?:до|to|gacha|до|إلى|kadar)\s+(\S+)\s*$', lower)
    m_from  = re.match(rf'^{re.escape(trim_kw)}\s+(?:с|from|dan|від|من|den)\s+(\S+)\s*$', lower)

    if m_range or m_to or m_from:
        st = _trim_state.get(uid)
        if not st or not os.path.exists(st.get('file', '')):
            await safe_reply(update, t('trim_no_track', lang), parse_mode="HTML"); return
        if m_range:
            start_sec = parse_time(m_range.group(1)); end_sec = parse_time(m_range.group(2))
        elif m_to:
            start_sec = 0; end_sec = parse_time(m_to.group(1))
        else:
            start_sec = parse_time(m_from.group(1)); end_sec = None
        if start_sec is None:
            await safe_reply(update, "❌ Неверный формат.", parse_mode="HTML"); return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, "❌ Конец должен быть больше начала."); return
        msg = await safe_reply(update, t('trimming', lang), parse_mode="HTML")
        trimmed = await loop.run_in_executor(executor, _trim_audio, st['file'], start_sec, end_sec)
        if not trimmed:
            await safe_edit(msg, "❌ ffmpeg error", parse_mode="HTML"); return
        s_fmt = fmt_dur(start_sec); e_fmt = fmt_dur(end_sec) if end_sec else "end"
        await safe_edit(msg, t('trim_done', lang, s=s_fmt, e=e_fmt), parse_mode="HTML")
        with open(trimmed, 'rb') as f:
            await update.message.reply_audio(f, title=f"{st['title']} [{s_fmt}-{e_fmt}]", performer=st.get('uploader', ''))
        try: await msg.delete()
        except: pass
        try: os.remove(trimmed)
        except: pass
        return

    # ── Музыка ────────────────────────────────────────────────────────────────
    url_match = is_url(text)
    search_kw = t('search_keyword', lang)
    search_match = lower.startswith(search_kw)
    if not url_match and not search_match: return

    # ── TikTok ────────────────────────────────────────────────────────────────
    if url_match and is_tiktok(text):
        msg = await safe_reply(update, t('processing', lang), parse_mode="HTML")
        if not msg: return
        await safe_edit(msg, t('shazam_detecting', lang), parse_mode="HTML")
        try:
            shazam_q = await asyncio.wait_for(loop.run_in_executor(executor, _shazam_identify_tiktok, text), timeout=45)
        except asyncio.TimeoutError: shazam_q = None
        vid_key = store_url(text)
        if shazam_q:
            aud_key = store_url(shazam_q)
            track_line = f"\n\n🎵 <b>{shazam_q}</b>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"),
                                        InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}")]])
        else:
            try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, text), timeout=20)
            except: meta = None
            if meta and meta.get('query'):
                aud_key = store_url(meta['query'])
                track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"),
                                            InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}")]])
            else:
                track_line = ""
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{vid_key}"),
                                            InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}")]])
        await safe_edit(msg, f"📱 <b>TikTok</b>{track_line}\n\n{t('choose_format', lang)}", parse_mode="HTML", reply_markup=kb)
        return

    # ── Pinterest ─────────────────────────────────────────────────────────────
    if url_match and is_pinterest(text):
        msg = await safe_reply(update, t('processing', lang), parse_mode="HTML")
        if not msg: return
        try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, text), timeout=30)
        except: meta = None
        vid_key = store_url(text); buttons = []; track_line = ""
        if meta and meta.get('query'):
            track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
            buttons.append(InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{store_url(meta['query'])}"))
        buttons.append(InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}"))
        await safe_edit(msg, f"📌 <b>Pinterest</b>{track_line}\n\n{t('choose_format', lang)}",
                        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([buttons]))
        return

    # ── Поиск / ссылка ────────────────────────────────────────────────────────
    query = text if url_match else text[len(search_kw):].strip()

    # Для текстового поиска — показываем список 5 вариантов
    if search_match and not url_match:
        msg = await safe_reply(update, "🔍 <b>Ищу варианты...</b>", parse_mode="HTML")
        if not msg: return
        try:
            tracks = await asyncio.wait_for(loop.run_in_executor(executor, _search_tracks_list, query, 5), timeout=30)
        except asyncio.TimeoutError: tracks = []
        if not tracks:
            await safe_edit(msg, t('not_found', lang), parse_mode="HTML"); return
        lines = []; buttons = []
        for i, tr in enumerate(tracks, 1):
            dur = f"  ⏱{fmt_dur(tr['duration'])}" if tr['duration'] else ''
            lines.append(f"{i}. <b>{tr['title']}</b>\n    <i>{tr['uploader']}</i>{dur}")
            buttons.append([InlineKeyboardButton(f"⬇️ {i}. {tr['title'][:35]}", callback_data=f"audio|{store_url(tr['url'])}")])
        list_text = f"🎵 <b>Результаты:</b> «{query}»\n\n" + "\n\n".join(lines)
        await safe_edit(msg, list_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Для ссылки — сначала мета, потом кнопки
    msg = await safe_reply(update, "🔍 Ищу...", parse_mode="HTML")
    if not msg: return
    try:
        meta = await asyncio.wait_for(loop.run_in_executor(executor, _search_track_meta, query), timeout=30)
    except asyncio.TimeoutError: meta = None
    if not meta:
        await safe_edit(msg, t('not_found', lang), parse_mode="HTML"); return

    title = meta['title']; uploader = meta['uploader']
    meta_key = store_url(json.dumps({'url': meta['url'], 'title': title, 'uploader': uploader,
                                      'duration': meta['duration']}, ensure_ascii=False))
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎵 Скачать музыку", callback_data=f"dl_audio|{meta_key}"),
        InlineKeyboardButton("🎬 Скачать видео", callback_data=f"dl_video|{meta_key}"),
    ]])
    await safe_edit(msg, f"✅ <b>Трек найден!</b>\n\n🎵 <b>{title}</b>\n👤 {uploader}",
                    parse_mode="HTML", reply_markup=kb)

# ── Callback кнопок ───────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    await cb.answer()
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    data = cb.data
    loop = asyncio.get_event_loop()

    # ── Язык ──────────────────────────────────────────────────────────────────
    if data.startswith("setlang|"):
        new_lang = data.split("|", 1)[1]
        if new_lang not in LANGS: return
        db_set_lang(uid, new_lang)
        try: await cb.edit_message_text(t('lang_set', new_lang), parse_mode="HTML")
        except: pass
        name = update.effective_user.first_name or "friend"
        await cb.message.reply_text(t('start_main', new_lang, name=name), parse_mode="HTML")
        return

    # ── Скачать музыку (новый флоу с мета) ───────────────────────────────────
    if data.startswith("dl_audio|"):
        raw = get_stored(data.split("|", 1)[1])
        try:
            meta = json.loads(raw)
            url = meta['url']; meta_title = meta.get('title', ''); meta_uploader = meta.get('uploader', '')
            meta_duration = meta.get('duration', 0)
        except: url = raw; meta_title = ''; meta_uploader = ''; meta_duration = 0
        try: await cb.edit_message_text("⏳ <b>Скачиваю...</b>", parse_mode="HTML")
        except: pass
        result = await asyncio.wait_for(loop.run_in_executor(executor, _download_audio, url), timeout=120)
        if not result or not os.path.exists(result.get('file', '')):
            try: await cb.edit_message_text(t('not_found', lang), parse_mode="HTML")
            except: pass
            return
        title = meta_title or result['title']
        uploader = meta_uploader or result['uploader']
        duration = meta_duration or result['duration']
        try: await cb.edit_message_text("📤 <b>Отправляю...</b>", parse_mode="HTML")
        except: pass
        try:
            from telegram import InputFile
            # Сначала отправляем без кнопки
            with open(result['file'], 'rb') as f:
                sent = await cb.message.reply_audio(InputFile(f, filename='audio.mp3'),
                                                    title=title, performer=uploader,
                                                    caption=f"<b>{title}</b>\n{uploader}",
                                                    parse_mode="HTML")
            if sent and sent.audio:
                file_id = sent.audio.file_id
                _trim_state[uid] = {'file': result['file'], 'title': title, 'uploader': uploader,
                                    'file_id': file_id, 'duration': duration}
                # Теперь знаем file_id — добавляем кнопку сохранения
                save_key = store_url(json.dumps({'title': title, 'artist': uploader,
                                                  'duration': duration, 'file_id': file_id}, ensure_ascii=False))
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_save_lib', lang), callback_data=f"lib_save|{save_key}")]])
                try: await sent.edit_reply_markup(reply_markup=kb)
                except: pass
            try: await cb.message.delete()
            except: pass
        except Exception as ex:
            log.error(f"dl_audio: {ex}")
            try: await cb.edit_message_text(f"⚠️ {ex}", parse_mode="HTML")
            except: pass
        finally:
            try: os.remove(result['file'])
            except: pass
        return

    # ── Скачать видео (новый флоу с мета) ────────────────────────────────────
    if data.startswith("dl_video|"):
        raw = get_stored(data.split("|", 1)[1])
        try:
            meta = json.loads(raw)
            url = meta['url']; meta_title = meta.get('title', ''); meta_uploader = meta.get('uploader', '')
        except: url = raw; meta_title = ''; meta_uploader = ''
        try: await cb.edit_message_text("⏳ <b>Скачиваю видео...</b>", parse_mode="HTML")
        except: pass
        result = await asyncio.wait_for(loop.run_in_executor(executor, _download_video, url), timeout=120)
        if not result or not os.path.exists(result.get('file', '')):
            try: await cb.edit_message_text(t('not_found', lang), parse_mode="HTML")
            except: pass
            return
        title = meta_title or result['title']; uploader = meta_uploader or result['uploader']
        try: await cb.edit_message_text("📤 <b>Отправляю...</b>", parse_mode="HTML")
        except: pass
        try:
            with open(result['file'], 'rb') as f:
                await cb.message.reply_video(f, caption=f"<b>{title}</b>\n{uploader}", parse_mode="HTML")
            try: await cb.message.delete()
            except: pass
        except Exception as ex:
            log.error(f"dl_video: {ex}")
            try: await cb.edit_message_text(f"⚠️ {ex}", parse_mode="HTML")
            except: pass
        finally:
            try: os.remove(result['file'])
            except: pass
        return

    # ── Shazam из видео ───────────────────────────────────────────────────────
    if data.startswith("vid_shazam|"):
        vid_path = get_stored(data.split("|", 1)[1])
        if not os.path.exists(vid_path):
            await cb.answer("❌ File not found", show_alert=True); return
        try: await cb.edit_message_text(t('shazam_detecting', lang), parse_mode="HTML")
        except: pass
        try:
            track = await asyncio.wait_for(_recognize_shazam_best(vid_path), timeout=60)
        except asyncio.TimeoutError: track = None
        if os.path.exists(vid_path):
            try: os.remove(vid_path)
            except: pass
        _user_state.pop(uid, None)
        if not track:
            try: await cb.edit_message_text(t('track_not_recognized', lang), parse_mode="HTML")
            except: pass
            return
        q_key = store_url(f"{track['artist']} {track['title']}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_download_full', lang), callback_data=f"audio|{q_key}")]])
        try:
            await cb.edit_message_text(t('track_detected', lang, artist=track['artist'], title=track['title']),
                                       parse_mode="HTML", reply_markup=kb)
        except: pass
        return

    if data.startswith("vid_trim|"):
        vid_path = get_stored(data.split("|", 1)[1])
        if not os.path.exists(vid_path):
            await cb.answer("❌ File not found", show_alert=True); return
        state = _user_state.get(uid, {}); vid_dur = state.get('vid_dur', 0)
        _user_state[uid] = {'action': 'trim_input', 'vid_path': vid_path, 'vid_dur': vid_dur}
        prompt = f"✂️ <b>Обрезка</b>  ⏱ {fmt_dur(vid_dur)}\n\nНапиши: <code>начало конец</code>\nПример: <code>0:05 0:10</code>"
        try:
            await cb.edit_message_text(prompt, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_back', lang), callback_data=f"vid_back|{store_url(vid_path)}")]]))
        except: pass
        return

    if data.startswith("vid_back|"):
        vid_path = get_stored(data.split("|", 1)[1])
        state = _user_state.get(uid, {}); vid_dur = state.get('vid_dur', 0)
        _user_state[uid] = {'action': 'video_menu', 'vid_path': vid_path, 'vid_dur': vid_dur}
        vid_key = store_url(vid_path)
        try:
            await cb.edit_message_text(t('video_received', lang, dur=fmt_dur(vid_dur)), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t('btn_find_track', lang), callback_data=f"vid_shazam|{vid_key}"),
                    InlineKeyboardButton(t('btn_trim_video', lang), callback_data=f"vid_trim|{vid_key}")
                ]]))
        except: pass
        return

    if data.startswith("vid_trim_fmt|"):
        parts = data.split("|")
        vid_path = get_stored(parts[1]); start_sec = int(parts[2])
        end_sec = int(parts[3]) if parts[3] != 'end' else None; fmt_v = parts[4]
        if not os.path.exists(vid_path):
            await cb.answer("❌ File not found", show_alert=True); return
        try: await cb.edit_message_text(t('trimming', lang), parse_mode="HTML")
        except: pass
        def _do_trim():
            dur_arg = f"-t {end_sec - start_sec}" if end_sec is not None else ""
            if fmt_v == 'audio':
                out = tmpfile(f"trim_{uid}_{start_sec}_{end_sec or 'end'}.mp3")
                cmd = f'/tmp/ffmpeg -y -i "{vid_path}" -ss {start_sec} {dur_arg} -vn -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
            else:
                out = tmpfile(f"trim_{uid}_{start_sec}_{end_sec or 'end'}.mp4")
                cmd = f'/tmp/ffmpeg -y -i "{vid_path}" -ss {start_sec} {dur_arg} -c:v libx264 -c:a aac -preset fast "{out}" -loglevel quiet'
            ret = os.system(cmd)
            return out if ret == 0 and os.path.exists(out) else None
        out_path = await loop.run_in_executor(executor, _do_trim)
        if os.path.exists(vid_path):
            try: os.remove(vid_path)
            except: pass
        _user_state.pop(uid, None)
        if not out_path:
            try: await cb.edit_message_text("⚠️ ffmpeg error", parse_mode="HTML")
            except: pass
            return
        s_str = fmt_dur(start_sec); e_str = fmt_dur(end_sec) if end_sec is not None else "end"
        try: await cb.edit_message_text(t('trim_done', lang, s=s_str, e=e_str), parse_mode="HTML")
        except: pass
        with open(out_path, 'rb') as f:
            if fmt_v == 'audio': await cb.message.reply_audio(f, title=f"Trim {s_str}-{e_str}")
            else: await cb.message.reply_video(f, caption=f"✂️ {s_str} → {e_str}")
        try: os.remove(out_path)
        except: pass
        try: await cb.delete_message()
        except: pass
        return

    # ── Библиотека ────────────────────────────────────────────────────────────
    if data == "lib_back":
        await show_library(cb, uid, lang, edit=True); return
    if data == "lib_new_folder":
        _user_state[uid] = {'action': 'create_folder'}
        try:
            await cb.edit_message_text(t('create_folder_prompt', lang), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_back', lang), callback_data="lib_back")]]))
        except: pass
        return
    if data.startswith("lib_folder|"):
        folder = get_stored(data.split("|", 1)[1])
        await show_folder(cb, uid, lang, folder); return
    if data.startswith("lib_play|"):
        _, folder_key, idx_str = data.split("|")
        folder = get_stored(folder_key); idx = int(idx_str)
        folders = lib_get_user(uid); tracks = folders.get(folder, [])
        if idx >= len(tracks): await cb.answer("Not found", show_alert=True); return
        track = tracks[idx]
        try:
            await cb.answer("📤")
            await cb.message.reply_audio(audio=track['file_id'], title=track['title'], performer=track.get('artist', ''))
        except Exception as ex: log.error(f"lib_play: {ex}"); await cb.answer("❌ Error", show_alert=True)
        return
    if data.startswith("lib_del_track|"):
        _, folder_key, idx_str = data.split("|")
        folder = get_stored(folder_key); idx = int(idx_str)
        lib_delete_track(uid, folder, idx); await cb.answer("🗑")
        await show_folder(cb, uid, lang, folder); return
    if data.startswith("lib_del_folder|"):
        folder = get_stored(data.split("|", 1)[1])
        lib_delete_folder(uid, folder); await cb.answer("🗑")
        await show_library(cb, uid, lang, edit=True); return
    if data.startswith("lib_save|"):
        track_key = data.split("|", 1)[1]
        folders = lib_get_user(uid)
        if not folders:
            await cb.answer("❌ Сначала создай папку в /library", show_alert=True)
            return
        buttons = []
        for fname in folders:
            fkey = store_url(fname)
            buttons.append([InlineKeyboardButton(f"📁 {fname} ({len(folders[fname])})", callback_data=f"lib_save_to|{fkey}|{track_key}")])
        buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="lib_cancel_save")])
        await cb.message.reply_text("📁 Выбери папку:", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data == "lib_cancel_save":
        try: await cb.delete_message()
        except: pass
        return
    if data.startswith("lib_save_to|"):
        _, folder_key, track_key = data.split("|", 2)
        folder = get_stored(folder_key); track_meta_str = get_stored(track_key)
        try: track_meta = json.loads(track_meta_str)
        except: track_meta = {}
        file_id = track_meta.get('file_id') or _trim_state.get(uid, {}).get('file_id')
        if not file_id:
            await cb.answer("❌ Перескачай трек.", show_alert=True); return
        added = lib_add_track(uid, folder, {
            'title': track_meta.get('title', ''),
            'artist': track_meta.get('artist', ''),
            'duration': track_meta.get('duration', 0),
            'file_id': file_id
        })
        await cb.answer(f"✅ Сохранено в «{folder}»" if added else f"ℹ️ Уже есть в «{folder}»", show_alert=True)
        try: await cb.delete_message()
        except: pass
        return

    # ── Старый флоу audio|/video| (TikTok, Pinterest, библиотека похожих) ────
    if '|' not in data: return
    action, key = data.split('|', 1)
    value = get_stored(key)

    emoji = '🎵' if 'audio' in action else '🎬'
    try: await cb.edit_message_text(f"{emoji} <b>Загружаю...</b>", parse_mode="HTML")
    except: pass
    try:
        if action == 'video':
            result = await asyncio.wait_for(loop.run_in_executor(executor, _download_video, value), timeout=120)
        else:
            result = await asyncio.wait_for(loop.run_in_executor(executor, _download_audio, value), timeout=90)
    except asyncio.TimeoutError:
        try: await cb.edit_message_text(t('timeout', lang), parse_mode="HTML")
        except: pass
        return
    if not result or not os.path.exists(result.get('file', '')):
        try: await cb.edit_message_text(t('not_found', lang), parse_mode="HTML")
        except: pass
        return
    try:
        title = result['title']; uploader = result['uploader']
        if result['type'] == 'audio':
            from telegram import InputFile
            with open(result['file'], 'rb') as f:
                sent = await cb.message.reply_audio(InputFile(f, filename='audio.mp3'),
                                                    title=title, performer=uploader,
                                                    caption=f"<b>{title}</b>\n{uploader}",
                                                    parse_mode="HTML")
            if sent and sent.audio:
                file_id = sent.audio.file_id
                _trim_state[uid] = {'file': result['file'], 'title': title, 'uploader': uploader,
                                    'file_id': file_id, 'duration': result['duration']}
                save_key = store_url(json.dumps({'title': title, 'artist': uploader,
                                                  'duration': result['duration'], 'file_id': file_id}, ensure_ascii=False))
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_save_lib', lang), callback_data=f"lib_save|{save_key}")]])
                try: await sent.edit_reply_markup(reply_markup=kb)
                except: pass
            try: os.remove(result['file'])
            except: pass
        else:
            with open(result['file'], 'rb') as f:
                await cb.message.reply_video(f, caption=f"<b>{title}</b>", parse_mode="HTML")
            try: os.remove(result['file'])
            except: pass
        try: await cb.delete_message()
        except: pass
    except Exception as ex:
        log.error(f"callback send: {ex}")
        try: await cb.edit_message_text(f"❌ {ex}")
        except: pass

# ── Видеофайл ─────────────────────────────────────────────────────────────────
async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.animation: return
    video = update.message.video or update.message.document
    if not video: return
    dur = getattr(video, 'duration', None)
    if dur is not None and dur == 0: return
    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("⚠️ > 20MB"); return
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    caption = (update.message.caption or '').strip().lower()

    if 'найти' in caption or 'find' in caption:
        msg = await safe_reply(update, "🔍 <b>Ищу в базе фильмов...</b>", parse_mode="HTML")
        query = re.sub(r'найти|find', '', caption, flags=re.IGNORECASE).strip()
        if not query:
            fn = getattr(video, 'file_name', '') or ''
            query = os.path.splitext(fn)[0].replace('_', ' ').replace('-', ' ').strip()
        if not query:
            await safe_edit(msg, "😔 Напиши название: <code>найти Inception</code>", parse_mode="HTML"); return
        result = await asyncio.get_event_loop().run_in_executor(executor, _search_media_tmdb, query)
        try: await msg.delete()
        except: pass
        if not result:
            await update.message.reply_text("😔 Ничего не найдено.", parse_mode="HTML"); return
        await _send_tmdb_result(update.message, result)
        return

    msg = await safe_reply(update, "⏳ <b>Получаю файл...</b>", parse_mode="HTML")
    if not msg: return
    vid_path = tmpfile(f"video_{uid}_{update.message.message_id}.mp4")
    try:
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(vid_path)
    except Exception as ex:
        await safe_edit(msg, f"⚠️ {ex}", parse_mode="HTML"); return
    vid_dur = getattr(video, 'duration', 0) or 0
    _user_state[uid] = {'action': 'video_menu', 'vid_path': vid_path, 'vid_dur': vid_dur}
    vid_key = store_url(vid_path)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t('btn_find_track', lang), callback_data=f"vid_shazam|{vid_key}"),
        InlineKeyboardButton(t('btn_trim_video', lang), callback_data=f"vid_trim|{vid_key}"),
    ]])
    await safe_edit(msg, t('video_received', lang, dur=fmt_dur(vid_dur)), parse_mode="HTML", reply_markup=kb)

# ── Фото ──────────────────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    caption = (update.message.caption or '').strip().lower()
    if 'найти' not in caption and 'find' not in caption: return
    msg = await safe_reply(update, "🔍 <b>Ищу в базе фильмов...</b>", parse_mode="HTML")
    query = re.sub(r'найти|find', '', caption, flags=re.IGNORECASE).strip()
    if not query:
        await safe_edit(msg, "😔 Напиши название рядом с фото: <code>найти Inception</code>", parse_mode="HTML"); return
    result = await asyncio.get_event_loop().run_in_executor(executor, _search_media_tmdb, query)
    try: await msg.delete()
    except: pass
    if not result:
        await update.message.reply_text("😔 Ничего не найдено.", parse_mode="HTML"); return
    await _send_tmdb_result(update.message, result)

# ── MP3 файл ──────────────────────────────────────────────────────────────────
async def handle_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    audio = update.message.audio or update.message.document
    if not audio: return
    mime = getattr(audio, 'mime_type', '') or ''
    fname = getattr(audio, 'file_name', '') or ''
    if not (mime.startswith('audio/') or fname.lower().endswith('.mp3')): return
    caption = (update.message.caption or '').strip().lower()
    if not any(w in caption for w in ['обрежь', 'обрезать', 'trim', 'cut', 'обрезай']): return
    if audio.file_size and audio.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("⚠️ Файл больше 50MB."); return
    msg = await safe_reply(update, "⏳ <b>Скачиваю аудио...</b>", parse_mode="HTML")
    if not msg: return
    audio_path = tmpfile(f"mp3_{uid}_{update.message.message_id}.mp3")
    try:
        file = await context.bot.get_file(audio.file_id)
        await file.download_to_drive(audio_path)
    except Exception as ex:
        await safe_edit(msg, f"⚠️ {ex}", parse_mode="HTML"); return
    import subprocess
    dur_sec = 0
    try:
        r = subprocess.run(['/tmp/ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', audio_path],
                           capture_output=True, text=True, timeout=10)
        dur_sec = float(json.loads(r.stdout).get('format', {}).get('duration', 0))
    except: pass
    title = getattr(audio, 'title', '') or os.path.splitext(fname)[0] or 'track'
    performer = getattr(audio, 'performer', '') or ''
    _trim_state[uid] = {'file': audio_path, 'title': title, 'uploader': performer,
                        'file_id': audio.file_id, 'duration': int(dur_sec)}
    _user_state[uid] = {'action': 'mp3_trim_input', 'audio_path': audio_path, 'dur': int(dur_sec)}
    dur_str = fmt_dur(int(dur_sec)) if dur_sec else "?"
    await safe_edit(msg,
        f"🎵 <b>{title}</b>  ⏱ {dur_str}\n\n"
        f"✂️ Напиши какую часть оставить:\n"
        f"  <code>0:30 1:00</code> — с 30 сек до 1 мин\n"
        f"  <code>0:30 конец</code> — с 30 сек до конца",
        parse_mode="HTML")

# ── Запуск ────────────────────────────────────────────────────────────────────
async def post_init(application):
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_my_commands([
        ('start', 'Главное меню'),
        ('help', 'Помощь'),
        ('lang', 'Язык'),
        ('library', 'Библиотека'),
    ])

app = (ApplicationBuilder().token(TOKEN).post_init(post_init)
       .connect_timeout(30).read_timeout(60).write_timeout(120).build())
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("help", cmd_help))
app.add_handler(CommandHandler("lang", cmd_lang))
app.add_handler(CommandHandler("library", cmd_library))
app.add_handler(CallbackQueryHandler(handle_callback))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.AUDIO | (filters.Document.AUDIO | filters.Document.MimeType("audio/mpeg")), handle_audio_file))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler((filters.VIDEO | filters.Document.VIDEO) & ~filters.ANIMATION, handle_video_file))
log.info("Бот запущен ✅")
app.run_polling(drop_pending_updates=True)