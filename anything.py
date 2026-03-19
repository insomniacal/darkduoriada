import os, re, asyncio, hashlib, logging, unicodedata, urllib.request, urllib.parse, json
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
from shazamio import Shazam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import psycopg2

# ── Настройки ─────────────────────────────────────────────────────────────────
TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"        # Telegram Bot Token (от @BotFather)
DB_URL = "postgresql://postgres:.rep.1417228@db.yhxxgohuznubzaqebiyu.supabase.co:5432/postgres"       # postgresql://postgres:ПАРОЛЬ@db.ХХХХ.supabase.co:5432/postgres
TMDB_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InloeHhnb2h1em51YnphcWViaXl1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMzNDQ1ODksImV4cCI6MjA4ODkyMDU4OX0.HGcEVR5wMnPjvlR2IGiztJ8fMIZtn9QP9vFEaUre0Ew"   # themoviedb.org → Settings → API → API Read Access Token (длинный eyJ...)

TEMP_DIR = "/tmp/musicbot"
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=8)
cache: dict = {}
CACHE_MAX = 30
_url_store: dict = {}
_trim_state: dict = {}
_user_state: dict = {}

URL_PATTERN = re.compile(
    r'https?://(www\.|vm\.|vt\.)?'
    r'(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com'
    r'|pin\.it|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

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
        'ru': "👋 <b>Привет, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nВыбери язык интерфейса:",
        'en': "👋 <b>Hello, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nChoose your language:",
        'uz': "👋 <b>Salom, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nTilni tanlang:",
        'ua': "👋 <b>Привіт, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nОберіть мову:",
        'ar': "👋 <b>مرحباً، {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nاختر لغتك:",
        'tr': "👋 <b>Merhaba, {name}!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nDil seçin:",
    },
    'lang_set': {
        'ru': "✅ Язык установлен: 🇷🇺 Русский",
        'en': "✅ Language set: 🇬🇧 English",
        'uz': "✅ Til o'rnatildi: 🇺🇿 O'zbek",
        'ua': "✅ Мову встановлено: 🇺🇦 Українська",
        'ar': "✅ تم تعيين اللغة: 🇸🇦 العربية",
        'tr': "✅ Dil ayarlandı: 🇹🇷 Türkçe",
    },
    'start_main': {
        'ru': (
            "🎵 <b>С возвращением, {name}!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Что умею:</b>\n\n"
            "🔗 <b>Ссылка</b> — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
            "🔍 <b>Поиск:</b> <code>найти The Weeknd Blinding Lights</code>\n\n"
            "✂️ <b>Обрезка</b> (после скачивания):\n"
            "    <code>обрезать 0:30 0:45</code>\n\n"
            "📁 <b>Библиотека</b> — /library\n\n"
            "🎬 <b>Распознать трек</b> — пришли видео до 20MB\n\n"
            "🌐 Сменить язык — /lang\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ Повторные запросы — мгновенно"
        ),
        'en': (
            "🎵 <b>Welcome back, {name}!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>What I can do:</b>\n\n"
            "🔗 <b>Link</b> — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
            "🔍 <b>Search:</b> <code>find The Weeknd Blinding Lights</code>\n\n"
            "✂️ <b>Trim</b> (after download):\n"
            "    <code>trim 0:30 0:45</code>\n\n"
            "📁 <b>Library</b> — /library\n\n"
            "🎬 <b>Recognize track</b> — send video up to 20MB\n\n"
            "🌐 Change language — /lang\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ Repeated requests — instant"
        ),
        'uz': (
            "🎵 <b>Xush kelibsiz, {name}!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Nima qila olaman:</b>\n\n"
            "🔗 <b>Havola</b> — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
            "🔍 <b>Qidirish:</b> <code>topish The Weeknd Blinding Lights</code>\n\n"
            "✂️ <b>Kesish</b> (yuklab olgandan keyin):\n"
            "    <code>kesish 0:30 0:45</code>\n\n"
            "📁 <b>Kutubxona</b> — /library\n\n"
            "🎬 <b>Trekni aniqlash</b> — 20MB gacha video yuboring\n\n"
            "🌐 Tilni o'zgartirish — /lang\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ Takroriy so'rovlar — darhol"
        ),
        'ua': (
            "🎵 <b>З поверненням, {name}!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Що вмію:</b>\n\n"
            "🔗 <b>Посилання</b> — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
            "🔍 <b>Пошук:</b> <code>знайти The Weeknd Blinding Lights</code>\n\n"
            "✂️ <b>Обрізка</b> (після завантаження):\n"
            "    <code>обрізати 0:30 0:45</code>\n\n"
            "📁 <b>Бібліотека</b> — /library\n\n"
            "🎬 <b>Розпізнати трек</b> — надішли відео до 20MB\n\n"
            "🌐 Змінити мову — /lang\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ Повторні запити — миттєво"
        ),
        'ar': (
            "🎵 <b>مرحباً بعودتك، {name}!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>ما أستطيع فعله:</b>\n\n"
            "🔗 <b>رابط</b> — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
            "🔍 <b>بحث:</b> <code>ابحث The Weeknd Blinding Lights</code>\n\n"
            "✂️ <b>قص</b> (بعد التنزيل):\n"
            "    <code>قص 0:30 0:45</code>\n\n"
            "📁 <b>المكتبة</b> — /library\n\n"
            "🎬 <b>التعرف على الأغنية</b> — أرسل فيديو حتى 20MB\n\n"
            "🌐 تغيير اللغة — /lang\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ الطلبات المتكررة — فورية"
        ),
        'tr': (
            "🎵 <b>Tekrar hoş geldin, {name}!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Neler yapabilirim:</b>\n\n"
            "🔗 <b>Bağlantı</b> — TikTok · Pinterest · YouTube · SoundCloud · Spotify\n\n"
            "🔍 <b>Arama:</b> <code>bul The Weeknd Blinding Lights</code>\n\n"
            "✂️ <b>Kırp</b> (indirdikten sonra):\n"
            "    <code>kırp 0:30 0:45</code>\n\n"
            "📁 <b>Kütüphane</b> — /library\n\n"
            "🎬 <b>Parçayı tanı</b> — 20MB'a kadar video gönder\n\n"
            "🌐 Dil değiştir — /lang\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ Tekrar istekler — anında"
        ),
    },
    'searching': {
        'ru': '🔍 Ищу {q}...',
        'en': '🔍 Searching {q}...',
        'uz': '🔍 Qidirilmoqda {q}...',
        'ua': '🔍 Шукаю {q}...',
        'ar': '🔍 جاري البحث {q}...',
        'tr': '🔍 Aranıyor {q}...',
    },
    'found': {
        'ru': '✅ <b>Нашёл!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{title}</b>\n👤 {uploader}\n⏱ {dur}  •  {src}\n━━━━━━━━━━━━━━━━━━━━━━\n📤 Отправляю...',
        'en': '✅ <b>Found!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{title}</b>\n👤 {uploader}\n⏱ {dur}  •  {src}\n━━━━━━━━━━━━━━━━━━━━━━\n📤 Sending...',
        'uz': '✅ <b>Topildi!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{title}</b>\n👤 {uploader}\n⏱ {dur}  •  {src}\n━━━━━━━━━━━━━━━━━━━━━━\n📤 Yuborilmoqda...',
        'ua': '✅ <b>Знайшов!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{title}</b>\n👤 {uploader}\n⏱ {dur}  •  {src}\n━━━━━━━━━━━━━━━━━━━━━━\n📤 Відправляю...',
        'ar': '✅ <b>وجدت!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{title}</b>\n👤 {uploader}\n⏱ {dur}  •  {src}\n━━━━━━━━━━━━━━━━━━━━━━\n📤 جاري الإرسال...',
        'tr': '✅ <b>Bulundu!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{title}</b>\n👤 {uploader}\n⏱ {dur}  •  {src}\n━━━━━━━━━━━━━━━━━━━━━━\n📤 Gönderiliyor...',
    },
    'not_found': {
        'ru': '😔 Ничего не найдено. Попробуй уточнить запрос.',
        'en': '😔 Nothing found. Try a more specific query.',
        'uz': '😔 Hech narsa topilmadi. So\'rovni aniqlashtiring.',
        'ua': '😔 Нічого не знайдено. Спробуй уточнити запит.',
        'ar': '😔 لم يتم العثور على شيء. حاول تحديد البحث.',
        'tr': '😔 Hiçbir şey bulunamadı. Sorguyu detaylandırın.',
    },
    'timeout': {
        'ru': '⚠️ Превышено время ожидания. Попробуй ещё раз.',
        'en': '⚠️ Request timed out. Please try again.',
        'uz': '⚠️ Vaqt tugadi. Qayta urinib ko\'ring.',
        'ua': '⚠️ Час очікування вичерпано. Спробуй ще раз.',
        'ar': '⚠️ انتهت مهلة الطلب. يرجى المحاولة مرة أخرى.',
        'tr': '⚠️ İstek zaman aşımına uğradı. Lütfen tekrar deneyin.',
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
        'ru': '🎵 <b>Определяю трек через Shazam...</b>',
        'en': '🎵 <b>Detecting track via Shazam...</b>',
        'uz': '🎵 <b>Shazam orqali trek aniqlanmoqda...</b>',
        'ua': '🎵 <b>Визначаю трек через Shazam...</b>',
        'ar': '🎵 <b>جاري التعرف على الأغنية عبر Shazam...</b>',
        'tr': '🎵 <b>Shazam ile parça tespit ediliyor...</b>',
    },
    'choose_format': {
        'ru': 'Выбери формат:',
        'en': 'Choose format:',
        'uz': 'Formatni tanlang:',
        'ua': 'Обери формат:',
        'ar': 'اختر التنسيق:',
        'tr': 'Format seçin:',
    },
    'btn_similar': {
        'ru': '🔀 Похожие',
        'en': '🔀 Similar',
        'uz': '🔀 O\'xshash',
        'ua': '🔀 Схожі',
        'ar': '🔀 مشابه',
        'tr': '🔀 Benzer',
    },
    'btn_artist': {
        'ru': '🎤 Ещё от исполнителя',
        'en': '🎤 More by artist',
        'uz': '🎤 Ijrochidan ko\'proq',
        'ua': '🎤 Ще від виконавця',
        'ar': '🎤 المزيد من الفنان',
        'tr': '🎤 Sanatçıdan daha fazla',
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
        'uz': '⚠️ Kesish uchun trek yo\'q. Avval musiqa yuklab oling.',
        'ua': '⚠️ Немає треку для обрізки. Спочатку завантаж музику.',
        'ar': '⚠️ لا يوجد مقطع للقص. قم بتنزيل مقطع موسيقي أولاً.',
        'tr': '⚠️ Kırpılacak parça yok. Önce müzik indirin.',
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
        'uz': '✅ Tayyor! ⏱ {s} → {e}\n📤 Yuborilmoqda...',
        'ua': '✅ Готово! ⏱ {s} → {e}\n📤 Відправляю...',
        'ar': '✅ تم! ⏱ {s} → {e}\n📤 جاري الإرسال...',
        'tr': '✅ Bitti! ⏱ {s} → {e}\n📤 Gönderiliyor...',
    },
    'cache_instant': {
        'ru': '⚡️ <b>Мгновенно из кэша!</b>',
        'en': '⚡️ <b>Instant from cache!</b>',
        'uz': '⚡️ <b>Keshdan darhol!</b>',
        'ua': '⚡️ <b>Миттєво з кешу!</b>',
        'ar': '⚡️ <b>فوري من الذاكرة المؤقتة!</b>',
        'tr': '⚡️ <b>Önbellekten anında!</b>',
    },
    'lib_title': {
        'ru': '🎵 <b>Моя библиотека</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n',
        'en': '🎵 <b>My Library</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n',
        'uz': '🎵 <b>Mening kutubxonam</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n',
        'ua': '🎵 <b>Моя бібліотека</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n',
        'ar': '🎵 <b>مكتبتي</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n',
        'tr': '🎵 <b>Kütüphanem</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n',
    },
    'lib_empty': {
        'ru': 'Библиотека пуста.\nСоздай папку и добавляй треки!',
        'en': 'Library is empty.\nCreate a folder and add tracks!',
        'uz': 'Kutubxona bo\'sh.\nPapka yarating va treklar qo\'shing!',
        'ua': 'Бібліотека порожня.\nСтвори папку і додавай треки!',
        'ar': 'المكتبة فارغة.\nأنشئ مجلداً وأضف المقاطع!',
        'tr': 'Kütüphane boş.\nKlasör oluştur ve parça ekle!',
    },
    'lib_folders_count': {
        'ru': '📂 Папок: <b>{n}</b>\n\nВыбери папку:',
        'en': '📂 Folders: <b>{n}</b>\n\nChoose a folder:',
        'uz': '📂 Papkalar: <b>{n}</b>\n\nPapkani tanlang:',
        'ua': '📂 Папок: <b>{n}</b>\n\nОбери папку:',
        'ar': '📂 المجلدات: <b>{n}</b>\n\nاختر مجلداً:',
        'tr': '📂 Klasörler: <b>{n}</b>\n\nKlasör seçin:',
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
        'ru': '📁 <b>Создание папки</b>\n\nНапиши название новой папки:',
        'en': '📁 <b>Create folder</b>\n\nEnter the folder name:',
        'uz': '📁 <b>Papka yaratish</b>\n\nYangi papka nomini kiriting:',
        'ua': '📁 <b>Створення папки</b>\n\nНапиши назву нової папки:',
        'ar': '📁 <b>إنشاء مجلد</b>\n\nأدخل اسم المجلد الجديد:',
        'tr': '📁 <b>Klasör oluştur</b>\n\nYeni klasör adını girin:',
    },
    'folder_created': {
        'ru': '✅ Папка <b>«{name}»</b> создана!\n\nСкачай трек и нажми <b>📁 Сохранить в библиотеку</b>',
        'en': '✅ Folder <b>«{name}»</b> created!\n\nDownload a track and tap <b>📁 Save to library</b>',
        'uz': '✅ <b>«{name}»</b> papkasi yaratildi!\n\nTrekni yuklab oling va <b>📁 Kutubxonaga saqlash</b> tugmasini bosing',
        'ua': '✅ Папку <b>«{name}»</b> створено!\n\nЗавантаж трек і натисни <b>📁 Зберегти до бібліотеки</b>',
        'ar': '✅ تم إنشاء المجلد <b>«{name}»</b>!\n\nقم بتنزيل مقطع واضغط <b>📁 حفظ في المكتبة</b>',
        'tr': '✅ <b>«{name}»</b> klasörü oluşturuldu!\n\nBir parça indirin ve <b>📁 Kütüphaneye kaydet</b> düğmesine basın',
    },
    'video_received': {
        'ru': '🎬 <b>Видео получено</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nЧто хочешь сделать?',
        'en': '🎬 <b>Video received</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nWhat do you want to do?',
        'uz': '🎬 <b>Video qabul qilindi</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nNima qilmoqchisiz?',
        'ua': '🎬 <b>Відео отримано</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nЩо хочеш зробити?',
        'ar': '🎬 <b>تم استلام الفيديو</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nماذا تريد أن تفعل؟',
        'tr': '🎬 <b>Video alındı</b>  ⏱ {dur}\n━━━━━━━━━━━━━━━━━━━━━━\n\nNe yapmak istiyorsunuz?',
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
        'ru': '✅ <b>Трек определён!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{artist} — {title}</b>\n━━━━━━━━━━━━━━━━━━━━━━',
        'en': '✅ <b>Track detected!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{artist} — {title}</b>\n━━━━━━━━━━━━━━━━━━━━━━',
        'uz': '✅ <b>Trek aniqlandi!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{artist} — {title}</b>\n━━━━━━━━━━━━━━━━━━━━━━',
        'ua': '✅ <b>Трек визначено!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{artist} — {title}</b>\n━━━━━━━━━━━━━━━━━━━━━━',
        'ar': '✅ <b>تم التعرف على الأغنية!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{artist} — {title}</b>\n━━━━━━━━━━━━━━━━━━━━━━',
        'tr': '✅ <b>Parça tespit edildi!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🎵 <b>{artist} — {title}</b>\n━━━━━━━━━━━━━━━━━━━━━━',
    },
    'btn_download_full': {
        'ru': '⬇️ Скачать полную версию',
        'en': '⬇️ Download full version',
        'uz': '⬇️ To\'liq versiyani yuklab olish',
        'ua': '⬇️ Завантажити повну версію',
        'ar': '⬇️ تنزيل النسخة الكاملة',
        'tr': '⬇️ Tam sürümü indir',
    },
    'track_not_recognized': {
        'ru': '😔 <b>Трек не распознан</b>\n\nПопробуй видео с более чёткой музыкой.',
        'en': '😔 <b>Track not recognized</b>\n\nTry a video with clearer music.',
        'uz': '😔 <b>Trek aniqlanmadi</b>\n\nAniqroq musiqali video sinab ko\'ring.',
        'ua': '😔 <b>Трек не розпізнано</b>\n\nСпробуй відео з чіткішою музикою.',
        'ar': '😔 <b>لم يتم التعرف على الأغنية</b>\n\nجرب مقطع فيديو بموسيقى أوضح.',
        'tr': '😔 <b>Parça tanınamadı</b>\n\nDaha net müzikli bir video deneyin.',
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
    """Получить перевод по ключу и языку."""
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
        if row:
            return {'lang': row[0], 'is_new': row[1]}
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

def db_mark_not_new(uid: int):
    con = _db()
    try:
        cur = con.cursor()
        cur.execute("UPDATE users SET is_new=FALSE WHERE uid=%s", (uid,))
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
            result[fname] = [{'title': t[0], 'artist': t[1], 'duration': t[2], 'file_id': t[3]} for t in cur.fetchall()]
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
def is_url(tx): return bool(URL_PATTERN.search(tx))
def is_pinterest(tx): return 'pinterest.com' in tx or 'pin.it' in tx
def is_tiktok(tx): return 'tiktok.com' in tx
def is_spotify(tx): return 'spotify.com' in tx
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

def clean_search_query(text):
    """Убирает шумовые теги из поискового запроса."""
    q = re.sub(
        r'\s*[\(\[\{][^\)\]\}]*(slowed|reverb|sped up|nightcore|remix|edit|official|lyrics|video|hd|hq|4k|vevo)[^\)\]\}]*[\)\]\}]',
        '', text, flags=re.IGNORECASE
    )
    q = re.sub(r'\s*[\(\[\{][^\)\]\}]*$', '', q)
    q = ' '.join(q.split()).strip()
    return q if len(q) > 2 else text

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
        tx = track.get('title', ''); a = track.get('subtitle', '')
        return f"{a} {tx}".strip() if tx else None
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

def _search_similar(query, max_results=5):
    results = []
    for source in [f"scsearch{max_results}:{query}", f"ytsearch{max_results}:{query}"]:
        try:
            opts = {**BASE_OPTS, 'skip_download': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False)
                for e in info.get('entries', []):
                    if not e: continue
                    title = e.get('title', ''); url = e.get('url') or e.get('webpage_url', '')
                    if title and url:
                        results.append({'title': title, 'url': url, 'duration': e.get('duration', 0) or 0, 'uploader': e.get('uploader', '') or e.get('channel', '')})
                    if len(results) >= max_results: break
        except Exception as ex: log.warning(f"_search_similar: {ex}")
        if len(results) >= max_results: break
    seen = set(); unique = []
    for r in results:
        k = r['title'].lower()
        if k not in seen: seen.add(k); unique.append(r)
    return unique[:max_results]

def _extract_audio_for_shazam(video_path):
    out = video_path + '_shazam.mp3'
    ret = os.system(f'ffmpeg -y -i "{video_path}" -t 30 -vn -ar 44100 -ac 2 -b:a 128k "{out}" -loglevel quiet')
    return out if ret == 0 and os.path.exists(out) else None

def _trim_audio(src, start_sec, end_sec):
    out = src.replace('.mp3', f'_trim_{start_sec}_{end_sec or "end"}.mp3')
    dur_arg = f"-t {end_sec - start_sec}" if end_sec is not None else ""
    cmd = f'ffmpeg -y -i "{src}" -ss {start_sec} {dur_arg} -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
    ret = os.system(cmd)
    return out if ret == 0 and os.path.exists(out) else None

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

# ── Библиотека UI ─────────────────────────────────────────────────────────────
async def show_library(update_or_query, uid, lang, edit=False):
    folders = lib_get_user(uid)
    buttons = []
    if folders:
        for fname in folders:
            count = len(folders[fname])
            buttons.append([InlineKeyboardButton(f"📁 {fname}  ({count})", callback_data=f"lib_folder|{store_url(fname)}")])
    buttons.append([InlineKeyboardButton(t('btn_new_folder', lang), callback_data="lib_new_folder")])
    text = t('lib_title', lang)
    if folders:
        text += t('lib_folders_count', lang, n=len(folders))
    else:
        text += t('lib_empty', lang)
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
    buttons.append([
        InlineKeyboardButton("🗑 " + ("Удалить папку" if lang == 'ru' else "Delete folder" if lang == 'en' else "Klasörü sil" if lang == 'tr' else "O'chirish" if lang == 'uz' else "Видалити папку" if lang == 'ua' else "حذف المجلد"), callback_data=f"lib_del_folder|{store_url(folder)}"),
        InlineKeyboardButton(t('btn_back', lang), callback_data="lib_back"),
    ])
    empty_hint = {
        'ru': 'Папка пустая.\nСкачай трек и нажми 📁 Сохранить в библиотеку',
        'en': 'Folder is empty.\nDownload a track and tap 📁 Save to library',
        'uz': "Papka bo'sh.\nTrekni yuklab oling va 📁 Kutubxonaga saqlash tugmasini bosing",
        'ua': 'Папка порожня.\nЗавантаж трек і натисни 📁 Зберегти до бібліотеки',
        'ar': 'المجلد فارغ.\nقم بتنزيل مقطع واضغط 📁 حفظ في المكتبة',
        'tr': "Klasör boş.\nBir parça indirin ve 📁 Kütüphaneye kaydet'e basın",
    }
    text = f"📁 <b>{folder}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    if tracks:
        text += f"{'Треков' if lang=='ru' else 'Tracks' if lang=='en' else 'Treklar' if lang=='uz' else 'Треків' if lang=='ua' else 'المقاطع' if lang=='ar' else 'Parça'}: <b>{len(tracks)}</b>"
    else:
        text += empty_hint.get(lang, empty_hint['ru'])
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except: pass

# ── Поиск списка треков ───────────────────────────────────────────────────────
def _search_tracks_list(query, max_results=5):
    """Ищет несколько треков и возвращает список для выбора."""
    results = []
    q = clean_q(query)
    q_clean = clean_search_query(q)
    for source in [f"ytsearch{max_results}:{q}", f"scsearch{max_results}:{q_clean}"]:
        try:
            opts = {**BASE_OPTS, 'skip_download': True, 'extract_flat': True, 'quiet': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False)
                entries = info.get('entries', []) if info else []
                for e in entries:
                    if not e: continue
                    title = e.get('title', '')
                    url = e.get('url') or e.get('webpage_url', '')
                    dur = e.get('duration', 0) or 0
                    uploader = e.get('uploader') or e.get('channel', '')
                    if title and url and len(results) < max_results:
                        results.append({'title': title, 'url': url, 'duration': dur, 'uploader': uploader})
        except Exception as ex:
            log.warning(f"_search_tracks_list [{source}]: {ex}")
        if len(results) >= max_results:
            break
    seen = set(); unique = []
    for r in results:
        k = r['title'].lower()[:40]
        if k not in seen:
            seen.add(k); unique.append(r)
    return unique[:max_results]

# ── Поиск фильма/сериала/аниме через TMDB ────────────────────────────────────
def _search_media_tmdb(query):
    """Ищет фильм/сериал/аниме по названию через TMDB API."""
    if not TMDB_TOKEN:
        return None
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
    rating = best.get('vote_average', 0)
    votes = best.get('vote_count', 0)
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
    """Отправляет карточку фильма/сериала."""
    orig_line = f"\n🔤 <i>{result['original_title']}</i>" if result['original_title'] != result['title'] else ''
    caption = (
        f"{result['type']}  •  {result['year']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>{result['title']}</b>{orig_line}\n"
        f"⭐ {result['rating']:.1f}/10  ({result['vote_count']} голосов)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {result['overview']}"
    )
    if result['poster_url']:
        try:
            await message.reply_photo(photo=result['poster_url'], caption=caption, parse_mode="HTML")
            return
        except: pass
    await message.reply_text(caption, parse_mode="HTML")

# ── Команды ───────────────────────────────────────────────────────────────────
def lang_keyboard():
    """Клавиатура выбора языка."""
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
        # Первый запуск — показываем выбор языка
        lang = user_info.get('lang') or 'ru'
        await update.message.reply_text(
            t('welcome_new', lang, name=name),
            parse_mode="HTML",
            reply_markup=lang_keyboard()
        )
    else:
        # Повторный запуск — показываем меню на выбранном языке
        lang = user_info['lang']
        await update.message.reply_text(
            t('start_main', lang, name=name),
            parse_mode="HTML"
        )

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    await update.message.reply_text(
        t('choose_lang', lang),
        parse_mode="HTML",
        reply_markup=lang_keyboard()
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    help_texts = {
        'ru': (
            "📖 <b>Инструкция</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔗 TikTok / Pinterest → выбери Аудио или Видео\n"
            "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
            "🔍 <code>найти [исполнитель трек]</code>\n\n"
            "✂️ После скачивания:\n"
            "    <code>обрезать 0:30 0:45</code>\n"
            "    <code>обрезать до 1:30</code>\n"
            "    <code>обрезать с 0:30</code>\n\n"
            "📁 /library — личная библиотека\n"
            "🌐 /lang — сменить язык\n\n"
            "🎬 Пришли видеофайл до 20MB → Shazam распознает"
        ),
        'en': (
            "📖 <b>Help</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔗 TikTok / Pinterest → choose Audio or Video\n"
            "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
            "🔍 <code>find [artist track]</code>\n\n"
            "✂️ After downloading:\n"
            "    <code>trim 0:30 0:45</code>\n"
            "    <code>trim to 1:30</code>\n"
            "    <code>trim from 0:30</code>\n\n"
            "📁 /library — personal library\n"
            "🌐 /lang — change language\n\n"
            "🎬 Send video up to 20MB → Shazam recognizes"
        ),
        'uz': (
            "📖 <b>Qo'llanma</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔗 TikTok / Pinterest → Audio yoki Video tanlang\n"
            "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
            "🔍 <code>topish [ijrochi trek]</code>\n\n"
            "✂️ Yuklab olgandan keyin:\n"
            "    <code>kesish 0:30 0:45</code>\n\n"
            "📁 /library — shaxsiy kutubxona\n"
            "🌐 /lang — tilni o'zgartirish\n\n"
            "🎬 20MB gacha video yuboring → Shazam aniqlaydi"
        ),
        'ua': (
            "📖 <b>Інструкція</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔗 TikTok / Pinterest → обери Аудіо або Відео\n"
            "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
            "🔍 <code>знайти [виконавець трек]</code>\n\n"
            "✂️ Після завантаження:\n"
            "    <code>обрізати 0:30 0:45</code>\n\n"
            "📁 /library — особиста бібліотека\n"
            "🌐 /lang — змінити мову\n\n"
            "🎬 Надішли відео до 20MB → Shazam розпізнає"
        ),
        'ar': (
            "📖 <b>التعليمات</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔗 TikTok / Pinterest → اختر صوت أو فيديو\n"
            "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
            "🔍 <code>ابحث [فنان أغنية]</code>\n\n"
            "✂️ بعد التنزيل:\n"
            "    <code>قص 0:30 0:45</code>\n\n"
            "📁 /library — المكتبة الشخصية\n"
            "🌐 /lang — تغيير اللغة\n\n"
            "🎬 أرسل فيديو حتى 20MB → سيتعرف Shazam عليه"
        ),
        'tr': (
            "📖 <b>Yardım</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔗 TikTok / Pinterest → Ses veya Video seç\n"
            "▶️ YouTube / SoundCloud / Spotify → mp3\n\n"
            "🔍 <code>bul [sanatçı parça]</code>\n\n"
            "✂️ İndirdikten sonra:\n"
            "    <code>kırp 0:30 0:45</code>\n\n"
            "📁 /library — kişisel kütüphane\n"
            "🌐 /lang — dil değiştir\n\n"
            "🎬 20MB'a kadar video gönder → Shazam tanır"
        ),
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
            await safe_reply(update, "❌ " + ("Название слишком длинное (макс. 50 символов)." if lang == 'ru' else "Name too long (max 50 chars)."), parse_mode="HTML")
            return
        lib_create_folder(uid, folder_name)
        _user_state.pop(uid, None)
        await safe_reply(update, t('folder_created', lang, name=folder_name), parse_mode="HTML")
        await show_library(update, uid, lang)
        return

    # ── Ожидаем время обрезки MP3 файла ──────────────────────────────────────
    if state.get('action') == 'mp3_trim_input':
        audio_path = state.get('audio_path', '')
        vid_dur = state.get('dur', 0)
        if not os.path.exists(audio_path):
            _user_state.pop(uid, None)
            await safe_reply(update, "❌ Файл не найден. Пришли mp3 снова с подписью «обрежь».", parse_mode="HTML")
            return
        parts = text.strip().split()
        if len(parts) != 2:
            await safe_reply(update, "❌ Неверный формат.\n\nПример: <code>0:30 1:00</code> или <code>0:30 конец</code>", parse_mode="HTML")
            return
        start_sec = parse_time(parts[0])
        end_raw = parts[1].lower()
        end_sec = None if end_raw in ('конец', 'end', 'до конца') else parse_time(end_raw)
        if start_sec is None:
            await safe_reply(update, "❌ Неверный формат времени. Пример: <code>0:30 1:00</code>", parse_mode="HTML")
            return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, "❌ Конец должен быть больше начала.", parse_mode="HTML")
            return
        if end_sec is not None and vid_dur and end_sec > vid_dur:
            end_sec = vid_dur
        msg = await safe_reply(update, "✂️ <b>Обрезаю...</b>", parse_mode="HTML")
        trimmed = await loop.run_in_executor(executor, _trim_audio, audio_path, start_sec, end_sec)
        if not trimmed:
            await safe_edit(msg, "❌ Не удалось обрезать. Убедись что ffmpeg установлен.", parse_mode="HTML")
            return
        s_fmt = fmt_dur(start_sec)
        e_fmt = fmt_dur(end_sec) if end_sec is not None else "конец"
        trim_info = _trim_state.get(uid, {})
        title = trim_info.get('title', 'track')
        performer = trim_info.get('uploader', '')
        await safe_edit(msg, f"✅ Готово! ⏱ {s_fmt} → {e_fmt}\n📤 Отправляю...", parse_mode="HTML")
        with open(trimmed, 'rb') as f:
            await update.message.reply_audio(f, title=f"{title} [{s_fmt}-{e_fmt}]", performer=performer)
        _user_state.pop(uid, None)
        try: await msg.delete()
        except: pass
        try: os.remove(trimmed)
        except: pass
        # Исходный файл оставляем — вдруг захочет ещё раз обрезать
        return

    # ── Обрезка треков ────────────────────────────────────────────────────────
    trim_kw = t('trim_keyword', lang)
    m_range = re.match(rf'^{re.escape(trim_kw)}\s+(\S+)\s+(\S+)\s*$', lower)
    m_to    = re.match(rf'^{re.escape(trim_kw)}\s+(?:до|to|gacha|до|إلى|kadar)\s+(\S+)\s*$', lower)
    m_from  = re.match(rf'^{re.escape(trim_kw)}\s+(?:с|from|dan|від|من|den)\s+(\S+)\s*$', lower)

    if m_range or m_to or m_from:
        state = _trim_state.get(uid)
        if not state or not os.path.exists(state.get('file', '')):
            await safe_reply(update, t('trim_no_track', lang), parse_mode="HTML")
            return
        if m_range:
            start_sec = parse_time(m_range.group(1)); end_sec = parse_time(m_range.group(2))
        elif m_to:
            start_sec = 0; end_sec = parse_time(m_to.group(1))
        else:
            start_sec = parse_time(m_from.group(1)); end_sec = None
        if start_sec is None:
            await safe_reply(update, "❌ " + ("Неверный формат. Пример: обрезать 0:30 0:45" if lang == 'ru' else "Invalid format. Example: trim 0:30 0:45"), parse_mode="HTML")
            return
        if end_sec is not None and end_sec <= start_sec:
            await safe_reply(update, "❌ " + ("Конец должен быть больше начала." if lang == 'ru' else "End must be greater than start."), parse_mode="HTML")
            return
        msg = await safe_reply(update, t('trimming', lang), parse_mode="HTML")
        trimmed = await loop.run_in_executor(executor, _trim_audio, state['file'], start_sec, end_sec)
        if not trimmed:
            await safe_edit(msg, "❌ ffmpeg error", parse_mode="HTML"); return
        s_fmt = fmt_dur(start_sec); e_fmt = fmt_dur(end_sec) if end_sec else "end"
        await safe_edit(msg, t('trim_done', lang, s=s_fmt, e=e_fmt), parse_mode="HTML")
        with open(trimmed, 'rb') as f:
            await update.message.reply_audio(f, title=f"{state['title']} [{s_fmt}-{e_fmt}]", performer=state.get('uploader', ''))
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
        resolved = await loop.run_in_executor(executor, resolve_url, text)
        tiktok_url = resolved if 'tiktok.com' in resolved else text
        await safe_edit(msg, t('shazam_detecting', lang), parse_mode="HTML")
        try:
            shazam_q = await asyncio.wait_for(loop.run_in_executor(executor, _shazam_identify_tiktok, tiktok_url), timeout=45)
        except asyncio.TimeoutError: shazam_q = None
        vid_key = store_url(tiktok_url)
        if shazam_q:
            aud_key = store_url(shazam_q)
            track_line = f"\n\n🎵 <b>{shazam_q}</b>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"), InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}")]])
        else:
            try: meta = await asyncio.wait_for(loop.run_in_executor(executor, _get_track_meta, tiktok_url), timeout=20)
            except: meta = None
            if meta and meta.get('query'):
                aud_key = store_url(meta['query'])
                track_line = f"\n\n🎵 <b>{meta['artist']} — {meta['title']}</b>"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{aud_key}"), InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}")]])
            else:
                track_line = ""
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ mp3", callback_data=f"audio|{vid_key}"), InlineKeyboardButton("🎬 mp4", callback_data=f"video|{vid_key}")]])
        await safe_edit(msg, f"📱 <b>TikTok</b>{track_line}\n\n━━━━━━━━━━━━━━━━━━━━━━\n{t('choose_format', lang)}", parse_mode="HTML", reply_markup=kb)
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
        await safe_edit(msg, f"📌 <b>Pinterest</b>{track_line}\n\n━━━━━━━━━━━━━━━━━━━━━━\n{t('choose_format', lang)}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([buttons]))
        return

    # ── YouTube / SoundCloud / Spotify / поиск ────────────────────────────────
    query = text if url_match else text[len(search_kw):].strip()
    ck = cache_key(query)
    if ck in cache:
        cached = cache[ck]
        if os.path.exists(cached.get('file', '')):
            msg = await safe_reply(update, t('cache_instant', lang), parse_mode="HTML")
            with open(cached['file'], 'rb') as f:
                await update.message.reply_audio(f, title=cached['title'], performer=cached['uploader'])
            if msg:
                try: await msg.delete()
                except: pass
            return
        del cache[ck]

    # Для текстового поиска — показываем список 5 вариантов
    if search_match and not url_match:
        msg = await safe_reply(update, f"🔍 <b>Ищу варианты...</b>", parse_mode="HTML")
        if not msg: return
        try:
            tracks = await asyncio.wait_for(
                loop.run_in_executor(executor, _search_tracks_list, query, 5), timeout=30)
        except asyncio.TimeoutError:
            tracks = []
        if not tracks:
            await safe_edit(msg, t('not_found', lang), parse_mode="HTML"); return
        # Строим список с кнопками
        lines = []
        buttons = []
        for i, tr in enumerate(tracks, 1):
            dur = fmt_dur(tr['duration']) if tr['duration'] else ''
            dur_str = f"  ⏱{dur}" if dur else ''
            lines.append(f"{i}. <b>{tr['title']}</b>\n    <i>{tr['uploader']}</i>{dur_str}")
            t_key = store_url(tr['url'])
            buttons.append([InlineKeyboardButton(f"⬇️ {i}. {tr['title'][:35]}", callback_data=f"audio|{t_key}")])
        list_text = f"🎵 <b>Результаты поиска:</b> «{query}»\n━━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(lines)
        await safe_edit(msg, list_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Для ссылки — скачиваем сразу
    display = "🔗"
    msg = await safe_reply(update, t('searching', lang, q=display), parse_mode="HTML")
    if not msg: return

    try:
        result = await asyncio.wait_for(loop.run_in_executor(executor, _download_audio, query), timeout=90)
    except asyncio.TimeoutError:
        await safe_edit(msg, t('timeout', lang), parse_mode="HTML"); return

    if not result or not os.path.exists(result.get('file', '')):
        await safe_edit(msg, t('not_found', lang), parse_mode="HTML"); return

    try:
        title = result['title']; uploader = result['uploader']
        save_key = store_url(json.dumps({'title': title, 'artist': uploader, 'duration': result['duration']}, ensure_ascii=False))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t('btn_save_lib', lang), callback_data=f"lib_save|{save_key}")],
        ])
        await safe_edit(msg, t('found', lang, title=title, uploader=uploader, dur=fmt_dur(result['duration']), src=src_emoji(result['source'])), parse_mode="HTML")
        sent = None
        with open(result['file'], 'rb') as f:
            sent = await update.message.reply_audio(f, title=title, performer=uploader)
        if sent and sent.audio:
            _trim_state[uid] = {'file': result['file'], 'title': title, 'uploader': uploader, 'file_id': sent.audio.file_id, 'duration': result['duration']}
        try: os.remove(result['file'])
        except: pass
        await update.message.reply_text(f"🎵 <b>{title}</b>", parse_mode="HTML", reply_markup=kb)
        save_cache(ck, result)
        try: await msg.delete()
        except: pass
    except Exception as ex:
        log.error(f"handle_message: {ex}")
        await safe_edit(msg, f"⚠️ <code>{ex}</code>", parse_mode="HTML")

