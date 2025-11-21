"""
Backend сервер для загрузки видео через Telegram Web App
Использует FastAPI для обработки HTTP запросов
"""
import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
from dotenv import load_dotenv
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(title="Video Upload WebApp")

# Получаем настройки из переменных окружения
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'https://example.com')
VIDEOS_DIR = Path(os.getenv('VIDEOS_DIR', 'videos'))
CONVERTED_DIR = Path(os.getenv('CONVERTED_DIR', 'converted'))  # Папка для сконвертированных видео
PORT = int(os.getenv('WEBAPP_PORT', '8000'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')  # Токен бота для отправки уведомлений
TELEGRAM_NOTIFY_CHAT_ID = os.getenv('TELEGRAM_NOTIFY_CHAT_ID', '')  # ID чата для уведомлений (опционально)

# Создаем директории, если их нет
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Директория для загруженных видео: {VIDEOS_DIR.absolute()}")
logger.info(f"Директория для сконвертированных видео: {CONVERTED_DIR.absolute()}")

# Разрешенные расширения видео файлов
ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.wmv', '.m4v', '.3gp'}

# Максимальный размер файла (по умолчанию 2GB)
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', str(2 * 1024 * 1024 * 1024)))


def get_file_extension(filename: str) -> str:
    """Получает расширение файла"""
    return Path(filename).suffix.lower()


def is_video_file(filename: str) -> bool:
    """Проверяет, является ли файл видео"""
    ext = get_file_extension(filename)
    return ext in ALLOWED_EXTENSIONS


def generate_unique_filename(original_filename: str) -> str:
    """Генерирует уникальное имя файла"""
    ext = get_file_extension(original_filename)
    unique_id = str(uuid.uuid4())
    return f"{unique_id}{ext}"


@app.get("/", response_class=HTMLResponse)
async def root():
    """Корневая страница - редирект на /upload"""
    return f"""
    <html>
        <head>
            <meta http-equiv="refresh" content="0; url=/upload">
        </head>
        <body>
            <p>Redirecting to <a href="/upload">/upload</a></p>
        </body>
    </html>
    """


@app.get("/upload", response_class=HTMLResponse)
async def upload_form():
    """
    GET /upload - отображает HTML форму для загрузки видео
    """
    html_template = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Загрузка видео</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: #1a1a1a;
                color: #e0e0e0;
                padding: 20px;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }
            .container {
                max-width: 600px;
                width: 100%;
                background: #2c2c2c;
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(139, 92, 246, 0.2);
            }
            h1 {
                text-align: center;
                margin-bottom: 30px;
                color: #ffffff;
                font-size: 28px;
                font-weight: 600;
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .upload-area {
                border: 2px dashed #8b5cf6;
                border-radius: 16px;
                padding: 50px 20px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                background: rgba(139, 92, 246, 0.05);
                position: relative;
                overflow: hidden;
            }
            .upload-area::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.1), transparent);
                transition: left 0.5s;
            }
            .upload-area:hover {
                border-color: #a78bfa;
                background: rgba(139, 92, 246, 0.1);
                transform: translateY(-2px);
                box-shadow: 0 4px 20px rgba(139, 92, 246, 0.3);
            }
            .upload-area:hover::before {
                left: 100%;
            }
            .upload-area.dragover {
                border-color: #3b82f6;
                background: rgba(59, 130, 246, 0.15);
                transform: scale(1.02);
            }
            input[type="file"] {
                display: none;
            }
            .file-label {
                display: block;
                cursor: pointer;
                color: #a78bfa;
                font-weight: 500;
                font-size: 16px;
            }
            .file-info {
                margin-top: 20px;
                padding: 15px;
                background: #1a1a1a;
                border-radius: 12px;
                display: none;
                border: 1px solid rgba(139, 92, 246, 0.3);
                color: #e0e0e0;
            }
            .file-info.show {
                display: block;
            }
            button {
                width: 100%;
                padding: 16px 24px;
                margin-top: 20px;
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            button:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(139, 92, 246, 0.5);
            }
            button:active:not(:disabled) {
                transform: translateY(0);
            }
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }
            .progress {
                width: 100%;
                height: 10px;
                background: #1a1a1a;
                border-radius: 10px;
                margin-top: 20px;
                overflow: hidden;
                display: none;
                border: 1px solid rgba(139, 92, 246, 0.3);
            }
            .progress.show {
                display: block;
            }
            .progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #8b5cf6 0%, #3b82f6 100%);
                width: 0%;
                transition: width 0.3s ease;
                box-shadow: 0 0 10px rgba(139, 92, 246, 0.5);
            }
            .message {
                margin-top: 20px;
                padding: 16px;
                border-radius: 12px;
                display: none;
                font-weight: 500;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: rgba(34, 197, 94, 0.15);
                color: #4ade80;
                border: 1px solid rgba(34, 197, 94, 0.3);
            }
            .message.error {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.3);
            }
            .video-url {
                margin-top: 20px;
                padding: 16px;
                background: #1a1a1a;
                border-radius: 12px;
                word-break: break-all;
                display: none;
                border: 1px solid rgba(139, 92, 246, 0.3);
                color: #a78bfa;
            }
            .video-url.show {
                display: block;
            }
            .send-button {
                margin-top: 20px;
                display: none;
            }
            .send-button.show {
                display: block;
            }
            .videos-list {
                margin-top: 30px;
                padding-top: 30px;
                border-top: 2px solid var(--tg-theme-hint-color, #999999);
            }
            .videos-list h2 {
                margin-bottom: 20px;
                color: var(--tg-theme-text-color, #000000);
            }
            .video-item {
                background: var(--tg-theme-secondary-bg-color, #f0f0f0);
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 15px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .video-item-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .video-item-name {
                font-weight: 500;
                color: var(--tg-theme-text-color, #000000);
                word-break: break-all;
            }
            .video-item-size {
                color: var(--tg-theme-hint-color, #999999);
                font-size: 0.9em;
            }
            .video-item-url {
                background: var(--tg-theme-bg-color, #ffffff);
                padding: 10px;
                border-radius: 6px;
                word-break: break-all;
                font-size: 0.9em;
                color: var(--tg-theme-link-color, #3390ec);
            }
            .video-item-actions {
                display: flex;
                gap: 10px;
            }
            .video-item-btn {
                flex: 1;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                cursor: pointer;
                transition: opacity 0.3s;
            }
            .video-item-btn:hover {
                opacity: 0.8;
            }
            .btn-copy {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
            }
            .btn-delete {
                background: #ef4444;
                color: #ffffff;
            }
            .btn-delete:hover {
                background: #dc2626;
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4);
            }
            .btn-refresh {
                width: 100%;
                margin-top: 15px;
                padding: 10px;
                background: var(--tg-theme-secondary-bg-color, #f0f0f0);
                color: var(--tg-theme-text-color, #000000);
                border: 1px solid var(--tg-theme-hint-color, #999999);
                border-radius: 6px;
                cursor: pointer;
            }
            .loading {
                text-align: center;
                padding: 20px;
                color: var(--tg-theme-hint-color, #999999);
            }
            .empty-list {
                text-align: center;
                padding: 40px;
                color: var(--tg-theme-hint-color, #999999);
            }
        </style>
    </head>
    <body>
            <div class="container">
            <h1>🎬 Загрузка видео</h1>
            <div style="margin-bottom: 30px; display: flex; gap: 12px; flex-wrap: wrap; justify-content: center;">
                <a href="/files" class="nav-btn" style="display: inline-block; padding: 12px 24px; background: rgba(139, 92, 246, 0.2); color: #a78bfa; text-decoration: none; border-radius: 12px; font-weight: 600; border: 1px solid rgba(139, 92, 246, 0.4); transition: all 0.3s ease;">
                    📁 Все файлы
                </a>
                <a href="/converted" class="nav-btn" style="display: inline-block; padding: 12px 24px; background: rgba(59, 130, 246, 0.2); color: #60a5fa; text-decoration: none; border-radius: 12px; font-weight: 600; border: 1px solid rgba(59, 130, 246, 0.4); transition: all 0.3s ease;">
                    🎬 Сконвертированные
                </a>
            </div>
            <style>
                .nav-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
                }
            </style>
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="upload-area" id="uploadArea">
                    <label for="fileInput" class="file-label">
                        📁 Нажмите для выбора файла<br>
                        или перетащите видео сюда
                    </label>
                    <input type="file" id="fileInput" name="file" accept="video/*" required>
                </div>
                <div class="file-info" id="fileInfo"></div>
                <div class="progress" id="progress">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
                <button type="submit" id="submitBtn">Загрузить видео</button>
                <div class="message" id="message"></div>
                <div class="video-url" id="videoUrl"></div>
                <button type="button" class="send-button" id="sendButton" onclick="sendLinkToBot()">
                    Отправить ссылку в Telegram
                </button>
            </form>
            
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            tg.expand();

            let videoUrl = '';

            const fileInput = document.getElementById('fileInput');
            const uploadArea = document.getElementById('uploadArea');
            const fileInfo = document.getElementById('fileInfo');
            const progress = document.getElementById('progress');
            const progressBar = document.getElementById('progressBar');
            const submitBtn = document.getElementById('submitBtn');
            const message = document.getElementById('message');
            const videoUrlDiv = document.getElementById('videoUrl');
            const sendButton = document.getElementById('sendButton');
            const uploadForm = document.getElementById('uploadForm');

            // Обработка drag and drop
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    fileInput.files = files;
                    handleFileSelect(files[0]);
                }
            });

            // Обработка выбора файла
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    handleFileSelect(e.target.files[0]);
                }
            });

            function handleFileSelect(file) {
                const fileSizeMB = (file.size / 1024 / 1024).toFixed(2);
                fileInfo.innerHTML = `
                    <strong>Выбранный файл:</strong><br>
                    ${file.name}<br>
                    Размер: ${fileSizeMB} MB
                `;
                fileInfo.classList.add('show');
            }

            // Обработка отправки формы
            uploadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const file = fileInput.files[0];
                if (!file) {
                    showMessage('Пожалуйста, выберите файл', 'error');
                    return;
                }

                // Проверка размера файла
                if (file.size > {{ max_file_size }}) {
                    const maxSizeGB = ({{ max_file_size }} / 1024 / 1024 / 1024).toFixed(2);
                    showMessage(`Файл слишком большой. Максимальный размер: ${maxSizeGB} GB`, 'error');
                    return;
                }

                submitBtn.disabled = true;
                progress.classList.add('show');
                progressBar.style.width = '0%';
                message.classList.remove('show');
                videoUrlDiv.classList.remove('show');
                sendButton.classList.remove('show');

                const formData = new FormData();
                formData.append('file', file);
                
                // Получаем user_id из Telegram WebApp
                const tg = window.Telegram.WebApp;
                if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                    const userId = tg.initDataUnsafe.user.id;
                    if (userId) {
                        formData.append('user_id', userId.toString());
                    }
                }

                try {
                    const xhr = new XMLHttpRequest();

                    xhr.upload.addEventListener('progress', (e) => {
                        if (e.lengthComputable) {
                            const percentComplete = (e.loaded / e.total) * 100;
                            progressBar.style.width = percentComplete + '%';
                        }
                    });

                    xhr.addEventListener('load', () => {
                        if (xhr.status === 200) {
                            const response = JSON.parse(xhr.responseText);
                            videoUrl = response.video_url;
                            showMessage('Видео успешно загружено!', 'success');
                            videoUrlDiv.innerHTML = `<strong>Прямая ссылка:</strong><br><a href="${videoUrl}" target="_blank">${videoUrl}</a>`;
                            videoUrlDiv.classList.add('show');
                            sendButton.classList.add('show');
                        } else {
                            const error = JSON.parse(xhr.responseText);
                            showMessage(error.detail || 'Ошибка при загрузке файла', 'error');
                        }
                        submitBtn.disabled = false;
                        progress.classList.remove('show');
                    });

                    xhr.addEventListener('error', () => {
                        showMessage('Ошибка сети при загрузке файла', 'error');
                        submitBtn.disabled = false;
                        progress.classList.remove('show');
                    });

                    xhr.open('POST', '/upload');
                    xhr.send(formData);
                } catch (error) {
                    showMessage('Ошибка: ' + error.message, 'error');
                    submitBtn.disabled = false;
                    progress.classList.remove('show');
                }
            });

            function showMessage(text, type) {
                message.textContent = text;
                message.className = 'message show ' + type;
            }

            function sendLinkToBot() {
                if (videoUrl) {
                    tg.sendData(JSON.stringify({ video_url: videoUrl }));
                    tg.close();
                } else {
                    showMessage('Ссылка на видео не найдена', 'error');
                }
            }
        </script>
    </body>
    </html>
    """
    
    template = Template(html_template)
    return template.render(max_file_size=MAX_FILE_SIZE)


@app.post("/upload")
async def upload_video(file: UploadFile = File(...), user_id: Optional[str] = Form(None)):
    """
    POST /upload - принимает видео файл и сохраняет его на сервере
    
    Args:
        file: Загружаемый видео файл
        
    Returns:
        JSON с прямой ссылкой на загруженное видео
    """
    try:
        # Проверяем, что файл выбран
        if not file.filename:
            raise HTTPException(status_code=400, detail="Файл не выбран")
        
        # Проверяем, что это видео файл
        if not is_video_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла. Разрешенные форматы: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Генерируем уникальное имя файла
        unique_filename = generate_unique_filename(file.filename)
        file_path = VIDEOS_DIR / unique_filename
        
        # Читаем файл по частям и сохраняем
        file_size = 0
        with open(file_path, 'wb') as f:
            while True:
                chunk = await file.read(8192)  # Читаем по 8KB
                if not chunk:
                    break
                file_size += len(chunk)
                
                # Проверяем размер файла
                if file_size > MAX_FILE_SIZE:
                    # Удаляем частично загруженный файл
                    if file_path.exists():
                        file_path.unlink()
                    raise HTTPException(
                        status_code=413,
                        detail=f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE / 1024 / 1024 / 1024:.2f} GB"
                    )
                
                f.write(chunk)
        
        logger.info(f"✅ Видео загружено: {unique_filename} ({file_size / 1024 / 1024:.2f} MB)")
        logger.info(f"🔍 Получен user_id из формы: {user_id}")
        logger.info(f"🔍 TELEGRAM_BOT_TOKEN настроен: {bool(TELEGRAM_BOT_TOKEN)}")
        logger.info(f"🔍 TELEGRAM_NOTIFY_CHAT_ID: {TELEGRAM_NOTIFY_CHAT_ID}")
        
        # Формируем публичный URL
        video_url = f"{PUBLIC_BASE_URL}/videos/{unique_filename}"
        
        # Отправляем уведомление боту о загрузке файла (если настроен токен)
        if TELEGRAM_BOT_TOKEN:
            try:
                # Используем стандартную библиотеку для отправки HTTP запросов
                import urllib.request
                import urllib.parse
                import json
                
                # Получаем user_id из параметров формы (передается из Telegram WebApp)
                notify_user_id = user_id or TELEGRAM_NOTIFY_CHAT_ID
                logger.info(f"🔍 notify_user_id для отправки: {notify_user_id}")
                
                if notify_user_id:
                    file_size_mb = file_size / 1024 / 1024
                    message_text = (
                        f"📹 **Новое видео загружено на сайт!**\n\n"
                        f"📁 Файл: `{unique_filename}`\n"
                        f"📊 Размер: {file_size_mb:.2f} MB\n"
                        f"🔗 Ссылка: {video_url}\n\n"
                        f"❓ Конвертировать ли этот ролик?"
                    )
                    
                    # Создаем кнопки Да/Нет
                    # Используем только filename в callback_data, так как URL может быть слишком длинным
                    # URL будет восстановлен из filename при обработке callback
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "✅ Да, конвертировать", "callback_data": f"convert_uploaded:{unique_filename}"},
                                {"text": "❌ Нет", "callback_data": f"skip_convert:{unique_filename}"}
                            ]
                        ]
                    }
                    
                    # Отправляем сообщение через Telegram Bot API
                    bot_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    logger.info(f"🔍 Отправка уведомления: user_id={notify_user_id}, filename={unique_filename}")
                    
                    # Подготавливаем данные для отправки
                    data = {
                        "chat_id": notify_user_id,
                        "text": message_text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard
                    }
                    
                    # Отправляем синхронный HTTP запрос в отдельном потоке (чтобы не блокировать event loop)
                    import asyncio
                    
                    def send_notification():
                        try:
                            data_json = json.dumps(data).encode('utf-8')
                            req = urllib.request.Request(bot_api_url, data=data_json, headers={'Content-Type': 'application/json'})
                            with urllib.request.urlopen(req, timeout=10) as response:
                                return json.loads(response.read().decode('utf-8'))
                        except urllib.error.HTTPError as e:
                            # Получаем детали ошибки
                            error_body = e.read().decode('utf-8')
                            logger.error(f"❌ HTTP Error {e.code}: {error_body}")
                            return {'ok': False, 'error': error_body}
                        except Exception as e:
                            logger.error(f"❌ Ошибка при отправке уведомления: {e}")
                            return {'ok': False, 'error': str(e)}
                    
                    # Выполняем в отдельном потоке
                    loop = asyncio.get_event_loop()
                    response_data = await loop.run_in_executor(None, send_notification)
                    
                    if response_data.get('ok'):
                        logger.info(f"📤 Уведомление отправлено боту о загрузке: {unique_filename}")
                    else:
                        logger.warning(f"⚠️ Не удалось отправить уведомление боту: {response_data}")
                else:
                    logger.warning(f"⚠️ user_id не получен из формы и TELEGRAM_NOTIFY_CHAT_ID не настроен. user_id из формы: {user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить уведомление боту: {e}", exc_info=True)
        
        return {
            "status": "success",
            "video_url": video_url,
            "filename": unique_filename,
            "size": file_size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке видео: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке файла: {str(e)}")


@app.get("/videos/{filename}")
async def get_video(filename: str):
    """
    GET /videos/{filename} - отдает загруженное видео файл
    """
    """
    GET /videos/{filename} - отдает видео файл
    
    Args:
        filename: Имя файла
        
    Returns:
        Видео файл
    """
    # Получаем абсолютный путь к файлу
    if VIDEOS_DIR.is_absolute():
        videos_path = VIDEOS_DIR
    else:
        videos_path = Path.cwd() / VIDEOS_DIR
    
    videos_path = videos_path.resolve()
    file_path = videos_path / filename
    file_path = file_path.resolve()
    
    # Проверка безопасности: файл должен быть внутри videos_path
    if not str(file_path).startswith(str(videos_path)):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Проверяем, что файл существует
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    # Проверяем, что это видео файл
    if not is_video_file(filename):
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат файла")
    
    return FileResponse(
        path=file_path,
        media_type='video/mp4',
        filename=filename
    )


@app.get("/files", response_class=HTMLResponse)
async def files_list():
    """
    GET /files - отображает HTML страницу со списком всех видео файлов
    """
    html_template = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Все файлы</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: #1a1a1a;
                color: #e0e0e0;
                padding: 20px;
                min-height: 100vh;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 30px;
                color: #ffffff;
                font-size: 32px;
                font-weight: 600;
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .header-actions {
                display: flex;
                gap: 12px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            .btn {
                padding: 12px 24px;
                border: none;
                border-radius: 12px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                text-decoration: none;
                display: inline-block;
                transition: all 0.3s ease;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .btn-primary {
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                color: #ffffff;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .btn-secondary {
                background: rgba(139, 92, 246, 0.2);
                color: #a78bfa;
                border: 1px solid rgba(139, 92, 246, 0.4);
            }
            .btn-danger {
                background: rgba(239, 68, 68, 0.2);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.4);
            }
            .video-item {
                background: #2c2c2c;
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 20px;
                display: flex;
                flex-direction: column;
                gap: 15px;
                border: 1px solid rgba(139, 92, 246, 0.2);
                transition: all 0.3s ease;
            }
            .video-item:hover {
                border-color: rgba(139, 92, 246, 0.5);
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(139, 92, 246, 0.2);
            }
            .video-item-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 10px;
            }
            .video-item-name {
                font-weight: 600;
                color: #ffffff;
                word-break: break-all;
                flex: 1;
                font-size: 16px;
            }
            .video-item-size {
                color: #a78bfa;
                font-size: 14px;
                font-weight: 500;
            }
            .video-item-date {
                font-size: 13px;
                color: #9ca3af;
            }
            .video-item-url {
                background: #1a1a1a;
                padding: 14px;
                border-radius: 12px;
                word-break: break-all;
                font-size: 13px;
                color: #60a5fa;
                border: 1px solid rgba(139, 92, 246, 0.3);
                font-family: 'Courier New', monospace;
            }
            .video-item-actions {
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
            }
            .video-item-btn {
                flex: 1;
                min-width: 140px;
                padding: 12px 20px;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            .video-item-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .btn-copy {
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                color: #ffffff;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3);
            }
            .btn-delete {
                background: rgba(239, 68, 68, 0.2);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.4);
            }
            .btn-delete:hover {
                background: rgba(239, 68, 68, 0.3);
                box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
            }
            .loading {
                text-align: center;
                padding: 60px;
                color: #9ca3af;
                font-size: 16px;
            }
            .empty-list {
                text-align: center;
                padding: 60px;
                color: #9ca3af;
                font-size: 16px;
            }
            .message {
                padding: 16px;
                border-radius: 12px;
                margin-bottom: 20px;
                display: none;
                font-weight: 500;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: rgba(34, 197, 94, 0.15);
                color: #4ade80;
                border: 1px solid rgba(34, 197, 94, 0.3);
            }
            .message.error {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.3);
            }
            .stats {
                background: #2c2c2c;
                padding: 24px;
                border-radius: 16px;
                margin-bottom: 30px;
                display: flex;
                justify-content: space-around;
                flex-wrap: wrap;
                gap: 30px;
                border: 1px solid rgba(139, 92, 246, 0.2);
            }
            .stat-item {
                text-align: center;
            }
            .stat-value {
                font-size: 32px;
                font-weight: 700;
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .stat-label {
                font-size: 13px;
                color: #9ca3af;
                margin-top: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📁 Все файлы</h1>
            
            <div class="header-actions">
                <a href="/upload" class="btn btn-primary">⬆️ Загрузить видео</a>
                <a href="/converted" class="btn btn-secondary">🎬 Сконвертированные</a>
                <button type="button" class="btn btn-secondary" onclick="loadVideosList()">🔄 Обновить</button>
            </div>
            
            <div class="message" id="message"></div>
            
            <div class="stats" id="stats" style="display: none;">
                <div class="stat-item">
                    <div class="stat-value" id="totalFiles">0</div>
                    <div class="stat-label">Всего файлов</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="totalSize">0 MB</div>
                    <div class="stat-label">Общий размер</div>
                </div>
            </div>
            
            <div id="videosListContainer">
                <div class="loading">Загрузка списка видео...</div>
            </div>
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            tg.expand();

            // Загрузка списка видео
            async function loadVideosList() {
                const container = document.getElementById('videosListContainer');
                const message = document.getElementById('message');
                const stats = document.getElementById('stats');
                
                container.innerHTML = '<div class="loading">Загрузка списка видео...</div>';
                message.className = 'message';
                stats.style.display = 'none';
                
                try {
                    const response = await fetch('/api/videos');
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка при загрузке списка');
                    }
                    
                    const videos = data.videos || [];
                    
                    if (videos.length === 0) {
                        container.innerHTML = '<div class="empty-list">📭 Видео файлов пока нет</div>';
                        return;
                    }
                    
                    // Подсчет статистики
                    const totalSize = videos.reduce((sum, v) => sum + v.size, 0);
                    const totalSizeMB = (totalSize / 1024 / 1024).toFixed(2);
                    
                    document.getElementById('totalFiles').textContent = videos.length;
                    document.getElementById('totalSize').textContent = totalSizeMB + ' MB';
                    stats.style.display = 'flex';
                    
                    // Формирование списка
                    let html = '';
                    videos.forEach(video => {
                        const date = new Date(video.created_at);
                        const dateStr = date.toLocaleString('ru-RU', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                        
                        html += `
                            <div class="video-item">
                                <div class="video-item-header">
                                    <div class="video-item-name">${escapeHtml(video.filename)}</div>
                                    <div class="video-item-size">${video.size_mb} MB</div>
                                </div>
                                <div class="video-item-date">
                                    📅 ${dateStr}
                                </div>
                                <div class="video-item-url" id="url-${escapeHtml(video.filename)}">
                                    ${escapeHtml(video.url)}
                                </div>
                                <div class="video-item-actions">
                                    <button type="button" class="video-item-btn btn-copy" onclick="copyVideoUrl('${escapeHtml(video.url)}', '${escapeHtml(video.filename)}')">
                                        📋 Копировать ссылку
                                    </button>
                                    <button type="button" class="video-item-btn btn-delete" onclick="deleteVideo('${escapeHtml(video.filename)}')">
                                        🗑️ Удалить
                                    </button>
                                </div>
                            </div>
                        `;
                    });
                    
                    container.innerHTML = html;
                } catch (error) {
                    container.innerHTML = '';
                    message.textContent = `Ошибка: ${escapeHtml(error.message)}`;
                    message.className = 'message error show';
                }
            }

            // Копирование ссылки на видео
            async function copyVideoUrl(url, filename) {
                try {
                    await navigator.clipboard.writeText(url);
                    showMessage(`✅ Ссылка на ${filename} скопирована!`, 'success');
                } catch (error) {
                    // Fallback для старых браузеров
                    const textArea = document.createElement('textarea');
                    textArea.value = url;
                    textArea.style.position = 'fixed';
                    textArea.style.opacity = '0';
                    document.body.appendChild(textArea);
                    textArea.select();
                    try {
                        document.execCommand('copy');
                        showMessage(`✅ Ссылка на ${filename} скопирована!`, 'success');
                    } catch (err) {
                        showMessage('❌ Не удалось скопировать ссылку', 'error');
                    }
                    document.body.removeChild(textArea);
                }
            }

            // Удаление видео
            async function deleteVideo(filename) {
                if (!confirm(`Вы уверены, что хотите удалить видео "${filename}"?`)) {
                    return;
                }
                
                try {
                    const response = await fetch(`/api/videos/${encodeURIComponent(filename)}`, {
                        method: 'DELETE'
                    });
                    
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка при удалении');
                    }
                    
                    showMessage(`✅ Видео ${filename} удалено`, 'success');
                    
                    // Обновляем список
                    setTimeout(() => {
                        loadVideosList();
                    }, 500);
                } catch (error) {
                    showMessage(`❌ Ошибка: ${escapeHtml(error.message)}`, 'error');
                }
            }

            // Показать сообщение
            function showMessage(text, type) {
                const message = document.getElementById('message');
                message.textContent = text;
                message.className = `message ${type} show`;
                
                // Автоматически скрыть через 3 секунды
                setTimeout(() => {
                    message.className = 'message';
                }, 3000);
            }

            // Экранирование HTML
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Загружаем список при загрузке страницы
            loadVideosList();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_template)


@app.get("/converted", response_class=HTMLResponse)
async def converted_list():
    """
    GET /converted - отображает HTML страницу со списком всех сконвертированных видео файлов
    """
    html_template = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Сконвертированные видео</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: #1a1a1a;
                color: #e0e0e0;
                padding: 20px;
                min-height: 100vh;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 30px;
                color: #ffffff;
                font-size: 32px;
                font-weight: 600;
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .header-actions {
                display: flex;
                gap: 12px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            .btn {
                padding: 12px 24px;
                border: none;
                border-radius: 12px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                text-decoration: none;
                display: inline-block;
                transition: all 0.3s ease;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .btn-primary {
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                color: #ffffff;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .btn-secondary {
                background: rgba(139, 92, 246, 0.2);
                color: #a78bfa;
                border: 1px solid rgba(139, 92, 246, 0.4);
            }
            .video-item {
                background: #2c2c2c;
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 20px;
                display: flex;
                flex-direction: column;
                gap: 15px;
                border: 1px solid rgba(59, 130, 246, 0.2);
                transition: all 0.3s ease;
            }
            .video-item:hover {
                border-color: rgba(59, 130, 246, 0.5);
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(59, 130, 246, 0.2);
            }
            .video-item-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 10px;
            }
            .video-item-name {
                font-weight: 600;
                color: #ffffff;
                word-break: break-all;
                flex: 1;
                font-size: 16px;
            }
            .video-item-size {
                color: #60a5fa;
                font-size: 14px;
                font-weight: 500;
            }
            .video-item-date {
                font-size: 13px;
                color: #9ca3af;
            }
            .video-item-url {
                background: #1a1a1a;
                padding: 14px;
                border-radius: 12px;
                word-break: break-all;
                font-size: 13px;
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.3);
                font-family: 'Courier New', monospace;
            }
            .video-item-actions {
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
            }
            .video-item-btn {
                flex: 1;
                min-width: 140px;
                padding: 12px 20px;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            .video-item-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4);
            }
            .btn-copy {
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                color: #ffffff;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3);
            }
            .loading {
                text-align: center;
                padding: 60px;
                color: #9ca3af;
                font-size: 16px;
            }
            .empty-list {
                text-align: center;
                padding: 60px;
                color: #9ca3af;
                font-size: 16px;
            }
            .message {
                padding: 16px;
                border-radius: 12px;
                margin-bottom: 20px;
                display: none;
                font-weight: 500;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: rgba(34, 197, 94, 0.15);
                color: #4ade80;
                border: 1px solid rgba(34, 197, 94, 0.3);
            }
            .message.error {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.3);
            }
            .stats {
                background: #2c2c2c;
                padding: 24px;
                border-radius: 16px;
                margin-bottom: 30px;
                display: flex;
                justify-content: space-around;
                flex-wrap: wrap;
                gap: 30px;
                border: 1px solid rgba(59, 130, 246, 0.2);
            }
            .stat-item {
                text-align: center;
            }
            .stat-value {
                font-size: 32px;
                font-weight: 700;
                background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .stat-label {
                font-size: 13px;
                color: #9ca3af;
                margin-top: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            /* Модальное окно */
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(4px);
            }
            .modal.show {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .modal-content {
                background: #2c2c2c;
                border-radius: 20px;
                padding: 30px;
                max-width: 400px;
                width: 90%;
                border: 1px solid rgba(139, 92, 246, 0.3);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            }
            .modal-title {
                font-size: 20px;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 15px;
            }
            .modal-text {
                color: #e0e0e0;
                margin-bottom: 25px;
                line-height: 1.5;
            }
            .modal-actions {
                display: flex;
                gap: 12px;
                justify-content: flex-end;
            }
            .modal-btn {
                padding: 12px 24px;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            .modal-btn-cancel {
                background: rgba(139, 92, 246, 0.2);
                color: #a78bfa;
                border: 1px solid rgba(139, 92, 246, 0.4);
            }
            .modal-btn-cancel:hover {
                background: rgba(139, 92, 246, 0.3);
            }
            .modal-btn-confirm {
                background: #ef4444;
                color: #ffffff;
            }
            .modal-btn-confirm:hover {
                background: #dc2626;
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎬 Сконвертированные видео</h1>
            
            <div class="header-actions">
                <a href="/upload" class="btn btn-primary">⬆️ Загрузить видео</a>
                <a href="/files" class="btn btn-secondary">📁 Все файлы</a>
                <button type="button" class="btn btn-secondary" onclick="loadVideosList()">🔄 Обновить</button>
            </div>
            
            <div class="message" id="message"></div>
            
            <!-- Модальное окно подтверждения удаления -->
            <div class="modal" id="deleteModal">
                <div class="modal-content">
                    <div class="modal-title">🗑️ Удаление файла</div>
                    <div class="modal-text" id="modalText">Вы уверены, что хотите удалить этот файл? Это действие нельзя отменить.</div>
                    <div class="modal-actions">
                        <button type="button" class="modal-btn modal-btn-cancel" onclick="closeDeleteModal()">Отмена</button>
                        <button type="button" class="modal-btn modal-btn-confirm" id="confirmDeleteBtn">Удалить</button>
                    </div>
                </div>
            </div>
            
            <div class="stats" id="stats" style="display: none;">
                <div class="stat-item">
                    <div class="stat-value" id="totalFiles">0</div>
                    <div class="stat-label">Всего файлов</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="totalSize">0 MB</div>
                    <div class="stat-label">Общий размер</div>
                </div>
            </div>
            
            <div id="videosListContainer">
                <div class="loading">Загрузка списка видео...</div>
            </div>
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            tg.expand();

            // Загрузка списка видео
            async function loadVideosList() {
                const container = document.getElementById('videosListContainer');
                const message = document.getElementById('message');
                const stats = document.getElementById('stats');
                
                container.innerHTML = '<div class="loading">Загрузка списка видео...</div>';
                message.className = 'message';
                stats.style.display = 'none';
                
                try {
                    const response = await fetch('/api/converted');
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка при загрузке списка');
                    }
                    
                    const videos = data.videos || [];
                    
                    if (videos.length === 0) {
                        container.innerHTML = '<div class="empty-list">📭 Сконвертированных видео пока нет</div>';
                        return;
                    }
                    
                    // Подсчет статистики
                    const totalSize = videos.reduce((sum, v) => sum + v.size, 0);
                    const totalSizeMB = (totalSize / 1024 / 1024).toFixed(2);
                    
                    document.getElementById('totalFiles').textContent = videos.length;
                    document.getElementById('totalSize').textContent = totalSizeMB + ' MB';
                    stats.style.display = 'flex';
                    
                    // Формирование списка
                    let html = '';
                    videos.forEach(video => {
                        const date = new Date(video.created_at);
                        const dateStr = date.toLocaleString('ru-RU', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                        
                        html += `
                            <div class="video-item">
                                <div class="video-item-header">
                                    <div class="video-item-name">${escapeHtml(video.filename)}</div>
                                    <div class="video-item-size">${video.size_mb} MB</div>
                                </div>
                                <div class="video-item-date">
                                    📅 ${dateStr}
                                </div>
                                <div class="video-item-url" id="url-${escapeHtml(video.filename)}">
                                    ${escapeHtml(video.url)}
                                </div>
                                <div class="video-item-actions">
                                    <button type="button" class="video-item-btn btn-copy" onclick="copyVideoUrl('${escapeHtml(video.url)}', '${escapeHtml(video.filename)}')">
                                        📋 Копировать ссылку
                                    </button>
                                    <button type="button" class="video-item-btn btn-delete" onclick="deleteVideo('${escapeHtml(video.filename)}')">
                                        🗑️ Удалить
                                    </button>
                                </div>
                            </div>
                        `;
                    });
                    
                    container.innerHTML = html;
                } catch (error) {
                    container.innerHTML = '';
                    message.textContent = `Ошибка: ${escapeHtml(error.message)}`;
                    message.className = 'message error show';
                }
            }

            // Копирование ссылки на видео
            async function copyVideoUrl(url, filename) {
                try {
                    await navigator.clipboard.writeText(url);
                    showMessage(`✅ Ссылка на ${filename} скопирована!`, 'success');
                } catch (error) {
                    // Fallback для старых браузеров
                    const textArea = document.createElement('textarea');
                    textArea.value = url;
                    textArea.style.position = 'fixed';
                    textArea.style.opacity = '0';
                    document.body.appendChild(textArea);
                    textArea.select();
                    try {
                        document.execCommand('copy');
                        showMessage(`✅ Ссылка на ${filename} скопирована!`, 'success');
                    } catch (err) {
                        showMessage('❌ Не удалось скопировать ссылку', 'error');
                    }
                    document.body.removeChild(textArea);
                }
            }

            // Показать сообщение
            function showMessage(text, type) {
                const message = document.getElementById('message');
                message.textContent = text;
                message.className = `message ${type} show`;
                
                // Автоматически скрыть через 3 секунды
                setTimeout(() => {
                    message.className = 'message';
                }, 3000);
            }

            // Экранирование HTML
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Модальное окно для удаления
            let fileToDelete = null;
            
            function showDeleteModal(filename) {
                fileToDelete = filename;
                const modal = document.getElementById('deleteModal');
                const modalText = document.getElementById('modalText');
                modalText.textContent = `Вы уверены, что хотите удалить файл "${filename}"? Это действие нельзя отменить.`;
                modal.classList.add('show');
            }
            
            function closeDeleteModal() {
                const modal = document.getElementById('deleteModal');
                modal.classList.remove('show');
                fileToDelete = null;
            }
            
            // Удаление видео
            async function deleteVideo(filename) {
                showDeleteModal(filename);
            }
            
            // Подтверждение удаления
            async function confirmDelete() {
                if (!fileToDelete) return;
                
                const filename = fileToDelete;
                closeDeleteModal();
                
                try {
                    const response = await fetch(`/api/converted/${encodeURIComponent(filename)}`, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        showMessage(`✅ Файл ${filename} успешно удален!`, 'success');
                        // Обновляем список после удаления
                        setTimeout(() => loadVideosList(), 1000);
                    } else {
                        const error = await response.json();
                        showMessage(`❌ Ошибка при удалении: ${error.detail || 'Неизвестная ошибка'}`, 'error');
                    }
                } catch (error) {
                    showMessage(`❌ Ошибка при удалении: ${escapeHtml(error.message)}`, 'error');
                }
            }
            
            // Привязываем кнопку подтверждения
            document.addEventListener('DOMContentLoaded', function() {
                const confirmBtn = document.getElementById('confirmDeleteBtn');
                if (confirmBtn) {
                    confirmBtn.addEventListener('click', confirmDelete);
                }
                
                // Закрытие модального окна при клике вне его
                const modal = document.getElementById('deleteModal');
                if (modal) {
                    modal.addEventListener('click', function(e) {
                        if (e.target === modal) {
                            closeDeleteModal();
                        }
                    });
                }
            });

            // Загружаем список при загрузке страницы
            loadVideosList();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_template)


@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    return {
        "status": "ok",
        "videos_dir": str(VIDEOS_DIR.absolute()),
        "converted_dir": str(CONVERTED_DIR.absolute())
    }


@app.get("/api/converted")
async def list_converted():
    """
    GET /api/converted - возвращает список всех сконвертированных видео файлов
    
    Returns:
        JSON с массивом сконвертированных видео файлов (имя, размер, дата создания, URL)
    """
    try:
        videos = []
        
        # Получаем абсолютный путь к директории
        if CONVERTED_DIR.is_absolute():
            converted_path = CONVERTED_DIR
        else:
            converted_path = Path.cwd() / CONVERTED_DIR
        
        # Нормализуем путь
        converted_path = converted_path.resolve()
        
        if not converted_path.exists():
            logger.warning(f"Директория сконвертированных видео не существует: {converted_path}")
            return JSONResponse(content={"videos": []})
        
        # Проходим по всем файлам в директории
        for file_path in converted_path.iterdir():
            if file_path.is_file() and is_video_file(file_path.name):
                try:
                    file_size = file_path.stat().st_size
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    video_url = f"{PUBLIC_BASE_URL}/converted/{file_path.name}"
                    
                    videos.append({
                        "filename": file_path.name,
                        "size": file_size,
                        "size_mb": round(file_size / 1024 / 1024, 2),
                        "created_at": file_mtime.isoformat(),
                        "url": video_url
                    })
                except Exception as e:
                    logger.warning(f"Ошибка при обработке файла {file_path.name}: {e}")
                    continue
        
        # Сортируем по дате создания (новые первыми)
        videos.sort(key=lambda x: x["created_at"], reverse=True)
        
        logger.info(f"Найдено сконвертированных видео файлов: {len(videos)}")
        
        return JSONResponse(content={"videos": videos})
    except Exception as e:
        logger.error(f"❌ Ошибка при получении списка сконвертированных видео: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка: {str(e)}")


@app.delete("/api/converted/{filename}")
async def delete_converted(filename: str):
    """
    DELETE /api/converted/{filename} - удаляет сконвертированный видео файл
    
    Args:
        filename: Имя файла для удаления
        
    Returns:
        JSON с результатом операции
    """
    try:
        # Получаем абсолютный путь к директории
        if CONVERTED_DIR.is_absolute():
            converted_path = CONVERTED_DIR
        else:
            converted_path = Path.cwd() / CONVERTED_DIR
        
        # Нормализуем путь
        converted_path = converted_path.resolve()
        file_path = converted_path / filename
        file_path = file_path.resolve()
        
        # Проверка безопасности: файл должен быть внутри converted_path
        if not str(file_path).startswith(str(converted_path)):
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        
        # Проверяем, что файл существует
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден")
        
        # Проверяем, что это видео файл
        if not is_video_file(filename):
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат файла")
        
        # Удаляем файл
        file_path.unlink()
        
        logger.info(f"✅ Сконвертированный файл удален: {filename}")
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Файл {filename} успешно удален"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении сконвертированного файла: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении файла: {str(e)}")
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка сконвертированных видео: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка сконвертированных видео: {str(e)}")


@app.get("/api/videos")
async def list_videos():
    """
    GET /api/videos - возвращает список всех видео файлов
    
    Returns:
        JSON с массивом видео файлов (имя, размер, дата создания, URL)
    """
    try:
        videos = []
        
        # Получаем абсолютный путь к директории
        if VIDEOS_DIR.is_absolute():
            videos_path = VIDEOS_DIR
        else:
            # Если относительный путь, берем относительно текущей рабочей директории
            videos_path = Path.cwd() / VIDEOS_DIR
        
        # Нормализуем путь
        videos_path = videos_path.resolve()
        
        if not videos_path.exists():
            logger.warning(f"Директория видео не существует: {videos_path}")
            return JSONResponse(content={"videos": []})
        
        # Проходим по всем файлам в директории
        for file_path in videos_path.iterdir():
            if file_path.is_file() and is_video_file(file_path.name):
                try:
                    file_size = file_path.stat().st_size
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    video_url = f"{PUBLIC_BASE_URL}/videos/{file_path.name}"
                    
                    videos.append({
                        "filename": file_path.name,
                        "size": file_size,
                        "size_mb": round(file_size / 1024 / 1024, 2),
                        "created_at": file_mtime.isoformat(),
                        "url": video_url
                    })
                except Exception as e:
                    logger.warning(f"Ошибка при обработке файла {file_path.name}: {e}")
                    continue
        
        # Сортируем по дате создания (новые первыми)
        videos.sort(key=lambda x: x["created_at"], reverse=True)
        
        logger.info(f"Найдено видео файлов: {len(videos)}")
        
        return JSONResponse(content={"videos": videos})
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка видео: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка видео: {str(e)}")


@app.delete("/api/videos/{filename}")
async def delete_video(filename: str):
    """
    DELETE /api/videos/{filename} - удаляет видео файл
    
    Args:
        filename: Имя файла для удаления
        
    Returns:
        JSON с результатом удаления
    """
    try:
        # Проверяем, что это видео файл
        if not is_video_file(filename):
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат файла")
        
        # Получаем абсолютный путь к директории
        if VIDEOS_DIR.is_absolute():
            videos_path = VIDEOS_DIR
        else:
            videos_path = Path.cwd() / VIDEOS_DIR
        
        videos_path = videos_path.resolve()
        file_path = videos_path / filename
        
        # Нормализуем путь для безопасности
        file_path = file_path.resolve()
        
        # Проверяем, что файл находится в правильной директории (безопасность)
        if not str(file_path).startswith(str(videos_path)):
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        
        # Проверяем, что файл существует
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден")
        
        # Удаляем файл
        file_path.unlink()
        
        logger.info(f"✅ Видео удалено: {filename}")
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Видео {filename} успешно удалено"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении видео: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении видео: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    logger.info(f"📁 Директория для загруженных видео: {VIDEOS_DIR.absolute()}")
    logger.info(f"📁 Директория для сконвертированных видео: {CONVERTED_DIR.absolute()}")
    logger.info(f"🌐 Публичный URL: {PUBLIC_BASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

