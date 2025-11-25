import os
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from video_converter import convert_video_to_mp4
from text_generator import generate_post_from_transcription
import httpx

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Отключаем избыточные логи от httpx (успешные HTTP запросы)
# Оставляем только ошибки (WARNING и выше)
logging.getLogger('httpx').setLevel(logging.WARNING)

# Также отключаем избыточные логи от httpcore (низкоуровневая библиотека httpx)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# Вспомогательная функция для безопасного редактирования сообщений
async def safe_edit_text(message, text, **kwargs):
    """Безопасно редактирует текст сообщения, игнорируя MessageNotModified"""
    try:
        await message.edit_text(text, **kwargs)
    except Exception as e:
        # Проверяем, является ли это ошибкой "MessageNotModified"
        error_msg = str(e).lower()
        if 'message is not modified' in error_msg or 'not modified' in error_msg:
            # Сообщение уже имеет такой же текст - это нормально, просто игнорируем
            pass
        else:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            raise

# Вспомогательная функция для создания клавиатуры с кнопкой "Главное меню"
def get_main_menu_keyboard():
    """Создает клавиатуру с кнопкой 'Главное меню'"""
    keyboard = [
        [
            InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Получаем токены из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Настройки для локального Bot API сервера (опционально)
# Если используется локальный Bot API сервер, укажите его URL
# Например: http://localhost:8081 или http://your-server:8081
TELEGRAM_LOCAL_API_URL = os.getenv('TELEGRAM_LOCAL_API_URL')  # Опционально

# URL для Web App загрузки видео (опционально)
# Например: https://my-domain.com/upload
VIDEO_WEBAPP_URL = os.getenv('VIDEO_WEBAPP_URL')  # Опционально

# Путь к папке converted в webapp (для веб-доступа к сконвертированным видео)
WEBAPP_CONVERTED_DIR = os.getenv('WEBAPP_CONVERTED_DIR', 'webapp/converted')  # Относительно корня проекта

# Отладочное логирование для проверки значений
if TELEGRAM_LOCAL_API_URL:
    logger.info(f"DEBUG: TELEGRAM_LOCAL_API_URL из .env: '{TELEGRAM_LOCAL_API_URL}'")
    logger.info(f"DEBUG: Длина TELEGRAM_LOCAL_API_URL: {len(TELEGRAM_LOCAL_API_URL)}")
    logger.info(f"DEBUG: TELEGRAM_BOT_TOKEN начинается с: '{TELEGRAM_BOT_TOKEN[:15] if TELEGRAM_BOT_TOKEN else 'None'}...'")
    # Проверяем, не попал ли токен в URL
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in TELEGRAM_LOCAL_API_URL:
        logger.error(f"ОШИБКА: Токен бота обнаружен в TELEGRAM_LOCAL_API_URL!")
        logger.error(f"TELEGRAM_LOCAL_API_URL: '{TELEGRAM_LOCAL_API_URL}'")
        raise ValueError("Токен бота не должен быть в TELEGRAM_LOCAL_API_URL! Проверьте файл .env")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в .env файле")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не установлен в .env файле")

# Определяем лимиты в зависимости от типа API
if TELEGRAM_LOCAL_API_URL:
    # Локальный Bot API: до 2GB для скачивания и отправки
    MAX_DOWNLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    logger.info(f"Используется локальный Bot API: {TELEGRAM_LOCAL_API_URL}")
else:
    # Стандартный Bot API: 20MB для скачивания, 50MB для отправки
    MAX_DOWNLOAD_SIZE = 20 * 1024 * 1024  # 20MB
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
    logger.info("Используется стандартный Telegram Bot API")

# GPT_ASSISTANT_ID не обязателен при запуске, но нужен для работы генератора
GPT_ASSISTANT_ID = os.getenv('GPT_ASSISTANT_ID')
GPT_ASSISTANT_ID_VIDEOS = os.getenv('GPT_ASSISTANT_ID_VIDEOS')  # Для постов роликов на платформе

if not GPT_ASSISTANT_ID:
    logger.warning("GPT_ASSISTANT_ID не установлен. Функция генерации поста для вебинара будет недоступна.")
if not GPT_ASSISTANT_ID_VIDEOS:
    logger.warning("GPT_ASSISTANT_ID_VIDEOS не установлен. Функция генерации поста для роликов будет недоступна.")

# Создаем директории для работы
Path("downloads").mkdir(exist_ok=True)
Path("converted").mkdir(exist_ok=True)

# Словарь для отслеживания активных конвертаций
# Ключ: (user_id, file_id), Значение: {'status_message': Message, 'file_path': str, 'output_path': str}
active_conversions = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = (
        "👋 Привет! Я бот-помощник для работы.\n\n"
        "Выберите функцию:\n\n"
        "📹 **Конвертер** - конвертирует видео в MP4 1920x1080\n"
        "✍️ **Генерация** - создает текст поста из транскрибации\n\n"
        "Нажмите на кнопку ниже, чтобы начать:"
    )
    
    # Создаем клавиатуру с кнопками
    keyboard = [
        [
            InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
            InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
        ],
        [
            InlineKeyboardButton("🎬 Видео", callback_data="list_converted_videos")
        ]
    ]
    
    # Добавляем кнопку загрузки видео через WebApp, если URL настроен
    if VIDEO_WEBAPP_URL:
        keyboard.append([
            InlineKeyboardButton("🎬 Загрузить видео", web_app=WebAppInfo(url=VIDEO_WEBAPP_URL))
        ])
        logger.info(f"Добавлена кнопка WebApp для загрузки видео: {VIDEO_WEBAPP_URL}")
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Сбрасываем режим при старте
    context.user_data['mode'] = None


async def reset_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset - сбрасывает выбранный режим"""
    context.user_data['mode'] = None
    context.user_data['post_type'] = None
    context.user_data['convert_method'] = None
    
    keyboard = [
        [
            InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
            InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
        ]
    ]
    
    # Добавляем кнопку загрузки видео через WebApp, если URL настроен
    if VIDEO_WEBAPP_URL:
        keyboard.append([
            InlineKeyboardButton("🎬 Загрузить видео", web_app=WebAppInfo(url=VIDEO_WEBAPP_URL))
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔄 Режим сброшен. Выберите функцию:",
        reply_markup=reply_markup
    )


def _format_videos_post(content_parts: dict) -> str:
    """
    Форматирует ответ второго ассистента (ролики) в одно сообщение
    с отступами между темами и выделением подтем жирным
    
    Args:
        content_parts: Словарь с частями ответа
    
    Returns:
        Отформатированный текст для отправки одним сообщением
    """
    import re
    
    parts = []
    
    # Собираем все части с отступами
    if content_parts.get('webinar_name'):
        parts.append(content_parts['webinar_name'])
    
    if content_parts.get('description'):
        parts.append(content_parts['description'])
    
    if content_parts.get('timestamps'):
        parts.append(content_parts['timestamps'])
    
    if content_parts.get('post'):
        parts.append(content_parts['post'])
    
    # Объединяем все части с двойными отступами между темами
    formatted_text = '\n\n'.join(parts)
    
    # Выделяем подтемы жирным текстом
    # Ищем строки, которые начинаются с цифры, буквы или маркера и заканчиваются двоеточием
    # Это обычно подтемы
    
    # Выделяем подтемы в формате "1. Тема", "2. Тема" и т.д.
    formatted_text = re.sub(
        r'^(\d+\.\s+[А-ЯЁA-Z][^:\n]{0,80}):?',
        r'*\1*',
        formatted_text,
        flags=re.MULTILINE
    )
    
    # Выделяем подтемы с маркерами "- Тема:", "• Тема:"
    formatted_text = re.sub(
        r'^([\-\•]\s+[А-ЯЁA-Z][^:\n]{0,80}):?',
        r'*\1*',
        formatted_text,
        flags=re.MULTILINE
    )
    
    # Выделяем подтемы, которые начинаются с заглавной буквы и заканчиваются двоеточием
    formatted_text = re.sub(
        r'^([А-ЯЁA-Z][^:\n]{3,80}):',
        r'*\1:*',
        formatted_text,
        flags=re.MULTILINE
    )
    
    # Выделяем подтемы в формате "**Тема:**" (если GPT уже отформатировал)
    formatted_text = re.sub(
        r'\*\*([^*]+):\*\*',
        r'*\1:*',
        formatted_text
    )
    
    # Убираем двойное выделение
    while '**' in formatted_text:
        formatted_text = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', formatted_text)
    
    return formatted_text


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"🔍 Обработка callback: {query.data}")
    
    if query.data == "mode_converter":
        context.user_data['mode'] = 'converter'
        # Показываем список видео из папки upload
        try:
            from pathlib import Path
            
            # Путь к папке upload (videos) в webapp
            videos_dir = Path("webapp/videos")
            if not videos_dir.exists():
                videos_dir = Path("webapp/videos")
            
            video_files = []
            if videos_dir.exists():
                for file_path in videos_dir.iterdir():
                    if file_path.is_file():
                        ext = file_path.suffix.lower()
                        if ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv', '.m4v', '.3gp']:
                            file_size = file_path.stat().st_size
                            video_files.append({
                                'name': file_path.name,
                                'size': file_size,
                                'path': str(file_path)
                            })
            
            if video_files:
                # Сортируем по имени
                video_files.sort(key=lambda x: x['name'])
                
                message = "📹 **Выберите видео для конвертации:**\n\n"
                keyboard = []
                
                # Показываем максимум 50 файлов (ограничение Telegram)
                for i, video in enumerate(video_files[:50]):
                    size_mb = video['size'] / 1024 / 1024
                    button_text = f"📹 {video['name'][:30]}{'...' if len(video['name']) > 30 else ''} ({size_mb:.1f}MB)"
                    keyboard.append([
                        InlineKeyboardButton(button_text, callback_data=f"select_video:{video['name']}")
                    ])
                
                keyboard.append([
                    InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                ])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                message = (
                    "📹 **Режим: Конвертер**\n\n"
                    "В папке upload нет видео файлов.\n\n"
                    "Отправьте мне:\n"
                    "• 📹 **Видео** (до 2GB) - отправьте как видео, не как файл\n"
                    "• 🔗 **Ссылку на видео** - прямая ссылка на видео файл\n\n"
                    "Или загрузите видео через WebApp."
                )
                keyboard = [
                    [
                        InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка видео: {e}", exc_info=True)
            message = (
                "📹 **Режим: Конвертер**\n\n"
                "Отправьте мне:\n"
                "• 📹 **Видео** (до 2GB) - отправьте как видео, не как файл\n"
                "• 🔗 **Ссылку на видео** - прямая ссылка на видео файл\n\n"
                "Я конвертирую его в MP4 1920x1080.\n\n"
                "Используйте /reset для смены режима."
            )
            keyboard = [
                [
                    InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif query.data == "mode_generator":
        # Показываем подменю с выбором типа поста
        message = (
            "✍️ **Режим: Генерация поста**\n\n"
            "Выберите тип поста:"
        )
        keyboard = [
            [
                InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
            ],
            [
                InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
            ],
            [
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif query.data == "post_webinar":
        context.user_data['mode'] = 'generator'
        context.user_data['post_type'] = 'webinar'
        message = (
            "📝 **Пост для вебинара**\n\n"
            "Отправьте мне текст транскрибации или текстовый файл (.txt, .doc, .docx, .md),\n"
            "и я создам из него контент для вебинара.\n\n"
            "Используйте /reset для смены режима."
        )
        await query.edit_message_text(message, parse_mode='Markdown')
        
    elif query.data == "post_videos":
        context.user_data['mode'] = 'generator'
        context.user_data['post_type'] = 'videos'
        message = (
            "🎬 **Пост для роликов на платформе**\n\n"
            "Отправьте мне текст транскрибации или текстовый файл (.txt, .doc, .docx, .md),\n"
            "и я создам из него контент для роликов на платформе.\n\n"
            "Используйте /reset для смены режима."
        )
        await query.edit_message_text(message, parse_mode='Markdown')
        
    elif query.data == "back_to_main":
        # Возвращаемся к главному меню
        context.user_data['mode'] = None
        context.user_data['post_type'] = None
        welcome_message = (
            "👋 Привет! Я бот-помощник для работы.\n\n"
            "Выберите функцию:\n\n"
            "📹 **Конвертер** - конвертирует видео в MP4 1920x1080\n"
            "✍️ **Генерация** - создает текст поста из транскрибации\n"
            "🎬 **Видео** - список сконвертированных видео\n\n"
            "Нажмите на кнопку ниже, чтобы начать:"
        )
        keyboard = [
            [
                InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
            ],
            [
                InlineKeyboardButton("🎬 Видео", callback_data="list_converted_videos")
            ]
        ]
        
        # Добавляем кнопку загрузки видео через WebApp, если URL настроен
        if VIDEO_WEBAPP_URL:
            keyboard.append([
                InlineKeyboardButton("🎬 Загрузить видео", web_app=WebAppInfo(url=VIDEO_WEBAPP_URL))
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data.startswith("convert_uploaded:"):
        # Обработка кнопки "Да, конвертировать" для загруженного на сайт видео
        logger.info(f"🔍 Обработка convert_uploaded: {query.data}")
        try:
            # Формат: convert_uploaded:filename (URL убран из callback_data из-за ограничения длины)
            parts = query.data.split(":", 1)
            logger.info(f"🔍 Разделил callback_data: {parts}")
            if len(parts) >= 2:
                filename = parts[1]
                logger.info(f"🔍 Извлечен filename: {filename}")
                
                # Восстанавливаем URL из filename
                public_base_url = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
                video_url = f"{public_base_url}/videos/{filename}"
                logger.info(f"🔍 Восстановлен URL: {video_url}")
                
                await safe_edit_text(query.message,
                    f"Начинаю конвертацию загруженного видео...\n\n"
                    f"Файл: {filename}",
                    reply_markup=get_main_menu_keyboard()
                )
                
                # Запускаем конвертацию в фоне с автоматическим именем
                user_id = query.from_user.id
                chat_id = query.message.chat_id
                
                logger.info(f"🔍 Параметры конвертации: user_id={user_id}, chat_id={chat_id}, video_url={video_url}")
                
                # Запускаем конвертацию в фоновой задаче
                logger.info(f"🔍 Создаю фоновую задачу для конвертации...")
                asyncio.create_task(
                    _convert_uploaded_video_background(
                        video_url=video_url,
                        filename=filename,
                        user_id=user_id,
                        chat_id=chat_id,
                        status_message=query.message,
                        custom_output_name=None  # Автоматическое имя
                    )
                )
                
                logger.info(f"✅ Конвертация запущена в фоне для загруженного файла: {filename}")
            else:
                logger.error(f"❌ Неверный формат callback_data: {query.data}, parts: {parts}")
                await safe_edit_text(query.message,
                    f"Ошибка: неверный формат данных",
                    reply_markup=get_main_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске конвертации загруженного видео: {e}", exc_info=True)
            await safe_edit_text(query.message,
                f"Ошибка при запуске конвертации:\n{str(e)}",
                reply_markup=get_main_menu_keyboard()
            )
    
    elif query.data.startswith("skip_convert:"):
        # Обработка кнопки "Нет" - просто подтверждаем
        try:
            parts = query.data.split(":", 1)
            filename = parts[1] if len(parts) > 1 else "файл"
            await safe_edit_text(query.message,
                f"✅ Понял, конвертация отменена.\n\n"
                f"📁 Файл `{filename}` останется без изменений.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке отмены конвертации: {e}")
    
    elif query.data == "list_converted_videos":
        # Показываем список сконвертированных видео
        try:
            from pathlib import Path
            
            # Путь к папке converted в webapp
            converted_dir = Path("webapp/converted")
            if not converted_dir.exists():
                converted_dir = Path("webapp/converted")
            
            video_files = []
            if converted_dir.exists():
                for file_path in converted_dir.iterdir():
                    if file_path.is_file():
                        ext = file_path.suffix.lower()
                        if ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv', '.m4v', '.3gp']:
                            file_size = file_path.stat().st_size
                            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                            video_files.append({
                                'name': file_path.name,
                                'size': file_size,
                                'mtime': file_mtime
                            })
            
            if video_files:
                # Сортируем по дате (новые первыми)
                video_files.sort(key=lambda x: x['mtime'], reverse=True)
                
                message = "🎬 **Сконвертированные видео:**\n\n"
                keyboard = []
                
                # Показываем максимум 50 файлов
                for i, video in enumerate(video_files[:50]):
                    size_mb = video['size'] / 1024 / 1024
                    date_str = video['mtime'].strftime("%d.%m.%Y %H:%M")
                    button_text = f"🎬 {video['name'][:25]}{'...' if len(video['name']) > 25 else ''} ({size_mb:.1f}MB)"
                    keyboard.append([
                        InlineKeyboardButton(button_text, callback_data=f"get_video_link:{video['name']}")
                    ])
                
                keyboard.append([
                    InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                ])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                message = "🎬 **Сконвертированные видео:**\n\n📭 Пока нет сконвертированных видео."
                keyboard = [
                    [
                        InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка сконвертированных видео: {e}", exc_info=True)
            await safe_edit_text(query.message,
                f"❌ Ошибка при получении списка видео:\n{str(e)}",
                reply_markup=get_main_menu_keyboard()
            )
    
    elif query.data.startswith("get_video_link:"):
        # Отправляем ссылку на выбранное видео
        try:
            parts = query.data.split(":", 1)
            filename = parts[1] if len(parts) > 1 else None
            
            if filename:
                public_base_url = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
                video_url = f"{public_base_url}/converted/{filename}"
                
                await safe_edit_text(query.message,
                    f"🔗 **Ссылка на видео:**\n\n{video_url}",
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                await safe_edit_text(query.message,
                    "❌ Ошибка: имя файла не указано",
                    reply_markup=get_main_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"❌ Ошибка при получении ссылки на видео: {e}", exc_info=True)
            await safe_edit_text(query.message,
                f"❌ Ошибка:\n{str(e)}",
                reply_markup=get_main_menu_keyboard()
            )
    
    elif query.data.startswith("select_video:"):
        # Обработка выбора видео для конвертации
        try:
            parts = query.data.split(":", 1)
            filename = parts[1] if len(parts) > 1 else None
            
            if filename:
                # Восстанавливаем URL из filename
                public_base_url = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
                video_url = f"{public_base_url}/videos/{filename}"
                
                await safe_edit_text(query.message,
                    f"Начинаю конвертацию видео...\n\n"
                    f"Файл: {filename}",
                    reply_markup=get_main_menu_keyboard()
                )
                
                # Запускаем конвертацию в фоне с автоматическим именем
                asyncio.create_task(
                    _convert_uploaded_video_background(
                        video_url=video_url,
                        filename=filename,
                        user_id=query.from_user.id,
                        chat_id=query.message.chat_id,
                        status_message=query.message,
                        custom_output_name=None  # Автоматическое имя
                    )
                )
                
                logger.info(f"✅ Конвертация запущена для файла из списка: {filename}")
            else:
                await safe_edit_text(query.message,
                    "Ошибка: имя файла не указано",
                    reply_markup=get_main_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"❌ Ошибка при выборе видео: {e}", exc_info=True)
            await safe_edit_text(query.message,
                f"Ошибка:\n{str(e)}",
                reply_markup=get_main_menu_keyboard()
            )


async def _process_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE, video_obj, file_name=None, source_type="video"):
    """
    Общая функция для обработки видео файлов
    Работает как с message.video, так и с message.document (MIME video/*)
    
    Args:
        update: Update объект
        context: Context объект
        video_obj: Объект Video или Document с видео
        file_name: Имя файла (для документов)
        source_type: Тип источника ("video" или "document")
    """
    logger.info(f"📹 Начало обработки видео (источник: {source_type})")
    
    # Автоматически устанавливаем режим конвертера
    if context.user_data.get('mode') != 'converter':
        context.user_data['mode'] = 'converter'
        logger.info("✅ Автоматически установлен режим 'converter'")
    
    try:
        if not video_obj:
            logger.error("❌ Не удалось получить объект видео")
            await update.message.reply_text("❌ Не удалось получить видео файл", reply_markup=get_main_menu_keyboard())
            return
        
        # Получаем информацию о файле
        file_id = video_obj.file_id
        file_size = getattr(video_obj, 'file_size', None)
        mime_type = getattr(video_obj, 'mime_type', None)
        
        logger.info(f"📊 Информация о файле: ID={file_id}, Размер={file_size / 1024 / 1024:.2f}MB" if file_size else f"📊 Информация о файле: ID={file_id}, Размер=неизвестен")
        logger.info(f"📋 MIME тип: {mime_type}, Имя файла: {file_name}")
        
        # Проверяем размер файла
        # Логируем информацию о лимитах
        max_size_gb = MAX_DOWNLOAD_SIZE / 1024 / 1024 / 1024
        api_type = "локальный" if TELEGRAM_LOCAL_API_URL else "стандартный"
        logger.info(f"📏 Лимиты: MAX_DOWNLOAD_SIZE={max_size_gb:.2f}GB, используется {api_type} Bot API")
        
        if file_size:
            size_gb = file_size / 1024 / 1024 / 1024
            logger.info(f"📏 Размер файла: {size_gb:.2f}GB, максимальный: {max_size_gb:.2f}GB")
            
            if file_size > MAX_DOWNLOAD_SIZE:
                local_api_text = ""
                if not TELEGRAM_LOCAL_API_URL:
                    local_api_text = (
                        "3. **Использование локального Bot API:**\n"
                        "   • Поднимите локальный Bot API сервер для работы с файлами до 2GB\n\n"
                    )
                
                logger.warning(f"⚠️ Файл слишком большой: {size_gb:.2f}GB > {max_size_gb:.2f}GB")
                await update.message.reply_text(
                    f"❌ Файл слишком большой для скачивания.\n\n"
                    f"📊 Размер файла: {size_gb:.2f}GB\n"
                    f"⚠️ Максимальный размер для скачивания: {max_size_gb:.2f}GB\n\n"
                    f"💡 **Альтернативные решения:**\n\n"
                    f"1. **Использование облачных хранилищ:**\n"
                    f"   • Загрузите видео в Google Drive/Dropbox\n"
                    f"   • Отправьте прямую ссылку на видео файл\n\n"
                    f"2. **Сжатие видео:**\n"
                    f"   • Используйте видеоредактор для сжатия\n"
                    f"   • Или отправьте ссылку на видео файл\n\n"
                    f"{local_api_text}"
                    f"ℹ️ **Важно:** Для файлов больше {max_size_gb:.2f}GB используйте конвертацию по ссылке."
                )
                return
            else:
                logger.info(f"✅ Размер файла в пределах лимита: {size_gb:.2f}GB <= {max_size_gb:.2f}GB")
        else:
            logger.info("⚠️ Размер файла не указан, продолжаем обработку (попробуем скачать)")
        
        # Отправляем сообщение о начале обработки
        status_message = await update.message.reply_text("⏳ Начинаю конвертацию видео...")
        logger.info("⏳ Отправлено сообщение о начале обработки")
        
        # Определяем расширение файла
        file_extension = 'mp4'
        if file_name:
            file_extension = Path(file_name).suffix.lower().lstrip('.') or 'mp4'
            logger.info(f"📝 Расширение из имени файла: {file_extension}")
        elif mime_type:
            # Пытаемся определить по MIME типу
            mime_to_ext = {
                'video/mp4': 'mp4',
                'video/quicktime': 'mov',
                'video/x-msvideo': 'avi',
                'video/webm': 'webm',
                'video/x-matroska': 'mkv'
            }
            file_extension = mime_to_ext.get(mime_type, 'mp4')
            logger.info(f"📝 Расширение из MIME типа: {file_extension}")
        
        # Скачиваем файл через локальный Bot API (если настроен) или стандартный API
        logger.info(f"⬇️ Начинаю скачивание файла через {'локальный' if TELEGRAM_LOCAL_API_URL else 'стандартный'} Bot API")
        try:
            file = await context.bot.get_file(file_id)
            file_path = f"downloads/{file_id}.{file_extension}"
            
            # Создаем директорию, если её нет
            os.makedirs("downloads", exist_ok=True)
            
            # Пытаемся использовать file_path, если файл большой
            if hasattr(file, 'file_path') and file.file_path:
                logger.info(f"📂 Используется file_path для скачивания: {file.file_path}")
            
            await file.download_to_drive(file_path)
            downloaded_size = os.path.getsize(file_path)
            logger.info(f"✅ Файл успешно скачан: {downloaded_size / 1024 / 1024:.2f}MB -> {file_path}")
        except Exception as download_error:
            error_msg = str(download_error).lower()
            logger.error(f"❌ Ошибка при скачивании файла: {download_error}")
            if 'too big' in error_msg or 'file is too big' in error_msg:
                await safe_edit_text(status_message,
                    f"❌ Файл слишком большой для скачивания.\n\n"
                    f"📊 Размер файла: {file_size / 1024 / 1024 / 1024:.2f}GB (если доступен)\n"
                    f"⚠️ Максимальный размер: 2GB\n\n"
                    f"💡 **Альтернативные решения:**\n\n"
                    f"1. **Использование облачных хранилищ:**\n"
                    f"   • Загрузите видео в Google Drive/Dropbox\n"
                    f"   • Отправьте прямую ссылку на видео файл\n\n"
                    f"2. **Сжатие видео:**\n"
                    f"   • Используйте видеоредактор для сжатия\n"
                    f"   • Или отправьте ссылку на видео файл\n\n"
                    f"ℹ️ **Важно:** Для файлов больше 2GB используйте конвертацию по ссылке."
                )
                return
            else:
                raise  # Пробрасываем другие ошибки
        
        # Обновляем статус и запускаем конвертацию в фоне
        await safe_edit_text(status_message,
            "🔄 Конвертирую видео в MP4 1920x1080...\n\n"
            "⏳ Это может занять некоторое время.\n"
            "💡 Вы можете продолжать пользоваться ботом - я уведомлю вас, когда конвертация завершится!",
            reply_markup=get_main_menu_keyboard()
        )
        logger.info("🔄 Начинаю конвертацию через FFmpeg в фоновом режиме")
        
        # Сохраняем информацию о конвертации
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        conversion_key = (user_id, file_id)
        active_conversions[conversion_key] = {
            'status_message': status_message,
            'file_path': file_path,
            'chat_id': chat_id,
            'user_id': user_id
        }
        
        # Запускаем конвертацию в фоновой задаче
        asyncio.create_task(
            _convert_video_background(
                file_path=file_path,
                file_id=file_id,
                user_id=user_id,
                chat_id=chat_id,
                status_message=status_message
            )
        )
        
        # Функция завершается здесь, бот может обрабатывать другие запросы
        logger.info(f"✅ Конвертация запущена в фоне для пользователя {user_id}, файл {file_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке видео: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                f"❌ Произошла ошибка при обработке видео:\n{str(e)}\n\n"
                "Попробуйте отправить видео еще раз."
            )
        except:
            pass


async def _convert_uploaded_video_background(video_url: str, filename: str, user_id: int, chat_id: int, status_message, custom_output_name: str = None):
    """
    Фоновая задача для конвертации видео, загруженного на сайт
    Не блокирует работу бота
    
    Args:
        video_url: URL видео для скачивания
        filename: Имя исходного файла
        user_id: ID пользователя
        chat_id: ID чата
        status_message: Сообщение для обновления статуса
        custom_output_name: Пользовательское имя для выходного файла (без расширения)
    """
    conversion_key = (user_id, f"uploaded_{filename}")
    try:
        logger.info(f"🎬 Начало фоновой конвертации загруженного видео")
        logger.info(f"🔍 Параметры: video_url={video_url}, filename={filename}, user_id={user_id}, chat_id={chat_id}, custom_output_name={custom_output_name}")
        
        # Скачиваем видео по URL
        import httpx
        file_path = f"downloads/uploaded_{filename}"
        os.makedirs("downloads", exist_ok=True)
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream('GET', video_url) as response:
                response.raise_for_status()
                with open(file_path, 'wb') as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        
        logger.info(f"✅ Видео скачано: {file_path}")
        
        # Формируем имя выходного файла
        if custom_output_name:
            # Используем пользовательское имя
            import re
            safe_name = re.sub(r'[^\w\s\-_\.]', '', custom_output_name)
            safe_name = re.sub(r'\s+', '_', safe_name)
            output_base_name = f"{safe_name}.mp4"
        else:
            # Автоматическое имя на основе исходного файла
            base_name = Path(filename).stem
            output_base_name = f"{base_name}_converted.mp4"
        
        # Конвертируем видео с ограничением размера до 800MB
        # Используем output_base_name без расширения как file_id для convert_video_to_mp4
        temp_file_id = output_base_name.replace('.mp4', '')
        output_path = await convert_video_to_mp4(file_path, temp_file_id, max_size_mb=800)
        
        if output_path and os.path.exists(output_path):
            # Переименовываем файл в нужное имя, если оно отличается
            final_output_path = Path("converted") / output_base_name
            if output_path != str(final_output_path):
                import shutil
                shutil.move(output_path, final_output_path)
                output_path = str(final_output_path)
                logger.info(f"✅ Файл переименован в: {output_path}")
            
            output_size = os.path.getsize(output_path)
            logger.info(f"✅ Конвертация завершена: {output_size / 1024 / 1024:.2f}MB -> {output_path}")
            
            # Копируем сконвертированное видео в веб-доступную папку
            if WEBAPP_CONVERTED_DIR:
                try:
                    import shutil
                    webapp_converted_path = Path(WEBAPP_CONVERTED_DIR)
                    webapp_converted_path.mkdir(parents=True, exist_ok=True)
                    
                    # Используем то же имя для веб-версии
                    output_filename = output_base_name
                    webapp_output_path = webapp_converted_path / output_filename
                    shutil.copy2(output_path, webapp_output_path)
                    
                    logger.info(f"✅ Видео скопировано в веб-папку: {webapp_output_path}")
                    
                    # Формируем публичный URL для сконвертированного видео
                    public_base_url = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
                    converted_url = f"{public_base_url}/converted/{output_filename}"
                    
                    logger.info(f"🔗 Формирую ссылку на сконвертированное видео: {converted_url}")
                    logger.info(f"📤 Отправляю сообщение со ссылкой пользователю {user_id}, chat_id={chat_id}")
                    
                    # Отправляем новое сообщение со ссылкой на сконвертированный файл
                    # Используем новое сообщение вместо редактирования, чтобы гарантировать доставку
                    try:
                        # Пытаемся получить бота из status_message
                        bot = None
                        if status_message and hasattr(status_message, 'bot'):
                            bot = status_message.bot
                            logger.info(f"✅ Бот получен из status_message")
                        else:
                            # Fallback: получаем из глобальной переменной
                            app = globals().get('application')
                            if app and hasattr(app, 'bot'):
                                bot = app.bot
                                logger.info(f"✅ Бот получен из application")
                        
                        if bot:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=f"Видео успешно сконвертировано!\n\n"
                                     f"Файл: {output_filename}\n"
                                     f"Размер: {output_size / 1024 / 1024:.2f} MB\n"
                                     f"Ссылка на сконвертированный файл:\n{converted_url}",
                                reply_markup=get_main_menu_keyboard()
                            )
                            logger.info(f"✅ Сообщение со ссылкой успешно отправлено как новое сообщение в chat_id={chat_id}")
                        else:
                            logger.error(f"❌ Бот не доступен для отправки сообщения")
                            # Fallback: пытаемся отредактировать старое сообщение
                            await safe_edit_text(status_message,
                                f"Видео успешно сконвертировано!\n\n"
                                f"Файл: {output_filename}\n"
                                f"Размер: {output_size / 1024 / 1024:.2f} MB\n"
                                f"Ссылка на сконвертированный файл:\n{converted_url}",
                                reply_markup=get_main_menu_keyboard()
                            )
                            logger.info(f"✅ Сообщение отредактировано (fallback)")
                    except Exception as send_error:
                        logger.error(f"❌ Ошибка при отправке сообщения со ссылкой: {send_error}", exc_info=True)
                        # Последняя попытка - редактируем старое сообщение
                        try:
                            await safe_edit_text(status_message,
                                f"Видео успешно сконвертировано!\n\n"
                                f"Файл: {output_filename}\n"
                                f"Размер: {output_size / 1024 / 1024:.2f} MB\n"
                                f"Ссылка: {converted_url}",
                                reply_markup=get_main_menu_keyboard()
                            )
                            logger.info(f"✅ Сообщение отредактировано (последняя попытка)")
                        except Exception as final_error:
                            logger.error(f"❌ Критическая ошибка: не удалось отправить сообщение: {final_error}", exc_info=True)
                except Exception as copy_error:
                    logger.warning(f"⚠️ Не удалось скопировать видео в веб-папку: {copy_error}")
                    await safe_edit_text(status_message,
                        f"✅ Видео сконвертировано, но не удалось скопировать в веб-папку.\n\n"
                        f"Ошибка: {str(copy_error)}",
                        reply_markup=get_main_menu_keyboard()
                    )
            
            # Удаляем временные файлы
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                logger.info("🗑️ Временные файлы удалены")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ Ошибка при удалении временных файлов: {cleanup_error}")
            
            # Удаляем из активных конвертаций
            if conversion_key in active_conversions:
                del active_conversions[conversion_key]
        else:
            logger.error("❌ Не удалось сконвертировать загруженное видео")
            await safe_edit_text(status_message,
                "❌ Не удалось сконвертировать видео 😔\n\n"
                "💡 **Возможные причины:**\n"
                "• Неподдерживаемый формат видео\n"
                "• Поврежденный файл\n"
                "• Недостаточно места на диске\n"
                "• Ошибка FFmpeg\n\n"
                "Попробуйте другой файл или другой формат.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Удаляем входной файл при ошибке
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            
            # Удаляем из активных конвертаций
            if conversion_key in active_conversions:
                del active_conversions[conversion_key]
    except Exception as e:
        logger.error(f"❌ Ошибка в фоновой конвертации загруженного видео: {e}", exc_info=True)
        try:
            await safe_edit_text(status_message,
                f"❌ Произошла ошибка при конвертации видео:\n{str(e)}\n\n"
                "Попробуйте отправить видео еще раз.",
                reply_markup=get_main_menu_keyboard()
            )
        except:
            pass
        
        # Удаляем из активных конвертаций
        if conversion_key in active_conversions:
            del active_conversions[conversion_key]


async def _convert_video_background(file_path: str, file_id: str, user_id: int, chat_id: int, status_message):
    """
    Фоновая задача для конвертации видео
    Не блокирует работу бота
    """
    conversion_key = (user_id, file_id)
    try:
        logger.info(f"🎬 Начало фоновой конвертации: {file_path}")
        
        # Конвертируем видео
        output_path = await convert_video_to_mp4(file_path, file_id)
        
        if output_path and os.path.exists(output_path):
            # Проверяем размер результата перед отправкой
            output_size = os.path.getsize(output_path)
            logger.info(f"✅ Конвертация завершена: {output_size / 1024 / 1024:.2f}MB -> {output_path}")
            
            # Копируем сконвертированное видео в веб-доступную папку и формируем ссылку
            converted_url = None
            logger.info(f"🔍 WEBAPP_CONVERTED_DIR: {WEBAPP_CONVERTED_DIR}")
            if WEBAPP_CONVERTED_DIR:
                try:
                    import shutil
                    webapp_converted_path = Path(WEBAPP_CONVERTED_DIR)
                    webapp_converted_path.mkdir(parents=True, exist_ok=True)
                    
                    output_filename = os.path.basename(output_path)
                    webapp_output_path = webapp_converted_path / output_filename
                    
                    logger.info(f"🔍 Копирую файл: {output_path} -> {webapp_output_path}")
                    
                    # Копируем только если еще не скопировано
                    if not webapp_output_path.exists():
                        shutil.copy2(output_path, webapp_output_path)
                        logger.info(f"✅ Видео скопировано в веб-папку: {webapp_output_path}")
                    else:
                        logger.info(f"✅ Видео уже есть в веб-папке: {webapp_output_path}")
                    
                    # Формируем публичный URL для сконвертированного видео
                    public_base_url = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
                    logger.info(f"🔍 PUBLIC_BASE_URL: {public_base_url}")
                    converted_url = f"{public_base_url}/converted/{output_filename}"
                    logger.info(f"🔍 Сформированная ссылка: {converted_url}")
                except Exception as copy_error:
                    logger.error(f"❌ Не удалось скопировать видео в веб-папку: {copy_error}", exc_info=True)
            else:
                logger.warning(f"⚠️ WEBAPP_CONVERTED_DIR не настроен, ссылка не будет отправлена")
            
            # Если файл слишком большой для отправки, отправляем только ссылку
            if output_size > MAX_UPLOAD_SIZE:
                # Результат слишком большой для отправки
                logger.warning(f"⚠️ Результат слишком большой для отправки: {output_size / 1024 / 1024:.1f}MB > {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB")
                if converted_url:
                    await safe_edit_text(status_message,
                        f"✅ **Видео успешно сконвертировано!**\n\n"
                        f"📁 Файл: `{os.path.basename(output_path)}`\n"
                        f"📊 Размер: {output_size / 1024 / 1024:.2f} MB\n"
                        f"⚠️ Файл слишком большой для отправки через бота.\n\n"
                        f"🔗 **Ссылка на сконвертированный файл:**\n{converted_url}",
                        parse_mode='Markdown',
                        reply_markup=get_main_menu_keyboard()
                    )
                    logger.info(f"✅ Ссылка на сконвертированное видео отправлена: {converted_url}")
                else:
                    await safe_edit_text(status_message,
                        f"✅ Видео успешно сконвертировано!\n\n"
                        f"❌ Но результат слишком большой для отправки через бота.\n\n"
                        f"📊 Размер результата: {output_size / 1024 / 1024:.1f}MB\n"
                        f"⚠️ Максимальный размер для отправки: {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB\n\n"
                        f"💡 **Решения:**\n\n"
                        f"1. Отправьте ссылку на видео файл для конвертации\n"
                        f"2. Используйте локальный Bot API сервер для работы с большими файлами",
                        reply_markup=get_main_menu_keyboard()
                    )
                # Удаляем временные файлы
                try:
                    os.remove(file_path)
                    os.remove(output_path)
                    logger.info("🗑️ Временные файлы удалены")
                except:
                    pass
                # Удаляем из активных конвертаций
                if conversion_key in active_conversions:
                    del active_conversions[conversion_key]
                return
            
            # Отправляем сообщение со ссылкой (если файл не слишком большой)
            if converted_url:
                await safe_edit_text(status_message,
                    f"✅ **Видео успешно сконвертировано!**\n\n"
                    f"📁 Файл: `{os.path.basename(output_path)}`\n"
                    f"📊 Размер: {output_size / 1024 / 1024:.2f} MB\n"
                    f"🔗 **Ссылка на сконвертированный файл:**\n{converted_url}",
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
                logger.info(f"✅ Ссылка на сконвертированное видео отправлена: {converted_url}")
            else:
                # Fallback: если не удалось создать ссылку, отправляем файл
                await safe_edit_text(status_message, "✅ Видео успешно сконвертировано! Отправляю...")
                logger.info("📤 Начинаю отправку сконвертированного видео")
                
                # Получаем бота из application (будет установлена в main)
                app = globals().get('application')
                if not app:
                    logger.error("❌ Application не доступна для отправки результата")
                    await safe_edit_text(status_message, "❌ Ошибка: не удалось отправить результат", reply_markup=get_main_menu_keyboard())
                    return
                
                try:
                    with open(output_path, 'rb') as video_file:
                        await app.bot.send_video(
                            chat_id=chat_id,
                            video=video_file,
                            caption="✅ Видео сконвертировано в MP4 1920x1080"
                        )
                    logger.info("✅ Видео успешно отправлено пользователю")
                except Exception as send_error:
                    error_msg = str(send_error).lower()
                    logger.error(f"❌ Ошибка при отправке видео: {send_error}")
                    if 'too big' in error_msg or 'file is too big' in error_msg:
                        await safe_edit_text(status_message,
                            f"✅ Видео успешно сконвертировано!\n\n"
                            f"❌ Но результат слишком большой для отправки через бота.\n\n"
                            f"📊 Размер результата: {output_size / 1024 / 1024:.1f}MB\n"
                            f"⚠️ Максимальный размер для отправки: {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB\n\n"
                            f"💡 **Решения:**\n\n"
                            f"1. Отправьте ссылку на видео файл для конвертации\n"
                            f"2. Используйте локальный Bot API сервер для работы с большими файлами",
                            reply_markup=get_main_menu_keyboard()
                        )
                    else:
                        await safe_edit_text(status_message,
                            f"❌ Ошибка при отправке видео:\n{str(send_error)}\n\n"
                            f"Попробуйте отправить видео еще раз.",
                            reply_markup=get_main_menu_keyboard()
                        )
            
            # Удаляем временные файлы (но НЕ удаляем файл из веб-папки!)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"🗑️ Удален временный входной файл: {file_path}")
                # НЕ удаляем output_path, если он уже скопирован в веб-папку
                # Удаляем только если он не в веб-папке
                if WEBAPP_CONVERTED_DIR:
                    webapp_converted_path = Path(WEBAPP_CONVERTED_DIR)
                    output_filename = os.path.basename(output_path)
                    webapp_output_path = webapp_converted_path / output_filename
                    if webapp_output_path.exists() and os.path.exists(output_path):
                        # Если файл уже в веб-папке, удаляем только временный файл
                        if str(output_path) != str(webapp_output_path):
                            os.remove(output_path)
                            logger.info(f"🗑️ Удален временный выходной файл: {output_path} (файл сохранен в веб-папке)")
                        else:
                            logger.info(f"✅ Файл сохранен в веб-папке, не удаляем: {output_path}")
                    else:
                        # Если файл не скопирован в веб-папку, не удаляем его
                        logger.warning(f"⚠️ Файл не найден в веб-папке, оставляем временный файл: {output_path}")
                else:
                    # Если WEBAPP_CONVERTED_DIR не настроен, удаляем временный файл
                    if os.path.exists(output_path):
                        os.remove(output_path)
                        logger.info(f"🗑️ Удален временный выходной файл: {output_path}")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ Ошибка при удалении временных файлов: {cleanup_error}")
            
            # Удаляем из активных конвертаций
            if conversion_key in active_conversions:
                del active_conversions[conversion_key]
            
            logger.info("✅ Обработка видео завершена успешно")
        else:
            logger.error("❌ Не удалось сконвертировать видео")
            await safe_edit_text(status_message,
                "❌ Не удалось сконвертировать видео 😔\n\n"
                "💡 **Возможные причины:**\n"
                "• Неподдерживаемый формат видео\n"
                "• Поврежденный файл\n"
                "• Недостаточно места на диске\n"
                "• Ошибка FFmpeg\n\n"
                "Попробуйте другой файл или другой формат.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Удаляем входной файл при ошибке
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            
            # Удаляем из активных конвертаций
            if conversion_key in active_conversions:
                del active_conversions[conversion_key]
    except Exception as e:
        logger.error(f"❌ Ошибка в фоновой конвертации: {e}", exc_info=True)
        try:
            await safe_edit_text(status_message,
                f"❌ Произошла ошибка при конвертации видео:\n{str(e)}\n\n"
                "Попробуйте отправить видео еще раз.",
                reply_markup=get_main_menu_keyboard()
            )
        except:
            pass
        
        # Удаляем из активных конвертаций
        if conversion_key in active_conversions:
            del active_conversions[conversion_key]
            
            # Отправляем кнопку меню даже при ошибке
            keyboard = [
                [
                    InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                    InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            app = globals().get('application')
            if app:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text="Что дальше?",
                    reply_markup=reply_markup
                )
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при обработке видео: {e}", exc_info=True)
        app = globals().get('application')
        if app:
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Произошла ошибка при обработке видео: {str(e)}",
                    reply_markup=get_main_menu_keyboard()
                )
            except:
                pass


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик видео файлов (message.video)"""
    logger.info("📹 Получено видео через message.video")
    video = update.message.video
    if not video:
        logger.error("❌ Не удалось получить video объект из update.message.video")
        await update.message.reply_text("❌ Не удалось получить видео файл", reply_markup=get_main_menu_keyboard())
        return
    
    await _process_video_file(update, context, video, source_type="video")


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик данных из Telegram Web App
    Обрабатывает загрузку видео через Web App
    """
    logger.info("📤 Получены данные из WebApp")
    
    try:
        if not update.effective_message or not update.effective_message.web_app_data:
            logger.error("❌ WebApp данные не найдены в сообщении")
            if update.effective_message:
                await update.effective_message.reply_text("❌ Ошибка: данные из WebApp не получены", reply_markup=get_main_menu_keyboard())
            return
        
        # Получаем данные из WebApp
        web_app_data = update.effective_message.web_app_data.data
        logger.info(f"📋 Получены данные WebApp: {web_app_data[:200]}...")  # Логируем первые 200 символов
        
        # Парсим JSON
        import json
        try:
            data = json.loads(web_app_data)
            logger.info(f"✅ JSON распарсен: type={data.get('type')}, url={data.get('video_url', 'N/A')[:50]}...")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON из WebApp: {e}")
            await update.message.reply_text("❌ Ошибка: неверный формат данных из WebApp", reply_markup=get_main_menu_keyboard())
            return
        
        # Проверяем тип данных
        if data.get('type') == 'uploaded' and data.get('video_url'):
            video_url = data.get('video_url')
            logger.info(f"✅ Видео успешно загружено: {video_url}")
            
            # Отправляем сообщение пользователю
            await update.effective_message.reply_text(
                f"✅ **Ваше видео успешно загружено!**\n\n"
                f"🔗 **Прямая ссылка:**\n{video_url}",
                parse_mode='Markdown'
            )
            
            # Отправляем кнопку меню
            keyboard = [
                [
                    InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                    InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
                ]
            ]
            if VIDEO_WEBAPP_URL:
                keyboard.append([
                    InlineKeyboardButton("🎬 Загрузить видео", web_app=WebAppInfo(url=VIDEO_WEBAPP_URL))
                ])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text("Что дальше?", reply_markup=reply_markup)
        elif data.get('video_url'):
            # Если просто video_url без type
            video_url = data.get('video_url')
            logger.info(f"✅ Видео успешно загружено: {video_url}")
            
            await update.effective_message.reply_text(
                f"✅ **Видео успешно загружено!**\n\n"
                f"🔗 **Прямая ссылка:**\n{video_url}",
                parse_mode='Markdown'
            )
            
            # Отправляем кнопку меню
            keyboard = [
                [
                    InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                    InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
                ]
            ]
            if VIDEO_WEBAPP_URL:
                keyboard.append([
                    InlineKeyboardButton("🎬 Загрузить видео", web_app=WebAppInfo(url=VIDEO_WEBAPP_URL))
                ])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text("Что дальше?", reply_markup=reply_markup)
        else:
            logger.warning(f"⚠️ Неожиданный формат данных WebApp: {data}")
            await update.effective_message.reply_text(
                f"⚠️ Получены данные из WebApp, но формат не распознан.\n\n"
                f"Тип: {data.get('type', 'не указан')}\n"
                f"URL: {data.get('video_url', 'не указан')}",
                reply_markup=get_main_menu_keyboard()
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке данных WebApp: {e}", exc_info=True)
        if update.effective_message:
            await update.effective_message.reply_text(f"❌ Произошла ошибка при обработке данных из WebApp: {str(e)}", reply_markup=get_main_menu_keyboard())


async def handle_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик конвертации видео по URL"""
    try:
        url = update.message.text.strip()
        
        # Проверяем, что это похоже на URL
        if not (url.startswith('http://') or url.startswith('https://')):
            await update.message.reply_text(
                "❌ Это не похоже на валидную ссылку. Отправьте прямую ссылку на видео файл.\n\n"
                "Пример: https://example.com/video.mp4"
            )
            return
        
        status_message = await update.message.reply_text("⏳ Скачиваю видео по ссылке...")
        
        # Скачиваем видео по ссылке
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                # Определяем расширение файла из URL или Content-Type
                file_extension = 'mp4'
                if '.' in url.split('/')[-1]:
                    file_extension = url.split('.')[-1].split('?')[0].lower()
                
                # Проверяем Content-Type
                content_type = response.headers.get('content-type', '').lower()
                if 'video' in content_type:
                    if 'mp4' in content_type:
                        file_extension = 'mp4'
                    elif 'quicktime' in content_type or 'mov' in content_type:
                        file_extension = 'mov'
                    elif 'webm' in content_type:
                        file_extension = 'webm'
                    elif 'x-matroska' in content_type or 'mkv' in content_type:
                        file_extension = 'mkv'
                
                # Проверяем, что это действительно видео файл
                content_type = response.headers.get('content-type', '').lower()
                content_length = response.headers.get('content-length')
                
                # Проверяем размер файла (минимум 1MB для видео)
                if content_length:
                    content_length_int = int(content_length)
                    if content_length_int < 1024 * 1024:  # Меньше 1MB
                        await safe_edit_text(status_message,
                            "❌ Скачанный файл слишком маленький для видео.\n\n"
                            f"📊 Размер: {content_length_int / 1024:.1f}KB\n"
                            "⚠️ Возможно, это не прямая ссылка на видео файл.\n\n"
                            "💡 **Как получить прямую ссылку:**\n"
                            "• Яндекс.Диск: используйте прямую ссылку на файл (не на страницу)\n"
                            "• Google Drive: используйте прямую ссылку для скачивания\n"
                            "• Другие сервисы: убедитесь, что ссылка ведет напрямую к файлу, а не к странице",
                            reply_markup=get_main_menu_keyboard()
                        )
                        return
                
                # Сохраняем файл
                file_id = f"url_{hash(url) % 1000000}"
                file_path = f"downloads/{file_id}.{file_extension}"
                
                # Создаем директорию, если её нет
                os.makedirs("downloads", exist_ok=True)
                
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                file_size = os.path.getsize(file_path)
                logger.info(f"Файл скачан по ссылке: {file_size / 1024 / 1024:.2f}MB, Content-Type: {content_type}")
                
                # Проверяем размер после скачивания
                if file_size < 1024 * 1024:  # Меньше 1MB
                    await safe_edit_text(status_message,
                        "❌ Скачанный файл слишком маленький для видео.\n\n"
                        f"📊 Размер: {file_size / 1024:.1f}KB\n"
                        "⚠️ Возможно, это не прямая ссылка на видео файл, а HTML страница.\n\n"
                        "💡 **Как получить прямую ссылку:**\n"
                        "• Яндекс.Диск: используйте прямую ссылку на файл (не на страницу)\n"
                        "• Google Drive: используйте прямую ссылку для скачивания\n"
                        "• Другие сервисы: убедитесь, что ссылка ведет напрямую к файлу",
                        reply_markup=get_main_menu_keyboard()
                    )
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    return
                
                # Проверяем, что это не HTML файл
                if file_size < 10 * 1024 * 1024:  # Для файлов меньше 10MB проверяем содержимое
                    try:
                        with open(file_path, 'rb') as f:
                            first_bytes = f.read(512)
                            # Проверяем, не является ли это HTML
                            if b'<html' in first_bytes.lower() or b'<!doctype' in first_bytes.lower():
                                await safe_edit_text(status_message,
                                    "❌ Скачанный файл является HTML страницей, а не видео файлом.\n\n"
                                    "⚠️ Ссылка ведет на страницу, а не на прямой файл.\n\n"
                                    "💡 **Как получить прямую ссылку:**\n"
                                    "• Яндекс.Диск: используйте прямую ссылку на файл\n"
                                    "• Google Drive: используйте прямую ссылку для скачивания\n"
                                    "• Другие сервисы: убедитесь, что ссылка ведет напрямую к файлу",
                                    reply_markup=get_main_menu_keyboard()
                                )
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                                return
                    except:
                        pass
                
        except httpx.TimeoutException:
            await safe_edit_text(status_message,
                "❌ Превышено время ожидания при скачивании файла.\n\n"
                "Попробуйте:\n"
                "• Проверить доступность ссылки\n"
                "• Использовать более быструю ссылку\n"
                "• Отправить видео напрямую",
                reply_markup=get_main_menu_keyboard()
            )
            return
        except Exception as download_error:
            logger.error(f"Ошибка при скачивании видео по ссылке: {download_error}")
            await safe_edit_text(status_message,
                f"❌ Ошибка при скачивании видео:\n{str(download_error)}\n\n"
                "Проверьте, что ссылка:\n"
                "• Доступна и не требует авторизации\n"
                "• Ведет напрямую к видео файлу\n"
                "• Не требует специальных заголовков",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Обновляем статус и запускаем конвертацию в фоне
        await safe_edit_text(status_message,
            "🔄 Конвертирую видео в MP4 1920x1080...\n\n"
            "⏳ Это может занять некоторое время.\n"
            "💡 Вы можете продолжать пользоваться ботом - я уведомлю вас, когда конвертация завершится!",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Сохраняем информацию о конвертации
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        file_id_for_conversion = f"url_{hash(file_path)}"  # Уникальный ID для URL конвертации
        conversion_key = (user_id, file_id_for_conversion)
        active_conversions[conversion_key] = {
            'status_message': status_message,
            'file_path': file_path,
            'chat_id': chat_id,
            'user_id': user_id
        }
        
        # Запускаем конвертацию в фоновой задаче
        asyncio.create_task(
            _convert_video_background(
                file_path=file_path,
                file_id=file_id_for_conversion,
                user_id=user_id,
                chat_id=chat_id,
                status_message=status_message
            )
        )
        
        # Функция завершается здесь, бот может обрабатывать другие запросы
        logger.info(f"✅ Конвертация запущена в фоне для пользователя {user_id}, файл из URL")
        
        # Проверяем файл перед конвертацией через ffprobe (опционально, можно убрать)
        try:
            import subprocess
            from video_converter import FFMPEG_PATH as VIDEO_FFMPEG_PATH
            import shutil
            
            # Определяем путь к ffprobe
            ffprobe_path = None
            
            if VIDEO_FFMPEG_PATH != 'ffmpeg' and os.path.exists(VIDEO_FFMPEG_PATH):
                # Если указан путь к ffmpeg, используем ffprobe из той же папки
                if VIDEO_FFMPEG_PATH.endswith('.exe'):
                    ffprobe_path = VIDEO_FFMPEG_PATH.replace('ffmpeg.exe', 'ffprobe.exe')
                else:
                    ffprobe_path = VIDEO_FFMPEG_PATH.replace('ffmpeg', 'ffprobe')
            else:
                # Ищем ffprobe в системном PATH
                ffprobe_path = shutil.which('ffprobe')
            
            # Если ffprobe не найден, используем 'ffprobe' из PATH (надеемся, что он там есть)
            if not ffprobe_path:
                ffprobe_path = 'ffprobe'
            
            # Быстрая проверка через ffprobe
            probe_result = subprocess.run(
                [ffprobe_path, '-v', 'error', '-show_entries', 'format=format_name', file_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if probe_result.returncode != 0:
                error_msg = probe_result.stderr[:200] if probe_result.stderr else "Неизвестная ошибка"
                await safe_edit_text(status_message,
                    f"❌ Файл не является валидным видео файлом.\n\n"
                    f"⚠️ Ошибка: {error_msg}\n\n"
                    f"💡 **Возможные причины:**\n"
                    f"• Ссылка ведет на HTML страницу, а не на файл\n"
                    f"• Файл поврежден\n"
                    f"• Неподдерживаемый формат\n\n"
                    f"**Как получить прямую ссылку:**\n"
                    f"• Яндекс.Диск: используйте прямую ссылку на файл\n"
                    f"• Google Drive: используйте прямую ссылку для скачивания",
                    reply_markup=get_main_menu_keyboard()
                )
                try:
                    os.remove(file_path)
                except:
                    pass
                return
        except FileNotFoundError:
            logger.warning("ffprobe не найден, пропускаем проверку")
            # Продолжаем, если ffprobe не найден
        except Exception as probe_error:
            logger.warning(f"Не удалось проверить файл через ffprobe: {probe_error}")
            # Продолжаем, если проверка не удалась
        
        # Обновляем статус и запускаем конвертацию в фоне
        await safe_edit_text(status_message,
            "🔄 Конвертирую видео в MP4 1920x1080...\n\n"
            "⏳ Это может занять некоторое время.\n"
            "💡 Вы можете продолжать пользоваться ботом - я уведомлю вас, когда конвертация завершится!",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Сохраняем информацию о конвертации
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        file_id_for_conversion = f"url_{hash(file_path)}"  # Уникальный ID для URL конвертации
        conversion_key = (user_id, file_id_for_conversion)
        active_conversions[conversion_key] = {
            'status_message': status_message,
            'file_path': file_path,
            'chat_id': chat_id,
            'user_id': user_id
        }
        
        # Запускаем конвертацию в фоновой задаче
        asyncio.create_task(
            _convert_video_background(
                file_path=file_path,
                file_id=file_id_for_conversion,
                user_id=user_id,
                chat_id=chat_id,
                status_message=status_message
            )
        )
        
        # Функция завершается здесь, бот может обрабатывать другие запросы
        logger.info(f"✅ Конвертация запущена в фоне для пользователя {user_id}, файл из URL")
        return  # Завершаем функцию, конвертация идет в фоне
        
        # Код ниже больше не выполняется, так как функция завершается выше
        # Оставлен для справки
        if False and output_path and os.path.exists(output_path):
            # Проверяем размер результата перед отправкой
            output_size = os.path.getsize(output_path)
            
            if output_size > MAX_UPLOAD_SIZE:
                await safe_edit_text(status_message,
                    f"✅ Видео успешно сконвертировано!\n\n"
                    f"❌ Но результат слишком большой для отправки через бота.\n\n"
                    f"📊 Размер результата: {output_size / 1024 / 1024:.1f}MB\n"
                    f"⚠️ Максимальный размер для отправки: {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB\n\n"
                    f"💡 Используйте локальный Bot API сервер для работы с большими файлами."
                )
                # Удаляем временные файлы
                try:
                    os.remove(file_path)
                    os.remove(output_path)
                except:
                    pass
                return
            
            # Отправляем конвертированное видео
            await safe_edit_text(status_message, "✅ Видео успешно сконвертировано! Отправляю...")
            
            try:
                with open(output_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption="✅ Видео сконвертировано в MP4 1920x1080"
                    )
            except Exception as send_error:
                error_msg = str(send_error).lower()
                if 'too big' in error_msg or 'file is too big' in error_msg:
                    await safe_edit_text(status_message,
                        f"✅ Видео успешно сконвертировано!\n\n"
                        f"❌ Но результат слишком большой для отправки через бота.\n\n"
                        f"📊 Размер результата: {output_size / 1024 / 1024:.1f}MB\n"
                        f"⚠️ Максимальный размер для отправки: {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB\n\n"
                        f"💡 Используйте локальный Bot API сервер для работы с большими файлами.",
                        reply_markup=get_main_menu_keyboard()
                    )
                else:
                    raise  # Пробрасываем другие ошибки
            
            # Удаляем временные файлы
            try:
                os.remove(file_path)
                os.remove(output_path)
            except Exception as cleanup_error:
                logger.warning(f"Ошибка при удалении временных файлов: {cleanup_error}")
            
            await status_message.delete()
            
            # Отправляем кнопку меню после успешной конвертации
            keyboard = [
                [
                    InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                    InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "✅ Готово! Что дальше?",
                reply_markup=reply_markup
            )
        else:
            await safe_edit_text(status_message,
                "❌ Не удалось сконвертировать видео 😔\n\n"
                "💡 **Возможные причины:**\n"
                "• Неподдерживаемый формат видео\n"
                "• Поврежденный файл\n"
                "• Недостаточно места на диске\n"
                "• Ошибка FFmpeg\n\n"
                "Попробуйте другой файл или другой формат.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Удаляем входной файл при ошибке
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            
            # Отправляем кнопку меню даже при ошибке
            keyboard = [
                [
                    InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                    InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Что дальше?", reply_markup=reply_markup)
            
    except Exception as e:
        # Не логируем ошибки типа "Message is not modified" как ошибки конвертации
        error_msg = str(e).lower()
        if 'message is not modified' not in error_msg:
            logger.error(f"Ошибка при конвертации по URL: {e}")
            await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}", reply_markup=get_main_menu_keyboard())
        else:
            # Это просто означает, что сообщение уже имеет такой же текст - это нормально
            logger.debug(f"Сообщение не изменено (это нормально): {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text.strip()
    
    # Проверяем, ожидается ли имя файла для конвертации (это должно быть ПЕРВЫМ!)
    if context.user_data.get('waiting_for_filename'):
        try:
            custom_filename = text.strip()
            selected_video = context.user_data.get('selected_video')
            selected_video_url = context.user_data.get('selected_video_url')
            conversion_type = context.user_data.get('conversion_type')
            status_message = context.user_data.get('conversion_status_message')
            conversion_user_id = context.user_data.get('conversion_user_id')
            conversion_chat_id = context.user_data.get('conversion_chat_id')
            
            # Очищаем флаги
            context.user_data['waiting_for_filename'] = False
            context.user_data['selected_video'] = None
            context.user_data['selected_video_url'] = None
            context.user_data['conversion_type'] = None
            context.user_data['conversion_status_message'] = None
            context.user_data['conversion_user_id'] = None
            context.user_data['conversion_chat_id'] = None
            
            if not selected_video:
                await update.message.reply_text(
                    "Ошибка: видео не выбрано. Пожалуйста, выберите видео заново.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Если пользователь отправил /skip, используем автоматическое имя
            if custom_filename.lower() == '/skip' or not custom_filename:
                custom_filename = None
            
            # Запускаем конвертацию
            if conversion_type == 'from_upload':
                # Конвертация из папки upload или загруженного через вебапп
                if not selected_video_url:
                    # Если URL не сохранен, восстанавливаем его
                    public_base_url = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
                    selected_video_url = f"{public_base_url}/videos/{selected_video}"
                
                # Используем сохраненное сообщение или создаем новое
                if status_message:
                    await safe_edit_text(status_message,
                        f"Начинаю конвертацию видео...\n\n"
                        f"Файл: {selected_video}",
                        reply_markup=get_main_menu_keyboard()
                    )
                    msg_to_use = status_message
                else:
                    msg_to_use = await update.message.reply_text(
                        f"Начинаю конвертацию видео...\n\n"
                        f"Файл: {selected_video}",
                        reply_markup=get_main_menu_keyboard()
                    )
                
                # Используем сохраненные user_id и chat_id или текущие
                user_id = conversion_user_id if conversion_user_id else update.effective_user.id
                chat_id = conversion_chat_id if conversion_chat_id else update.effective_chat.id
                
                # Запускаем конвертацию в фоне
                asyncio.create_task(
                    _convert_uploaded_video_background(
                        video_url=selected_video_url,
                        filename=selected_video,
                        user_id=user_id,
                        chat_id=chat_id,
                        status_message=msg_to_use,
                        custom_output_name=custom_filename
                    )
                )
                
                logger.info(f"✅ Конвертация запущена для файла: {selected_video}, имя: {custom_filename or 'автоматическое'}")
            else:
                await update.message.reply_text(
                    "Неизвестный тип конвертации",
                    reply_markup=get_main_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"Ошибка при обработке имени файла: {e}", exc_info=True)
            await update.message.reply_text(
                f"Ошибка:\n{str(e)}",
                reply_markup=get_main_menu_keyboard()
            )
        return
    
    # Проверяем, является ли текст URL (начинается с http:// или https://)
    is_url = text.startswith('http://') or text.startswith('https://')
    
    # Если режим конвертера выбран или текст похож на URL, обрабатываем как URL для конвертации
    if context.user_data.get('mode') == 'converter' or is_url:
        if is_url:
            # Автоматически устанавливаем режим конвертера, если не установлен
            if context.user_data.get('mode') != 'converter':
                context.user_data['mode'] = 'converter'
            await handle_video_url(update, context)
            return
        else:
            # Режим конвертера, но не URL - просим отправить видео или ссылку
            await update.message.reply_text(
                "Режим: Конвертер\n\n"
                "Отправьте мне:\n"
                "• Видео (до 2GB) - отправьте как видео, не как файл\n"
                "• Ссылку на видео - прямая ссылка на видео файл\n\n"
                "Используйте /reset для смены режима.",
                reply_markup=get_main_menu_keyboard()
            )
            return
    
    # Проверяем, выбран ли режим генератора и тип поста
    if context.user_data.get('mode') != 'generator' or not context.user_data.get('post_type'):
        # Показываем кнопки выбора типа поста
        message = "⚠️ Сначала выберите тип поста:"
        keyboard = [
            [
                InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
            ],
            [
                InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)
        return
    
    try:
        text = update.message.text
        
        if not text or len(text.strip()) < 10:
            await update.message.reply_text("❌ Текст слишком короткий. Отправьте более подробный текст.", reply_markup=get_main_menu_keyboard())
            return
        
        # Определяем какой ассистент использовать
        post_type = context.user_data.get('post_type', 'webinar')
        if post_type == 'videos':
            assistant_id = GPT_ASSISTANT_ID_VIDEOS
            if not assistant_id:
                await update.message.reply_text("❌ GPT_ASSISTANT_ID_VIDEOS не установлен в .env файле", reply_markup=get_main_menu_keyboard())
                return
            status_message = await update.message.reply_text("⏳ Обрабатываю транскрибацию для роликов на платформе...")
        else:
            assistant_id = GPT_ASSISTANT_ID
            if not assistant_id:
                await update.message.reply_text("❌ GPT_ASSISTANT_ID не установлен в .env файле", reply_markup=get_main_menu_keyboard())
                return
            status_message = await update.message.reply_text("⏳ Обрабатываю транскрибацию для вебинара...")
        
        # Генерируем контент через GPT ассистента
        content_parts = await generate_post_from_transcription(text, assistant_id)
        
        if not content_parts:
            await safe_edit_text(status_message, "❌ Не удалось сгенерировать контент. Проверьте настройки GPT_ASSISTANT_ID в .env", reply_markup=get_main_menu_keyboard())
            return
        
        await safe_edit_text(status_message, "✅ Контент готов! Отправляю...")
        await status_message.delete()
        
        # Проверяем тип поста
        post_type = context.user_data.get('post_type', 'webinar')
        
        if post_type == 'videos':
            # Для роликов отправляем одним сообщением с отступами и выделением подтем
            formatted_text = _format_videos_post(content_parts)
            await update.message.reply_text(
                formatted_text,
                parse_mode='Markdown'
            )
        else:
            # Для вебинаров отправляем 4 отдельных сообщения
            # 1. Название вебинара
            if content_parts.get('webinar_name'):
                await update.message.reply_text(
                    content_parts['webinar_name'],
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("(название вебинара не указано)")
            
            await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
            
            # 2. Описание
            if content_parts.get('description'):
                await update.message.reply_text(
                    content_parts['description'],
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("(описание не указано)")
            
            await asyncio.sleep(0.5)
            
            # 3. Тайм-код
            if content_parts.get('timestamps'):
                await update.message.reply_text(
                    content_parts['timestamps'],
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("(тайм-код не указан)")
            
            await asyncio.sleep(0.5)
            
            # 4. Пост для телеграм
            if content_parts.get('post'):
                await update.message.reply_text(
                    content_parts['post'],
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("(пост не указан)")
        
        # Отправляем кнопку меню после генерации поста
        if post_type == 'videos':
            # Если это был пост для роликов, показываем меню выбора типа поста
            keyboard = [
                [
                    InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
                ],
                [
                    InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ]
            ]
            message = "✅ Пост для роликов готов! Что дальше?"
        else:
            # Если это был пост для вебинара, показываем меню выбора типа поста
            keyboard = [
                [
                    InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
                ],
                [
                    InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ]
            ]
            message = "✅ Пост для вебинара готов! Что дальше?"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при обработке текста: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}", reply_markup=get_main_menu_keyboard())
        
        # Отправляем кнопку меню даже при ошибке
        keyboard = [
            [
                InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
            ],
            [
                InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
            ],
            [
                InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ Что-то пошло не так. Попробуйте еще раз:",
            reply_markup=reply_markup
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик документов (текстовые файлы для генерации поста И видео документы с MIME video/*)"""
    logger.info("📄 Получен документ")
    try:
        document = update.message.document
        
        if not document:
            logger.warning("⚠️ Документ не найден в сообщении")
            return
        
        file_name = document.file_name or ""
        mime_type = document.mime_type or ""
        logger.info(f"📋 Документ: имя={file_name}, MIME={mime_type}")
        
        # Проверяем, является ли это видео файлом (MIME video/*)
        is_video = False
        if mime_type.startswith('video/'):
            is_video = True
            logger.info(f"✅ Обнаружен видео документ по MIME типу: {mime_type}")
        else:
            # Проверяем по расширению файла
            video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv', '.m4v', '.3gp']
            file_ext = Path(file_name).suffix.lower() if file_name else ""
            if file_ext in video_extensions:
                is_video = True
                logger.info(f"✅ Обнаружен видео документ по расширению: {file_ext}")
        
        if is_video:
            # Это видео файл, отправленный как документ - обрабатываем как видео
            logger.info("📹 Обрабатываю видео документ")
            await _process_video_file(update, context, document, file_name=file_name, source_type="document")
            return
        
        # Показываем кнопки, если режим не выбран
        keyboard = [
            [
                InlineKeyboardButton("📹 Конвертер", callback_data="mode_converter"),
                InlineKeyboardButton("✍️ Генерация", callback_data="mode_generator")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Определяем расширение файла (если еще не определено)
        if 'file_ext' not in locals():
            file_ext = Path(file_name).suffix.lower() if file_name else ""
        
        # Проверяем, является ли это текстовым файлом
        text_extensions = ['.txt', '.doc', '.docx', '.md']
        if file_ext in text_extensions:
            # Текстовый файл - нужен режим генератора и тип поста
            if context.user_data.get('mode') != 'generator' or not context.user_data.get('post_type'):
                message = "⚠️ Для обработки текстового файла выберите тип поста:"
                keyboard = [
                    [
                        InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
                    ],
                    [
                        InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, reply_markup=reply_markup)
                return
            # Это текстовый файл - обрабатываем для генерации поста
            status_message = await update.message.reply_text("⏳ Читаю файл и генерирую текст для поста...")
            
            # Проверяем наличие file_id
            if not document.file_id:
                await safe_edit_text(status_message, "❌ Ошибка: не удалось получить ID файла", reply_markup=get_main_menu_keyboard())
                return
            
            # Скачиваем файл
            try:
                logger.info(f"📥 Скачиваю файл: file_id={document.file_id}, file_name={file_name}")
                file = await context.bot.get_file(document.file_id)
                if not file:
                    raise Exception("Не удалось получить информацию о файле")
                
                # Создаем папку downloads если её нет
                os.makedirs("downloads", exist_ok=True)
                
                file_path = f"downloads/{document.file_id}{file_ext}"
                logger.info(f"💾 Сохраняю файл в: {file_path}")
                
                # Пробуем несколько методов скачивания для совместимости
                download_success = False
                
                # Метод 1: прямое скачивание через HTTP (самый надежный при использовании прокси/локального API)
                if hasattr(file, 'file_path') and file.file_path:
                    try:
                        logger.info(f"📂 Пробую скачать напрямую через file_path: {file.file_path}")
                        import httpx
                        bot_token = context.bot.token
                        
                        # Определяем, является ли file_path полным URL или относительным путем
                        file_path_value = file.file_path
                        if file_path_value.startswith('http://') or file_path_value.startswith('https://'):
                            # Это уже полный URL - используем его напрямую
                            download_url = file_path_value
                            logger.info(f"🌐 file_path является полным URL, использую напрямую: {download_url[:100]}...")
                        else:
                            # Это относительный путь - формируем правильный URL
                            if TELEGRAM_LOCAL_API_URL:
                                # Используем локальный Bot API
                                base_url = TELEGRAM_LOCAL_API_URL.rstrip('/')
                                if not base_url.endswith('/bot'):
                                    base_url = f"{base_url}/bot"
                                download_url = f"{base_url}{bot_token}/{file_path_value}"
                            else:
                                # Используем стандартный Telegram API
                                download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_value}"
                            logger.info(f"🌐 Сформирован URL для скачивания: {download_url[:100]}...")
                        
                        # Настраиваем прокси, если указан
                        proxy_url = os.getenv('TELEGRAM_PROXY_URL')
                        client_kwargs = {'timeout': 60.0}
                        if proxy_url:
                            client_kwargs['proxies'] = {'http://': proxy_url, 'https://': proxy_url}
                            logger.info(f"🔗 Использую прокси: {proxy_url}")
                        
                        async with httpx.AsyncClient(**client_kwargs) as client:
                            response = await client.get(download_url)
                            response.raise_for_status()
                            with open(file_path, 'wb') as f:
                                f.write(response.content)
                        file_size = os.path.getsize(file_path)
                        if file_size > 0:
                            logger.info(f"✅ Файл скачан через прямой HTTP: {file_path}, размер: {file_size} байт")
                            download_success = True
                    except Exception as http_error:
                        logger.warning(f"⚠️ Прямое HTTP скачивание не сработало: {http_error}")
                
                # Метод 2: используем download_as_bytearray() для получения байтов (если HTTP не сработал)
                if not download_success:
                    try:
                        logger.info(f"📥 Пробую скачать через download_as_bytearray()...")
                        file_bytes = await file.download_as_bytearray()
                        with open(file_path, 'wb') as f:
                            f.write(file_bytes)
                        file_size = len(file_bytes)
                        if file_size > 0:
                            logger.info(f"✅ Файл скачан через download_as_bytearray(): {file_path}, размер: {file_size} байт")
                            download_success = True
                    except Exception as download_error:
                        logger.warning(f"⚠️ download_as_bytearray() не сработал: {download_error}")
                
                # Метод 3: fallback на download_to_drive() (последняя попытка)
                if not download_success:
                    try:
                        logger.info(f"📥 Пробую скачать через download_to_drive()...")
                        await file.download_to_drive(file_path)
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            if file_size > 0:
                                logger.info(f"✅ Файл скачан через download_to_drive(): {file_path}, размер: {file_size} байт")
                                download_success = True
                    except Exception as download_drive_error:
                        logger.error(f"❌ download_to_drive() также не сработал: {download_drive_error}")
                        # Не пробрасываем ошибку сразу, пробуем еще один метод
                
                # Метод 4: используем bot.request напрямую для скачивания
                if not download_success:
                    try:
                        logger.info(f"📥 Пробую скачать через bot.request напрямую...")
                        # Получаем file_path из объекта file
                        file_path_value = file.file_path if hasattr(file, 'file_path') and file.file_path else None
                        if file_path_value:
                            # Используем метод retrieve для получения файла
                            file_data = await context.bot.request.retrieve(file_path_value)
                            with open(file_path, 'wb') as f:
                                f.write(file_data)
                            file_size = os.path.getsize(file_path)
                            if file_size > 0:
                                logger.info(f"✅ Файл скачан через bot.request: {file_path}, размер: {file_size} байт")
                                download_success = True
                    except Exception as request_error:
                        logger.error(f"❌ bot.request также не сработал: {request_error}")
                
                if not download_success:
                    raise Exception("Не удалось скачать файл ни одним из доступных методов. Проверьте настройки прокси и локального Bot API.")
                
                if not os.path.exists(file_path):
                    raise Exception(f"Файл не был скачан: {file_path}")
                
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    raise Exception(f"Скачанный файл пуст: {file_path}")
                
                logger.info(f"✅ Файл успешно скачан: {file_path}, размер: {file_size} байт")
            except Exception as download_error:
                error_msg = str(download_error)
                logger.error(f"❌ Ошибка при скачивании файла: {error_msg}", exc_info=True)
                await safe_edit_text(status_message, 
                    f"❌ Не удалось скачать файл.\n\n"
                    f"Ошибка: {error_msg}\n\n"
                    f"Попробуйте отправить файл еще раз.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Читаем текст из файла
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except UnicodeDecodeError:
                # Пробуем другие кодировки
                with open(file_path, 'r', encoding='cp1251') as f:
                    text = f.read()
            
            if not text or len(text.strip()) < 10:
                await safe_edit_text(status_message, "❌ Файл слишком короткий или пустой", reply_markup=get_main_menu_keyboard())
                os.remove(file_path)
                return
            
            # Определяем какой ассистент использовать
            post_type = context.user_data.get('post_type', 'webinar')
            if post_type == 'videos':
                assistant_id = GPT_ASSISTANT_ID_VIDEOS
                if not assistant_id:
                    await safe_edit_text(status_message, "❌ GPT_ASSISTANT_ID_VIDEOS не установлен в .env файле", reply_markup=get_main_menu_keyboard())
                    os.remove(file_path)
                    return
            else:
                assistant_id = GPT_ASSISTANT_ID
                if not assistant_id:
                    await safe_edit_text(status_message, "❌ GPT_ASSISTANT_ID не установлен в .env файле", reply_markup=get_main_menu_keyboard())
                    os.remove(file_path)
                    return
            
            # Генерируем контент через GPT ассистента
            content_parts = await generate_post_from_transcription(text, assistant_id)
            
            if not content_parts:
                await safe_edit_text(status_message, "❌ Не удалось сгенерировать контент. Проверьте настройки ассистента в .env", reply_markup=get_main_menu_keyboard())
                os.remove(file_path)
                
                # Отправляем кнопку меню при ошибке
                keyboard = [
                    [
                        InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
                    ],
                    [
                        InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
                    ],
                    [
                        InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "❌ Что-то пошло не так. Попробуйте еще раз:",
                    reply_markup=reply_markup
                )
                return
            
            await safe_edit_text(status_message, "✅ Контент готов! Отправляю...")
            await status_message.delete()
            
            # Проверяем тип поста
            post_type = context.user_data.get('post_type', 'webinar')
            
            if post_type == 'videos':
                # Для роликов отправляем одним сообщением с отступами и выделением подтем
                formatted_text = _format_videos_post(content_parts)
                await update.message.reply_text(
                    formatted_text,
                    parse_mode='Markdown'
                )
            else:
                # Для вебинаров отправляем 4 отдельных сообщения
                # 1. Название вебинара
                if content_parts.get('webinar_name'):
                    await update.message.reply_text(
                        content_parts['webinar_name'],
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("(название вебинара не указано)")
                
                await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
                
                # 2. Описание
                if content_parts.get('description'):
                    await update.message.reply_text(
                        content_parts['description'],
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("(описание не указано)")
                
                await asyncio.sleep(0.5)
                
                # 3. Тайм-код
                if content_parts.get('timestamps'):
                    await update.message.reply_text(
                        content_parts['timestamps'],
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("(тайм-код не указан)")
                
                await asyncio.sleep(0.5)
                
                # 4. Пост для телеграм
                if content_parts.get('post'):
                    await update.message.reply_text(
                        content_parts['post'],
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("(пост не указан)")
            
            # Отправляем кнопку меню после генерации поста из файла
            if post_type == 'videos':
                keyboard = [
                    [
                        InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
                    ],
                    [
                        InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
                    ],
                    [
                        InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                    ]
                ]
                message = "✅ Пост для роликов готов! Что дальше?"
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("📝 Пост для вебинара", callback_data="post_webinar")
                    ],
                    [
                        InlineKeyboardButton("🎬 Пост для роликов на платформе", callback_data="post_videos")
                    ],
                    [
                        InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                    ]
                ]
                message = "✅ Пост для вебинара готов! Что дальше?"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message, reply_markup=reply_markup)
                
            # Удаляем временный файл
            os.remove(file_path)
        else:
            # Это может быть видео - пробуем обработать как видео
            if document.mime_type and 'video' in document.mime_type:
                # Видео файл - нужен режим конвертера с методом file
                if context.user_data.get('mode') != 'converter' or context.user_data.get('convert_method') != 'file':
                    keyboard = [
                        [
                            InlineKeyboardButton("📎 Отправить файл", callback_data="convert_file"),
                            InlineKeyboardButton("🔗 По ссылке", callback_data="convert_url")
                        ],
                        [
                            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        "⚠️ Для конвертации видео выберите способ:",
                        reply_markup=reply_markup
                    )
                    return
                await handle_video(update, context)
            else:
                await update.message.reply_text(
                    "❌ Неподдерживаемый тип файла. Отправьте видео или текстовый файл (.txt, .doc, .docx, .md)\n\n"
                    "Выберите режим работы:",
                    reply_markup=reply_markup
                )
                
    except Exception as e:
        logger.error(f"Ошибка при обработке документа: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}", reply_markup=get_main_menu_keyboard())


def check_ffmpeg():
    """
    Проверяет наличие FFmpeg в системе
    
    Проверяет в следующем порядке:
    1. FFMPEG_PATH из переменных окружения (если указан)
    2. FFmpeg в системном PATH (через shutil.which)
    
    Returns:
        bool: True если FFmpeg найден и работает, False иначе
    """
    import subprocess
    import shutil
    import platform
    
    # Сначала проверяем переменную окружения FFMPEG_PATH (если указана)
    custom_ffmpeg_path = os.getenv('FFMPEG_PATH')
    if custom_ffmpeg_path:
        # Нормализуем путь
        custom_ffmpeg_path = os.path.expanduser(custom_ffmpeg_path)
        if os.path.exists(custom_ffmpeg_path):
            try:
                result = subprocess.run(
                    [custom_ffmpeg_path, '-version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    logger.info(f"✅ FFmpeg найден через FFMPEG_PATH: {custom_ffmpeg_path}")
                    print(f"✅ FFmpeg найден через переменную FFMPEG_PATH: {custom_ffmpeg_path}")
                    return True
            except Exception as e:
                logger.warning(f"FFmpeg по пути {custom_ffmpeg_path} не работает: {e}")
        else:
            logger.warning(f"FFMPEG_PATH указан, но файл не существует: {custom_ffmpeg_path}")
    
    # Проверяем через shutil.which (ищет в системном PATH)
    # Это работает на Linux, macOS и Windows
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"✅ FFmpeg найден в системном PATH: {ffmpeg_path}")
                print(f"✅ FFmpeg найден в системном PATH: {ffmpeg_path}")
                return True
        except Exception as e:
            logger.warning(f"FFmpeg найден в PATH, но не работает: {e}")
    
    # Если не нашли
    logger.error("❌ FFmpeg не найден в системе")
    print("\n❌ FFmpeg не найден!")
    print("   Установите FFmpeg:")
    if platform.system() == 'Linux':
        print("   Ubuntu/Debian: sudo apt install ffmpeg")
        print("   CentOS/RHEL: sudo yum install ffmpeg")
    elif platform.system() == 'Darwin':  # macOS
        print("   brew install ffmpeg")
    elif platform.system() == 'Windows':
        print("   См. файл: FFMPEG_INSTALL_WINDOWS.md")
        print("   Или: https://www.gyan.dev/ffmpeg/builds/")
    else:
        print("   Установите FFmpeg согласно документации для вашей ОС")
    
    return False


def main():
    """Основная функция запуска бота"""
    # Проверяем наличие FFmpeg
    ffmpeg_found = check_ffmpeg()
    if not ffmpeg_found:
        logger.warning("FFmpeg не найден. Конвертация видео может не работать.")
        print("\n⚠️  ВНИМАНИЕ: FFmpeg не найден!")
        print("   Конвертация видео будет недоступна до установки FFmpeg.")
        print("\n💡 Важно после установки:")
        print("   1. Добавьте путь к папке 'bin' в переменную PATH")
        print("   2. ЗАКРОЙТЕ и откройте заново этот терминал/IDE")
        print("   3. Перезапустите бота")
        print("\n   Бот продолжит работу, но функция конвертации видео будет недоступна.\n")
    
    # Проверяем наличие токена
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
        print("   Создайте файл .env и добавьте туда ваш токен от @BotFather")
        return
    
    try:
        # Создаем приложение с увеличенными таймаутами
        from telegram.request import HTTPXRequest
        import re
        
        # Проверяем наличие прокси (если Telegram заблокирован)
        proxy_url = os.getenv('TELEGRAM_PROXY_URL')  # Например: http://proxy.example.com:8080
        
        # Создаем кастомный request с увеличенными таймаутами
        request_kwargs = {
            'connect_timeout': 30.0,
            'read_timeout': 30.0,
            'write_timeout': 30.0
        }
        
        # Добавляем прокси, если указан
        if proxy_url:
            request_kwargs['proxy_url'] = proxy_url
            logger.info(f"Используется прокси: {proxy_url}")
        
        # Если используется локальный Bot API, настраиваем базовый URL
        if TELEGRAM_LOCAL_API_URL:
            from urllib.parse import urlparse
            
            # Получаем и очищаем URL из .env
            base_url_raw = TELEGRAM_LOCAL_API_URL.strip()
            logger.info(f"Исходный TELEGRAM_LOCAL_API_URL из .env: '{base_url_raw}'")
            
            # Используем urlparse для правильного парсинга URL
            try:
                # Сначала убираем всё после host:port (если есть путь)
                if '://' in base_url_raw:
                    scheme_part, rest = base_url_raw.split('://', 1)
                    # Убираем путь после host:port
                    if '/' in rest:
                        rest = rest.split('/')[0]  # Берем только host:port
                    base_url_raw = f"{scheme_part}://{rest}"
                
                # Парсим URL
                parsed = urlparse(base_url_raw)
                
                # Извлекаем компоненты
                scheme = parsed.scheme or 'http'
                
                # Получаем host и port из netloc
                if parsed.netloc:
                    netloc = parsed.netloc
                    if ':' in netloc:
                        # Разделяем host и port
                        host, port_str = netloc.rsplit(':', 1)
                        # Проверяем, что port - это только цифры
                        if port_str.isdigit():
                            port = int(port_str)
                        else:
                            # Если порт содержит не только цифры, берем только цифры
                            port_digits = ''.join(filter(str.isdigit, port_str))
                            port = int(port_digits) if port_digits else 8081
                    else:
                        host = netloc
                        port = 8081
                elif parsed.hostname:
                    host = parsed.hostname
                    port = parsed.port if parsed.port else 8081
                else:
                    raise ValueError(f"Не удалось извлечь host из URL: {base_url_raw}")
                
                # Формируем чистый base_url
                base_url = f"{scheme}://{host}:{port}"
                
            except Exception as e:
                logger.error(f"Ошибка парсинга URL '{base_url_raw}': {e}")
                # Fallback: простая очистка вручную
                base_url_clean = base_url_raw
                
                # Убираем всё после первого слэша
                if '/' in base_url_clean and base_url_clean.count('/') > 2:
                    # Если есть путь после host:port
                    if '://' in base_url_clean:
                        scheme_part, rest = base_url_clean.split('://', 1)
                        host_port = rest.split('/')[0]
                        base_url_clean = f"{scheme_part}://{host_port}"
                
                # Убираем query параметры
                if '?' in base_url_clean:
                    base_url_clean = base_url_clean.split('?')[0]
                
                # Добавляем http:// если нет схемы
                if not base_url_clean.startswith('http://') and not base_url_clean.startswith('https://'):
                    base_url_clean = f'http://{base_url_clean}'
                
                # Извлекаем host:port
                if '://' in base_url_clean:
                    scheme_part = base_url_clean.split('://')[0]
                    rest = base_url_clean.split('://')[1]
                    
                    # Ищем host:port (порт только цифры)
                    match = re.match(r'^([^:]+):(\d{1,5})', rest)
                    if match:
                        host = match.group(1)
                        port = match.group(2)
                        base_url = f"{scheme_part}://{host}:{port}"
                    else:
                        # Если нет порта, добавляем стандартный
                        host = rest.split('/')[0].split(':')[0]
                        base_url = f"{scheme_part}://{host}:8081"
                else:
                    base_url = f"http://{base_url_clean}:8081"
            
            # Финальная проверка формата
            if not re.match(r'^https?://[^:/]+:\d{1,5}$', base_url):
                error_msg = (
                    f"Неправильный формат TELEGRAM_LOCAL_API_URL после обработки.\n"
                    f"Ожидается: http://host:port (например: http://72.56.73.219:8081)\n"
                    f"Получено из .env: '{TELEGRAM_LOCAL_API_URL}'\n"
                    f"Обработано как: '{base_url}'"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Финальная проверка: убеждаемся, что base_url не содержит токен
            if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in base_url:
                error_msg = (
                    f"ОШИБКА: Токен бота обнаружен в base_url!\n"
                    f"base_url: '{base_url}'\n"
                    f"Это недопустимо. Проверьте файл .env - возможно, токен попал в TELEGRAM_LOCAL_API_URL."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            logger.info(f"Используется локальный Bot API: {base_url}")
            
            # ВАЖНО: base_url должен заканчиваться на /bot и НЕ содержать токен
            # Формат: http://host:port/bot
            # Токен передается отдельно через .token()
            base_url_with_bot = f"{base_url}/bot"
            
            # Финальная проверка: убеждаемся, что base_url не содержит токен
            if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in base_url_with_bot:
                error_msg = (
                    f"ОШИБКА: Токен бота обнаружен в base_url!\n"
                    f"base_url: '{base_url}'\n"
                    f"base_url_with_bot: '{base_url_with_bot}'\n"
                    f"Проверьте файл .env - возможно, токен попал в TELEGRAM_LOCAL_API_URL."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            logger.info(f"base_url для Application.builder(): '{base_url_with_bot}'")
            logger.info(f"Токен передается отдельно через .token() (не в base_url)")
            
            # Создаем request (БЕЗ base_url, так как он передается в builder)
            request = HTTPXRequest(**request_kwargs)
            
            # Используем base_url в builder
            # base_url должен быть: http://host:port/bot (БЕЗ токена!)
            # Токен передается ТОЛЬКО через .token(), а НЕ в base_url
            application = Application.builder()\
                .token(TELEGRAM_BOT_TOKEN)\
                .base_url(base_url_with_bot)\
                .request(request)\
                .build()
        else:
            logger.info("Используется стандартный Telegram Bot API")
            request = HTTPXRequest(**request_kwargs)
            application = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()
        
        # Сохраняем application в глобальной переменной для доступа из фоновых задач
        globals()['application'] = application
        
        # Регистрируем обработчики
        # Обработчик кнопок должен быть первым
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("reset", reset_mode))
        # Обработчик видео - только для конвертации (до 2GB)
        application.add_handler(MessageHandler(filters.VIDEO, handle_video))
        # Обработчик документов - только для текстовых файлов (генерация поста)
        # Видео файлы, отправленные как документы, будут обработаны в handle_document с просьбой отправить как видео
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        # Обработчик текста - для генерации поста и конвертации по ссылке
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        # Обработчик данных из WebApp
        application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
        
        # Запускаем бота
        logger.info("Попытка подключения к Telegram API...")
        print("🔄 Подключаюсь к Telegram...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка при запуске бота: {error_msg}")
        
        if "TimedOut" in error_msg or "ConnectTimeout" in error_msg:
            print("\n❌ ОШИБКА ПОДКЛЮЧЕНИЯ:")
            print("   Не удалось подключиться к серверам Telegram.")
            print("\n🔍 Возможные причины:")
            print("   1. Проблемы с интернет-соединением")
            print("   2. Telegram заблокирован в вашем регионе (нужен VPN/прокси)")
            print("   3. Файрвол блокирует подключение")
            print("   4. Проблемы на стороне серверов Telegram")
            print("\n💡 Решения:")
            print("   - Проверьте интернет-соединение")
            print("   - Попробуйте использовать VPN")
            print("   - Проверьте настройки файрвола/антивируса")
            print("   - Попробуйте запустить позже")
        elif "Unauthorized" in error_msg or "401" in error_msg:
            print("\n❌ ОШИБКА АВТОРИЗАЦИИ:")
            print("   Неверный токен бота!")
            print("   Проверьте TELEGRAM_BOT_TOKEN в файле .env")
            print("   Получите новый токен у @BotFather в Telegram")
        else:
            print(f"\n❌ ОШИБКА: {error_msg}")
            print("   Проверьте логи выше для подробностей")
        
        raise


if __name__ == '__main__':
    main()