# ── Callback кнопок ───────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    await cb.answer()
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    data = cb.data
    loop = asyncio.get_event_loop()

    # ── Установка языка ───────────────────────────────────────────────────────
    if data.startswith("setlang|"):
        new_lang = data.split("|", 1)[1]
        if new_lang not in LANGS: return
        db_set_lang(uid, new_lang)
        flag, lname = LANGS[new_lang]
        try: await cb.edit_message_text(t('lang_set', new_lang), parse_mode="HTML")
        except: pass
        name = update.effective_user.first_name or "friend"
        await cb.message.reply_text(t('start_main', new_lang, name=name), parse_mode="HTML")
        return

    # ── Shazam из видео ───────────────────────────────────────────────────────
    if data.startswith("vid_shazam|"):
        vid_path = get_stored(data.split("|", 1)[1])
        if not os.path.exists(vid_path):
            await cb.answer("❌ File not found", show_alert=True); return
        try: await cb.edit_message_text(t('shazam_detecting', lang), parse_mode="HTML")
        except: pass
        aud_path = await loop.run_in_executor(executor, _extract_audio_for_shazam, vid_path)
        if not aud_path:
            try: await cb.edit_message_text("⚠️ ffmpeg error", parse_mode="HTML")
            except: pass
            return
        try:
            track = await asyncio.wait_for(_recognize_shazam(aud_path), timeout=30)
        except asyncio.TimeoutError: track = None
        finally:
            if os.path.exists(aud_path):
                try: os.remove(aud_path)
                except: pass
        if os.path.exists(vid_path):
            try: os.remove(vid_path)
            except: pass
        _user_state.pop(uid, None)
        if not track:
            try: await cb.edit_message_text(t('track_not_recognized', lang), parse_mode="HTML")
            except: pass
            return
        q_key = store_url(track['query'])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_download_full', lang), callback_data=f"audio|{q_key}")]])
        try:
            await cb.edit_message_text(t('track_detected', lang, artist=track['artist'], title=track['title']), parse_mode="HTML", reply_markup=kb)
        except: pass
        return

    if data.startswith("vid_trim|"):
        vid_path = get_stored(data.split("|", 1)[1])
        if not os.path.exists(vid_path):
            await cb.answer("❌ File not found", show_alert=True); return
        state = _user_state.get(uid, {})
        vid_dur = state.get('vid_dur', 0)
        _user_state[uid] = {'action': 'trim_input', 'vid_path': vid_path, 'vid_dur': vid_dur}
        trim_prompts = {
            'ru': f"✂️ <b>Обрезка</b>  ⏱ {fmt_dur(vid_dur)}\n\nНапиши: <code>начало конец</code>\nПример: <code>0:05 0:10</code>",
            'en': f"✂️ <b>Trim</b>  ⏱ {fmt_dur(vid_dur)}\n\nWrite: <code>start end</code>\nExample: <code>0:05 0:10</code>",
            'uz': f"✂️ <b>Kesish</b>  ⏱ {fmt_dur(vid_dur)}\n\nYozing: <code>boshlanish tugash</code>\nMisol: <code>0:05 0:10</code>",
            'ua': f"✂️ <b>Обрізка</b>  ⏱ {fmt_dur(vid_dur)}\n\nНапиши: <code>початок кінець</code>\nПриклад: <code>0:05 0:10</code>",
            'ar': f"✂️ <b>قص</b>  ⏱ {fmt_dur(vid_dur)}\n\nاكتب: <code>البداية النهاية</code>\nمثال: <code>0:05 0:10</code>",
            'tr': f"✂️ <b>Kırp</b>  ⏱ {fmt_dur(vid_dur)}\n\nYaz: <code>başlangıç bitiş</code>\nÖrnek: <code>0:05 0:10</code>",
        }
        try:
            await cb.edit_message_text(
                trim_prompts.get(lang, trim_prompts['ru']),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_back', lang), callback_data=f"vid_back|{store_url(vid_path)}")]])
            )
        except: pass
        return

    if data.startswith("vid_back|"):
        vid_path = get_stored(data.split("|", 1)[1])
        state = _user_state.get(uid, {}); vid_dur = state.get('vid_dur', 0)
        _user_state[uid] = {'action': 'video_menu', 'vid_path': vid_path, 'vid_dur': vid_dur}
        vid_key = store_url(vid_path)
        try:
            await cb.edit_message_text(
                t('video_received', lang, dur=fmt_dur(vid_dur)),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_find_track', lang), callback_data=f"vid_shazam|{vid_key}"), InlineKeyboardButton(t('btn_trim_video', lang), callback_data=f"vid_trim|{vid_key}")]])
            )
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
                cmd = f'ffmpeg -y -i "{vid_path}" -ss {start_sec} {dur_arg} -vn -acodec libmp3lame -q:a 2 "{out}" -loglevel quiet'
            else:
                out = tmpfile(f"trim_{uid}_{start_sec}_{end_sec or 'end'}.mp4")
                cmd = f'ffmpeg -y -i "{vid_path}" -ss {start_sec} {dur_arg} -c:v libx264 -c:a aac -preset fast "{out}" -loglevel quiet'
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
        try:
            await cb.edit_message_text(t('trim_done', lang, s=s_str, e=e_str), parse_mode="HTML")
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
            await cb.edit_message_text(
                t('create_folder_prompt', lang), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('btn_back', lang), callback_data="lib_back")]])
            )
        except: pass
        return
    if data.startswith("lib_folder|"):
        folder = get_stored(data.split("|", 1)[1])
        await show_folder(cb, uid, lang, folder); return
    if data.startswith("lib_play|"):
        _, folder_key, idx_str = data.split("|")
        folder = get_stored(folder_key); idx = int(idx_str)
        folders = lib_get_user(uid); tracks = folders.get(folder, [])
        if idx >= len(tracks):
            await cb.answer("Not found", show_alert=True); return
        track = tracks[idx]
        try:
            await cb.answer("📤")
            await cb.message.reply_audio(audio=track['file_id'], title=track['title'], performer=track.get('artist', ''))
        except Exception as ex:
            log.error(f"lib_play: {ex}"); await cb.answer("❌ Error", show_alert=True)
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
            try:
                await cb.edit_message_text(
                    t('lib_empty', lang), parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📁 /library", callback_data="lib_back")]])
                )
            except: pass
            return
        buttons = []
        for fname in folders:
            fkey = store_url(fname)
            buttons.append([InlineKeyboardButton(f"📁 {fname} ({len(folders[fname])})", callback_data=f"lib_save_to|{fkey}|{track_key}")])
        buttons.append([InlineKeyboardButton(t('btn_back', lang), callback_data="lib_cancel_save")])
        try:
            await cb.edit_message_text(t('btn_save_lib', lang), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        except: pass
        return
    if data == "lib_cancel_save":
        try: await cb.delete_message()
        except: pass
        return
    if data.startswith("lib_save_to|"):
        _, folder_key, track_key = data.split("|")
        folder = get_stored(folder_key); track_meta_str = get_stored(track_key)
        state = _trim_state.get(uid, {}); file_id = state.get('file_id')
        if not file_id:
            await cb.answer("❌ file_id not found. Redownload track.", show_alert=True); return
        try: track_meta = json.loads(track_meta_str)
        except: track_meta = {'title': 'Unknown', 'artist': '', 'duration': 0}
        added = lib_add_track(uid, folder, {'title': track_meta.get('title', ''), 'artist': track_meta.get('artist', ''), 'duration': track_meta.get('duration', 0), 'file_id': file_id})
        await cb.answer(f"✅ Saved to «{folder}»" if added else f"ℹ️ Already in «{folder}»")
        try: await cb.delete_message()
        except: pass
        return

    # ── Похожие / исполнитель ─────────────────────────────────────────────────
    if '|' not in data: return
    action, key = data.split('|', 1)
    value = get_stored(key)

    if action in ('similar', 'artist'):
        search_q = value if action == 'similar' else f"{value} best songs"
        try: await cb.edit_message_text("🔍 ...", parse_mode="HTML")
        except: pass
        tracks = await loop.run_in_executor(executor, _search_similar, search_q)
        if not tracks:
            try: await cb.edit_message_text(t('not_found', lang), parse_mode="HTML")
            except: pass
            return
        buttons = []; lines = []
        for i, tr in enumerate(tracks, 1):
            lines.append(f"{i}. <b>{tr['title']}</b> — {tr['uploader']} ⏱{fmt_dur(tr['duration'])}")
            buttons.append([InlineKeyboardButton(f"⬇️ {i}. {tr['title'][:30]}", callback_data=f"audio|{store_url(tr['url'])}")])
        header = t('btn_similar', lang) if action == 'similar' else t('btn_artist', lang)
        try:
            await cb.edit_message_text(f"<b>{header}:</b>\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as ex: log.warning(f"similar: {ex}")
        return

    # ── Скачать аудио / видео ─────────────────────────────────────────────────
    emoji = '🎵' if 'audio' in action else '🎬'
    try: await cb.edit_message_text(f"{emoji} ...", parse_mode="HTML")
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
        try:
            await cb.edit_message_text(
                t('found', lang, title=title, uploader=uploader, dur=fmt_dur(result['duration']), src=src_emoji(result['source'])),
                parse_mode="HTML"
            )
        except: pass
        if result['type'] == 'audio':
            similar_key = store_url(f"{uploader} {title}"); artist_key = store_url(uploader)
            save_key = store_url(json.dumps({'title': title, 'artist': uploader, 'duration': result['duration']}, ensure_ascii=False))
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t('btn_similar', lang), callback_data=f"similar|{similar_key}"), InlineKeyboardButton(t('btn_artist', lang), callback_data=f"artist|{artist_key}")],
                [InlineKeyboardButton(t('btn_save_lib', lang), callback_data=f"lib_save|{save_key}")],
            ])
            sent = None
            with open(result['file'], 'rb') as f:
                sent = await cb.message.reply_audio(f, title=title, performer=uploader)
            if sent and sent.audio:
                _trim_state[uid] = {'file': result['file'], 'title': title, 'uploader': uploader, 'file_id': sent.audio.file_id, 'duration': result['duration']}
            try: os.remove(result['file'])
            except: pass
            await cb.message.reply_text(f"🎵 <b>{title}</b>", parse_mode="HTML", reply_markup=kb)
        else:
            with open(result['file'], 'rb') as f:
                await cb.message.reply_video(f, caption=f"🎬 <b>{title}</b>", parse_mode="HTML")
            try: os.remove(result['file'])
            except: pass
        save_cache(cache_key(value), result)
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

    # Если написали "найти" — ищем фильм/сериал через TMDB
    if 'найти' in caption or 'find' in caption:
        msg = await safe_reply(update, "🔍 <b>Ищу в базе фильмов...</b>", parse_mode="HTML")
        if not TMDB_TOKEN:
            await safe_edit(msg,
                "⚠️ <b>TMDB не настроен</b>\n\n"
                "Чтобы искать фильмы и сериалы по фото/видео:\n"
                "1. Зарегистрируйся на <b>themoviedb.org</b>\n"
                "2. Настройки → API → Request API Key\n"
                "3. Скопируй <b>API Read Access Token</b>\n"
                "4. Вставь в <code>TMDB_TOKEN = \"...\"</code> в боте",
                parse_mode="HTML")
            return
        # Получаем название из подписи или имени файла
        query = re.sub(r'найти|find', '', caption, flags=re.IGNORECASE).strip()
        if not query:
            fn = getattr(video, 'file_name', '') or ''
            query = os.path.splitext(fn)[0].replace('_', ' ').replace('-', ' ').strip()
        if not query:
            await safe_edit(msg,
                "😔 Не могу определить название.\n\nПришли фото/видео с подписью:\n"
                "<code>найти Inception</code>", parse_mode="HTML")
            return
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, _search_media_tmdb, query)
        try: await msg.delete()
        except: pass
        if not result:
            await update.message.reply_text("😔 Ничего не найдено. Попробуй уточнить название.", parse_mode="HTML")
            return
        await _send_tmdb_result(update.message, result)
        return

    # Стандартная обработка — меню видео
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

# ── Обработчик фото ───────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фото + 'найти' → ищем фильм/сериал через TMDB."""
    uid = update.effective_user.id
    caption = (update.message.caption or '').strip().lower()
    if 'найти' not in caption and 'find' not in caption:
        return  # без подписи — игнорируем

    msg = await safe_reply(update, "🔍 <b>Ищу в базе фильмов...</b>", parse_mode="HTML")
    if not TMDB_TOKEN:
        await safe_edit(msg,
            "⚠️ <b>TMDB не настроен</b>\n\n"
            "Чтобы искать фильмы и сериалы по фото:\n"
            "1. Зарегистрируйся на <b>themoviedb.org</b>\n"
            "2. Настройки → API → Request API Key\n"
            "3. Скопируй <b>API Read Access Token</b>\n"
            "4. Вставь в <code>TMDB_TOKEN = \"...\"</code> в боте",
            parse_mode="HTML")
        return

    query = re.sub(r'найти|find', '', caption, flags=re.IGNORECASE).strip()
    if not query:
        await safe_edit(msg,
            "😔 Напиши название рядом с фото.\n\nПример:\n"
            "<i>(прикрепи постер)</i> + подпись <code>найти Inception</code>",
            parse_mode="HTML")
        return

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, _search_media_tmdb, query)
    try: await msg.delete()
    except: pass
    if not result:
        await update.message.reply_text("😔 Ничего не найдено. Уточни название.", parse_mode="HTML")
        return
    await _send_tmdb_result(update.message, result)

# ── Обработчик MP3 файла ──────────────────────────────────────────────────────
async def handle_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MP3 файл + 'обрежь' → спрашиваем время и режем."""
    uid = update.effective_user.id
    audio = update.message.audio or update.message.document
    if not audio: return

    # Проверяем что это аудио файл
    mime = getattr(audio, 'mime_type', '') or ''
    fname = getattr(audio, 'file_name', '') or ''
    if not (mime.startswith('audio/') or fname.lower().endswith('.mp3')):
        return

    caption = (update.message.caption or '').strip().lower()
    has_trim = any(w in caption for w in ['обрежь', 'обрезать', 'trim', 'cut', 'обрезай'])

    if not has_trim:
        return  # без слова "обрежь" — игнорируем

    if audio.file_size and audio.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("⚠️ Файл больше 50MB.")
        return

    msg = await safe_reply(update, "⏳ <b>Скачиваю аудио...</b>", parse_mode="HTML")
    if not msg: return

    audio_path = tmpfile(f"mp3_{uid}_{update.message.message_id}.mp3")
    try:
        file = await context.bot.get_file(audio.file_id)
        await file.download_to_drive(audio_path)
    except Exception as ex:
        await safe_edit(msg, f"⚠️ Не удалось скачать: {ex}", parse_mode="HTML")
        return

    # Получаем длительность через ffprobe
    import subprocess
    dur_sec = 0
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', audio_path],
            capture_output=True, text=True, timeout=10
        )
        dur_sec = float(json.loads(r.stdout).get('format', {}).get('duration', 0))
    except: pass

    title = getattr(audio, 'title', '') or os.path.splitext(fname)[0] or 'track'
    performer = getattr(audio, 'performer', '') or ''

    # Сохраняем файл для обрезки
    _trim_state[uid] = {
        'file': audio_path,
        'title': title,
        'uploader': performer,
        'file_id': audio.file_id,
        'duration': int(dur_sec),
    }
    _user_state[uid] = {'action': 'mp3_trim_input', 'audio_path': audio_path, 'dur': int(dur_sec)}

    dur_str = fmt_dur(int(dur_sec)) if dur_sec else "?"
    await safe_edit(
        msg,
        f"🎵 <b>{title}</b>  ⏱ {dur_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✂️ Напиши какую часть оставить:\n\n"
        f"  <code>0:30 1:00</code> — с 30 сек до 1 мин\n"
        f"  <code>0:30 конец</code> — с 30 сек до конца\n"
        f"  <code>0 0:45</code> — первые 45 сек",
        parse_mode="HTML"
    )

# ── Запуск ────────────────────────────────────────────────────────────────────
app = ApplicationBuilder().token(TOKEN).build()
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
if not os.path.exists('cookies.txt'): log.warning("cookies.txt не найден.")
app.run_polling(drop_pending_updates=True)