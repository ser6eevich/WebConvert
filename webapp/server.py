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
TEXTS_DIR = Path(os.getenv('TEXTS_DIR', 'texts'))  # Папка для текстовых документов
PORT = int(os.getenv('WEBAPP_PORT', '8000'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')  # Токен бота для отправки уведомлений
TELEGRAM_NOTIFY_CHAT_ID = os.getenv('TELEGRAM_NOTIFY_CHAT_ID', '')  # ID чата для уведомлений (опционально)

# Создаем директории, если их нет
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
TEXTS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Директория для загруженных видео: {VIDEOS_DIR.absolute()}")
logger.info(f"Директория для сконвертированных видео: {CONVERTED_DIR.absolute()}")
logger.info(f"Директория для текстовых документов: {TEXTS_DIR.absolute()}")

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
            :root {
                --tg-theme-bg-color: #ffffff;
                --tg-theme-text-color: #000000;
                --tg-theme-hint-color: #999999;
                --tg-theme-link-color: #3390ec;
                --tg-theme-button-color: #3390ec;
                --tg-theme-button-text-color: #ffffff;
                --tg-theme-secondary-bg-color: #f1f1f1;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: var(--tg-theme-bg-color, #ffffff);
                color: var(--tg-theme-text-color, #000000);
                padding: 16px;
                min-height: 100vh;
                line-height: 1.5;
            }
            .container {
                max-width: 600px;
                width: 100%;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 24px;
                color: var(--tg-theme-text-color, #000000);
                font-size: 24px;
                font-weight: 600;
            }
            .nav-links {
                display: flex;
                gap: 8px;
                margin-bottom: 24px;
                flex-wrap: wrap;
            }
            .nav-btn {
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                text-decoration: none;
                font-size: 14px;
                font-weight: 500;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .nav-btn:active {
                background: #e0e0e0;
            }
            .upload-area {
                border: 2px dashed #d0d0d0;
                border-radius: 8px;
                padding: 40px 20px;
                text-align: center;
                cursor: pointer;
                transition: border-color 0.2s;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                margin-bottom: 16px;
            }
            .upload-area.dragover {
                border-color: var(--tg-theme-button-color, #3390ec);
                background: #f0f7ff;
            }
            input[type="file"] {
                display: none;
            }
            .file-label {
                display: block;
                cursor: pointer;
                color: var(--tg-theme-text-color, #000000);
                font-weight: 500;
                font-size: 15px;
            }
            .file-info {
                margin-top: 16px;
                padding: 12px;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                border-radius: 8px;
                display: none;
                border: 1px solid #e0e0e0;
                color: var(--tg-theme-text-color, #000000);
                font-size: 14px;
            }
            .file-info.show {
                display: block;
            }
            input[type="text"] {
                width: 100%;
                padding: 10px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                background: var(--tg-theme-bg-color, #ffffff);
                color: var(--tg-theme-text-color, #000000);
                margin-top: 8px;
            }
            input[type="text"]:focus {
                outline: none;
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            label {
                display: block;
                margin-bottom: 8px;
                color: var(--tg-theme-text-color, #000000);
                font-weight: 500;
                font-size: 14px;
            }
            button {
                width: 100%;
                padding: 12px 16px;
                margin-top: 16px;
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border: 1px solid var(--tg-theme-button-color, #3390ec);
                border-radius: 8px;
                font-size: 15px;
                font-weight: 500;
                cursor: pointer;
                transition: opacity 0.2s;
            }
            button:active:not(:disabled) {
                opacity: 0.8;
            }
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .progress {
                width: 100%;
                height: 6px;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                border-radius: 3px;
                margin-top: 16px;
                overflow: hidden;
                display: none;
                border: 1px solid #e0e0e0;
            }
            .progress.show {
                display: block;
            }
            .progress-bar {
                height: 100%;
                background: var(--tg-theme-button-color, #3390ec);
                width: 0%;
                transition: width 0.3s ease;
            }
            .message {
                margin-top: 16px;
                padding: 12px 16px;
                border-radius: 8px;
                display: none;
                font-size: 14px;
                border: 1px solid;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: #f0f9ff;
                color: #0369a1;
                border-color: #bae6fd;
            }
            .message.error {
                background: #fef2f2;
                color: #991b1b;
                border-color: #fecaca;
            }
            .video-url {
                margin-top: 16px;
                padding: 12px;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                border-radius: 8px;
                word-break: break-all;
                display: none;
                border: 1px solid #e0e0e0;
                color: var(--tg-theme-link-color, #3390ec);
                font-size: 13px;
            }
            .video-url.show {
                display: block;
            }
            .send-button {
                margin-top: 16px;
                display: none;
            }
            .send-button.show {
                display: block;
            }
            @media (max-width: 480px) {
                body {
                    padding: 12px;
                }
                h1 {
                    font-size: 20px;
                    margin-bottom: 16px;
                }
                .upload-area {
                    padding: 30px 15px;
                }
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
            <div class="nav-links">
                <a href="/files" class="nav-btn">Все файлы</a>
                <a href="/converted" class="nav-btn">Сконвертированные</a>
                <a href="/texts" class="nav-btn">Тексты</a>
            </div>
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="upload-area" id="uploadArea">
                    <label for="fileInput" class="file-label">
                        Нажмите для выбора файла<br>
                        или перетащите видео сюда
                    </label>
                    <input type="file" id="fileInput" name="file" accept="video/*" required>
                </div>
                <div class="file-info" id="fileInfo"></div>
                <div style="margin-top: 20px;">
                    <label for="fileNameInput">
                        Название файла (необязательно):
                    </label>
                    <input type="text" id="fileNameInput" name="filename" placeholder="Оставьте пустым для автоматического названия">
                </div>
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
                
                // Получаем имя файла из поля ввода (если указано)
                const fileNameInput = document.getElementById('fileNameInput');
                const customFileName = fileNameInput.value.trim();
                if (customFileName) {
                    formData.append('custom_filename', customFileName);
                }
                
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
async def upload_video(file: UploadFile = File(...), user_id: Optional[str] = Form(None), custom_filename: Optional[str] = Form(None)):
    """
    POST /upload - принимает видео файл и сохраняет его на сервере
    
    Args:
        file: Загружаемый видео файл
        user_id: ID пользователя из Telegram WebApp
        custom_filename: Пользовательское имя файла (необязательно)
        
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
        
        # Генерируем имя файла
        if custom_filename and custom_filename.strip():
            # Используем пользовательское имя, но добавляем расширение если его нет
            custom_name = custom_filename.strip()
            ext = get_file_extension(file.filename)
            if not custom_name.endswith(ext):
                custom_name = f"{custom_name}{ext}"
            # Делаем имя безопасным для файловой системы
            import re
            custom_name = re.sub(r'[^\w\s\-_\.]', '', custom_name)
            custom_name = re.sub(r'\s+', '_', custom_name)
            # Добавляем уникальный ID чтобы избежать конфликтов
            unique_id = str(uuid.uuid4())[:8]
            unique_filename = f"{custom_name.rsplit('.', 1)[0]}_{unique_id}.{custom_name.rsplit('.', 1)[1] if '.' in custom_name else ext.lstrip('.')}"
        else:
            # Генерируем уникальное имя файла автоматически
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
                    
                    # Экранируем специальные символы для HTML
                    # В HTML нужно экранировать только <, >, &
                    escaped_filename = unique_filename.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    
                    message_text = (
                        f"📹 <b>Новое видео загружено на сайт!</b>\n\n"
                        f"📁 Файл: <code>{escaped_filename}</code>\n"
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
                        "parse_mode": "HTML",
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Все файлы</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            :root {
                --tg-theme-bg-color: #ffffff;
                --tg-theme-text-color: #000000;
                --tg-theme-hint-color: #999999;
                --tg-theme-link-color: #3390ec;
                --tg-theme-button-color: #3390ec;
                --tg-theme-button-text-color: #ffffff;
                --tg-theme-secondary-bg-color: #f1f1f1;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: var(--tg-theme-bg-color, #ffffff);
                color: var(--tg-theme-text-color, #000000);
                padding: 16px;
                min-height: 100vh;
                line-height: 1.5;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 24px;
                color: var(--tg-theme-text-color, #000000);
                font-size: 24px;
                font-weight: 600;
            }
            .header-actions {
                display: flex;
                gap: 8px;
                margin-bottom: 24px;
                flex-wrap: wrap;
            }
            .btn {
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                text-decoration: none;
                display: inline-block;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .btn:active {
                background: #e0e0e0;
            }
            .btn-primary {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            .btn-primary:active {
                opacity: 0.8;
            }
            .message {
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                display: none;
                font-size: 14px;
                border: 1px solid;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: #f0f9ff;
                color: #0369a1;
                border-color: #bae6fd;
            }
            .message.error {
                background: #fef2f2;
                color: #991b1b;
                border-color: #fecaca;
            }
            .stats {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 24px;
                display: flex;
                justify-content: space-around;
                flex-wrap: wrap;
                gap: 16px;
                border: 1px solid #e0e0e0;
            }
            .stat-item {
                text-align: center;
            }
            .stat-value {
                font-size: 24px;
                font-weight: 600;
                color: var(--tg-theme-text-color, #000000);
            }
            .stat-label {
                font-size: 12px;
                color: var(--tg-theme-hint-color, #999999);
                margin-top: 4px;
            }
            .video-item {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
                border: 1px solid #e0e0e0;
            }
            .video-item-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 8px;
            }
            .video-item-name {
                font-weight: 500;
                color: var(--tg-theme-text-color, #000000);
                word-break: break-word;
                flex: 1;
                font-size: 15px;
                min-width: 0;
            }
            .video-item-size {
                color: var(--tg-theme-hint-color, #999999);
                font-size: 13px;
                white-space: nowrap;
            }
            .video-item-date {
                font-size: 12px;
                color: var(--tg-theme-hint-color, #999999);
                margin-bottom: 12px;
            }
            .video-item-url {
                background: #ffffff;
                padding: 10px;
                border-radius: 6px;
                word-break: break-all;
                font-size: 12px;
                color: var(--tg-theme-link-color, #3390ec);
                border: 1px solid #e0e0e0;
                font-family: 'Courier New', monospace;
                margin-bottom: 12px;
            }
            .video-item-actions {
                display: flex;
                gap: 8px;
            }
            .video-item-btn {
                flex: 1;
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                background: #ffffff;
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .video-item-btn:active {
                background: #f0f0f0;
            }
            .btn-copy {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            .btn-copy:active {
                opacity: 0.8;
            }
            .btn-delete {
                background: #ffffff;
                color: #dc2626;
                border-color: #dc2626;
            }
            .btn-delete:active {
                background: #fef2f2;
            }
            .loading, .empty-list {
                text-align: center;
                padding: 40px 20px;
                color: var(--tg-theme-hint-color, #999999);
                font-size: 14px;
            }
            /* Модальное окно */
            .modal-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 1000;
                align-items: center;
                justify-content: center;
                padding: 16px;
            }
            .modal-overlay.show {
                display: flex;
            }
            .modal {
                background: var(--tg-theme-bg-color, #ffffff);
                border-radius: 12px;
                padding: 24px;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            }
            .modal-title {
                font-size: 18px;
                font-weight: 600;
                margin-bottom: 12px;
                color: var(--tg-theme-text-color, #000000);
            }
            .modal-text {
                font-size: 14px;
                color: var(--tg-theme-hint-color, #666666);
                margin-bottom: 20px;
                word-break: break-word;
            }
            .modal-filename {
                font-weight: 500;
                color: var(--tg-theme-text-color, #000000);
                margin-top: 8px;
            }
            .modal-actions {
                display: flex;
                gap: 8px;
            }
            .modal-btn {
                flex: 1;
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: background-color 0.2s;
            }
            .modal-btn-cancel {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
            }
            .modal-btn-cancel:active {
                background: #e0e0e0;
            }
            .modal-btn-confirm {
                background: #dc2626;
                color: #ffffff;
                border-color: #dc2626;
            }
            .modal-btn-confirm:active {
                opacity: 0.8;
            }
            @media (max-width: 480px) {
                body {
                    padding: 12px;
                }
                h1 {
                    font-size: 20px;
                    margin-bottom: 16px;
                }
                .header-actions {
                    flex-direction: column;
                }
                .btn {
                    width: 100%;
                    text-align: center;
                }
                .video-item-actions {
                    flex-direction: column;
                }
                .modal {
                    padding: 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Все файлы</h1>
            
            <div class="header-actions">
                <a href="/upload" class="btn btn-primary">Загрузить видео</a>
                <a href="/converted" class="btn">Сконвертированные</a>
                <a href="/texts" class="btn">Тексты</a>
                <button type="button" class="btn" onclick="loadVideosList()">Обновить</button>
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
        
        <!-- Модальное окно для удаления -->
        <div class="modal-overlay" id="deleteModal" onclick="if(event.target === this) closeDeleteModal()">
            <div class="modal">
                <div class="modal-title">Удалить файл?</div>
                <div class="modal-text">
                    Вы уверены, что хотите удалить этот файл? Это действие нельзя отменить.
                </div>
                <div class="modal-filename" id="modalFilename"></div>
                <div class="modal-actions">
                    <button class="modal-btn modal-btn-cancel" onclick="closeDeleteModal()">Отмена</button>
                    <button class="modal-btn modal-btn-confirm" onclick="confirmDelete()">Удалить</button>
                </div>
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
                        container.innerHTML = '<div class="empty-list">Видео файлов пока нет</div>';
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
                                    ${dateStr}
                                </div>
                                <div class="video-item-url" id="url-${escapeHtml(video.filename)}">
                                    ${escapeHtml(video.url)}
                                </div>
                                <div class="video-item-actions">
                                    <button type="button" class="video-item-btn btn-copy" onclick="copyVideoUrl('${escapeHtml(video.url)}', '${escapeHtml(video.filename)}')">
                                        Копировать ссылку
                                    </button>
                                    <button type="button" class="video-item-btn btn-delete" onclick="deleteVideo('${escapeHtml(video.filename)}')">
                                        Удалить
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
                    showMessage(`Ссылка на ${filename} скопирована`, 'success');
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
                        showMessage(`Ссылка на ${filename} скопирована`, 'success');
                    } catch (err) {
                        showMessage('❌ Не удалось скопировать ссылку', 'error');
                    }
                    document.body.removeChild(textArea);
                }
            }

            let fileToDelete = null;
            
            // Показать модальное окно удаления
            function showDeleteModal(filename) {
                fileToDelete = filename;
                document.getElementById('modalFilename').textContent = filename;
                document.getElementById('deleteModal').classList.add('show');
            }
            
            // Закрыть модальное окно
            function closeDeleteModal() {
                fileToDelete = null;
                document.getElementById('deleteModal').classList.remove('show');
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
                    const response = await fetch(`/api/videos/${encodeURIComponent(filename)}`, {
                        method: 'DELETE'
                    });
                    
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка при удалении');
                    }
                    
                    showMessage(`Видео ${filename} удалено`, 'success');
                    
                    // Обновляем список
                    setTimeout(() => {
                        loadVideosList();
                    }, 500);
                } catch (error) {
                    showMessage(`Ошибка: ${escapeHtml(error.message)}`, 'error');
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Сконвертированные видео</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            :root {
                --tg-theme-bg-color: #ffffff;
                --tg-theme-text-color: #000000;
                --tg-theme-hint-color: #999999;
                --tg-theme-link-color: #3390ec;
                --tg-theme-button-color: #3390ec;
                --tg-theme-button-text-color: #ffffff;
                --tg-theme-secondary-bg-color: #f1f1f1;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: var(--tg-theme-bg-color, #ffffff);
                color: var(--tg-theme-text-color, #000000);
                padding: 16px;
                min-height: 100vh;
                line-height: 1.5;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 24px;
                color: var(--tg-theme-text-color, #000000);
                font-size: 24px;
                font-weight: 600;
            }
            .header-actions {
                display: flex;
                gap: 8px;
                margin-bottom: 24px;
                flex-wrap: wrap;
            }
            .btn {
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                text-decoration: none;
                display: inline-block;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .btn:active {
                background: #e0e0e0;
            }
            .btn-primary {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            .btn-primary:active {
                opacity: 0.8;
            }
            .message {
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                display: none;
                font-size: 14px;
                border: 1px solid;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: #f0f9ff;
                color: #0369a1;
                border-color: #bae6fd;
            }
            .message.error {
                background: #fef2f2;
                color: #991b1b;
                border-color: #fecaca;
            }
            .stats {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 24px;
                display: flex;
                justify-content: space-around;
                flex-wrap: wrap;
                gap: 16px;
                border: 1px solid #e0e0e0;
            }
            .stat-item {
                text-align: center;
            }
            .stat-value {
                font-size: 24px;
                font-weight: 600;
                color: var(--tg-theme-text-color, #000000);
            }
            .stat-label {
                font-size: 12px;
                color: var(--tg-theme-hint-color, #999999);
                margin-top: 4px;
            }
            .video-item {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
                border: 1px solid #e0e0e0;
            }
            .video-item-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 8px;
            }
            .video-item-name {
                font-weight: 500;
                color: var(--tg-theme-text-color, #000000);
                word-break: break-word;
                flex: 1;
                font-size: 15px;
                min-width: 0;
            }
            .video-item-size {
                color: var(--tg-theme-hint-color, #999999);
                font-size: 13px;
                white-space: nowrap;
            }
            .video-item-date {
                font-size: 12px;
                color: var(--tg-theme-hint-color, #999999);
                margin-bottom: 12px;
            }
            .video-item-url {
                background: #ffffff;
                padding: 10px;
                border-radius: 6px;
                word-break: break-all;
                font-size: 12px;
                color: var(--tg-theme-link-color, #3390ec);
                border: 1px solid #e0e0e0;
                font-family: 'Courier New', monospace;
                margin-bottom: 12px;
            }
            .video-item-actions {
                display: flex;
                gap: 8px;
            }
            .video-item-btn {
                flex: 1;
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                background: #ffffff;
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .video-item-btn:active {
                background: #f0f0f0;
            }
            .btn-copy {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            .btn-copy:active {
                opacity: 0.8;
            }
            .btn-delete {
                background: #ffffff;
                color: #dc2626;
                border-color: #dc2626;
            }
            .btn-delete:active {
                background: #fef2f2;
            }
            .loading, .empty-list {
                text-align: center;
                padding: 40px 20px;
                color: var(--tg-theme-hint-color, #999999);
                font-size: 14px;
            }
            /* Модальное окно */
            .modal-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 1000;
                align-items: center;
                justify-content: center;
                padding: 16px;
            }
            .modal-overlay.show {
                display: flex;
            }
            .modal {
                background: var(--tg-theme-bg-color, #ffffff);
                border-radius: 12px;
                padding: 24px;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            }
            .modal-title {
                font-size: 18px;
                font-weight: 600;
                margin-bottom: 12px;
                color: var(--tg-theme-text-color, #000000);
            }
            .modal-text {
                font-size: 14px;
                color: var(--tg-theme-hint-color, #666666);
                margin-bottom: 20px;
                word-break: break-word;
            }
            .modal-filename {
                font-weight: 500;
                color: var(--tg-theme-text-color, #000000);
                margin-top: 8px;
            }
            .modal-actions {
                display: flex;
                gap: 8px;
            }
            .modal-btn {
                flex: 1;
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: background-color 0.2s;
            }
            .modal-btn-cancel {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
            }
            .modal-btn-cancel:active {
                background: #e0e0e0;
            }
            .modal-btn-confirm {
                background: #dc2626;
                color: #ffffff;
                border-color: #dc2626;
            }
            .modal-btn-confirm:active {
                opacity: 0.8;
            }
            @media (max-width: 480px) {
                body {
                    padding: 12px;
                }
                h1 {
                    font-size: 20px;
                    margin-bottom: 16px;
                }
                .header-actions {
                    flex-direction: column;
                }
                .btn {
                    width: 100%;
                    text-align: center;
                }
                .video-item-actions {
                    flex-direction: column;
                }
                .modal {
                    padding: 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Сконвертированные видео</h1>
            
            <div class="header-actions">
                <a href="/upload" class="btn btn-primary">Загрузить видео</a>
                <a href="/files" class="btn">Все файлы</a>
                <a href="/texts" class="btn">Тексты</a>
                <a href="/files" class="btn">Все файлы</a>
                <button type="button" class="btn" onclick="loadVideosList()">Обновить</button>
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
        
        <!-- Модальное окно для удаления -->
        <div class="modal-overlay" id="deleteModal" onclick="if(event.target === this) closeDeleteModal()">
            <div class="modal">
                <div class="modal-title">Удалить файл?</div>
                <div class="modal-text">
                    Вы уверены, что хотите удалить этот файл? Это действие нельзя отменить.
                </div>
                <div class="modal-filename" id="modalFilename"></div>
                <div class="modal-actions">
                    <button class="modal-btn modal-btn-cancel" onclick="closeDeleteModal()">Отмена</button>
                    <button class="modal-btn modal-btn-confirm" onclick="confirmDelete()">Удалить</button>
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
                        container.innerHTML = '<div class="empty-list">Сконвертированных видео пока нет</div>';
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
                                    ${dateStr}
                                </div>
                                <div class="video-item-url" id="url-${escapeHtml(video.filename)}">
                                    ${escapeHtml(video.url)}
                                </div>
                                <div class="video-item-actions">
                                    <button type="button" class="video-item-btn btn-copy" onclick="copyVideoUrl('${escapeHtml(video.url)}', '${escapeHtml(video.filename)}')">
                                        Копировать ссылку
                                    </button>
                                    <button type="button" class="video-item-btn btn-delete" onclick="deleteVideo('${escapeHtml(video.filename)}')">
                                        Удалить
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
                    showMessage(`Ссылка на ${filename} скопирована`, 'success');
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
                        showMessage(`Ссылка на ${filename} скопирована`, 'success');
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

            let fileToDelete = null;
            
            // Показать модальное окно удаления
            function showDeleteModal(filename) {
                fileToDelete = filename;
                document.getElementById('modalFilename').textContent = filename;
                document.getElementById('deleteModal').classList.add('show');
            }
            
            // Закрыть модальное окно
            function closeDeleteModal() {
                fileToDelete = null;
                document.getElementById('deleteModal').classList.remove('show');
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
                    
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка при удалении');
                    }
                    
                    showMessage(`Видео ${filename} удалено`, 'success');
                    
                    // Обновляем список
                    setTimeout(() => {
                        loadVideosList();
                    }, 500);
                } catch (error) {
                    showMessage(`Ошибка: ${escapeHtml(error.message)}`, 'error');
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


@app.get("/texts", response_class=HTMLResponse)
async def texts_list():
    """
    GET /texts - отображает HTML страницу со списком всех текстовых документов
    """
    html_template = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Текстовые документы</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            :root {
                --tg-theme-bg-color: #ffffff;
                --tg-theme-text-color: #000000;
                --tg-theme-hint-color: #999999;
                --tg-theme-link-color: #3390ec;
                --tg-theme-button-color: #3390ec;
                --tg-theme-button-text-color: #ffffff;
                --tg-theme-secondary-bg-color: #f1f1f1;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: var(--tg-theme-bg-color, #ffffff);
                color: var(--tg-theme-text-color, #000000);
                padding: 16px;
                min-height: 100vh;
                line-height: 1.5;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 24px;
                color: var(--tg-theme-text-color, #000000);
                font-size: 24px;
                font-weight: 600;
            }
            .header-actions {
                display: flex;
                gap: 8px;
                margin-bottom: 24px;
                flex-wrap: wrap;
            }
            .btn {
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                text-decoration: none;
                display: inline-block;
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .btn:active {
                background: #e0e0e0;
            }
            .btn-primary {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            .btn-primary:active {
                opacity: 0.8;
            }
            .message {
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                display: none;
                font-size: 14px;
                border: 1px solid;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: #f0f9ff;
                color: #0369a1;
                border-color: #bae6fd;
            }
            .message.error {
                background: #fef2f2;
                color: #991b1b;
                border-color: #fecaca;
            }
            .stats {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 24px;
                display: flex;
                justify-content: space-around;
                flex-wrap: wrap;
                gap: 16px;
                border: 1px solid #e0e0e0;
            }
            .stat-item {
                text-align: center;
            }
            .stat-value {
                font-size: 24px;
                font-weight: 600;
                color: var(--tg-theme-text-color, #000000);
            }
            .stat-label {
                font-size: 12px;
                color: var(--tg-theme-hint-color, #999999);
                margin-top: 4px;
            }
            .text-item {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
                border: 1px solid #e0e0e0;
            }
            .text-item-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 8px;
            }
            .text-item-name {
                font-weight: 500;
                color: var(--tg-theme-text-color, #000000);
                word-break: break-word;
                flex: 1;
                font-size: 15px;
                min-width: 0;
            }
            .text-item-size {
                color: var(--tg-theme-hint-color, #999999);
                font-size: 13px;
                white-space: nowrap;
            }
            .text-item-date {
                font-size: 12px;
                color: var(--tg-theme-hint-color, #999999);
                margin-bottom: 12px;
            }
            .text-item-actions {
                display: flex;
                gap: 8px;
            }
            .text-item-btn {
                flex: 1;
                padding: 10px 16px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                background: #ffffff;
                color: var(--tg-theme-text-color, #000000);
                transition: background-color 0.2s;
            }
            .text-item-btn:active {
                background: #f0f0f0;
            }
            .btn-download {
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border-color: var(--tg-theme-button-color, #3390ec);
            }
            .btn-download:active {
                opacity: 0.8;
            }
            .btn-delete {
                background: #ffffff;
                color: #dc2626;
                border-color: #dc2626;
            }
            .btn-delete:active {
                background: #fef2f2;
            }
            .loading {
                text-align: center;
                padding: 40px;
                color: var(--tg-theme-hint-color, #999999);
            }
            .empty-list {
                text-align: center;
                padding: 40px;
                color: var(--tg-theme-hint-color, #999999);
            }
            .modal-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 1000;
                align-items: center;
                justify-content: center;
            }
            .modal-overlay.show {
                display: flex;
            }
            .modal {
                background: var(--tg-theme-bg-color, #ffffff);
                border-radius: 12px;
                padding: 24px;
                max-width: 90%;
                width: 400px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            }
            .modal-title {
                font-size: 18px;
                font-weight: 600;
                margin-bottom: 12px;
                color: var(--tg-theme-text-color, #000000);
            }
            .modal-text {
                font-size: 14px;
                color: var(--tg-theme-text-color, #000000);
                margin-bottom: 20px;
                line-height: 1.5;
            }
            .modal-actions {
                display: flex;
                gap: 12px;
            }
            .modal-btn {
                flex: 1;
                padding: 12px;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: opacity 0.2s;
            }
            .modal-btn-cancel {
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
                color: var(--tg-theme-text-color, #000000);
            }
            .modal-btn-confirm {
                background: #dc2626;
                color: #ffffff;
            }
            .modal-btn:active {
                opacity: 0.8;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📄 Текстовые документы</h1>
            <div class="header-actions">
                <a href="/upload" class="btn">Загрузка</a>
                <a href="/files" class="btn">Все файлы</a>
                <a href="/converted" class="btn">Сконвертированные</a>
            </div>
            <div class="message" id="message"></div>
            <div class="stats" id="stats">
                <div class="stat-item">
                    <div class="stat-value" id="totalCount">0</div>
                    <div class="stat-label">Всего документов</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="totalSize">0 KB</div>
                    <div class="stat-label">Общий размер</div>
                </div>
            </div>
            <div id="textsList"></div>
        </div>

        <div class="modal-overlay" id="deleteModal" onclick="if(event.target === this) closeDeleteModal()">
            <div class="modal">
                <div class="modal-title">Удалить документ?</div>
                <div class="modal-text">
                    Вы уверены, что хотите удалить документ "<span id="modalFilename"></span>"? Это действие нельзя отменить.
                </div>
                <div class="modal-actions">
                    <button class="modal-btn modal-btn-cancel" onclick="closeDeleteModal()">Отмена</button>
                    <button class="modal-btn modal-btn-confirm" onclick="confirmDelete()">Удалить</button>
                </div>
            </div>
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            tg.expand();

            let texts = [];
            let deleteFilename = null;

            async function loadTexts() {
                const listDiv = document.getElementById('textsList');
                listDiv.innerHTML = '<div class="loading">Загрузка...</div>';

                try {
                    const response = await fetch('/api/texts');
                    const data = await response.json();
                    texts = data.texts || [];

                    updateStats();
                    renderTexts();
                } catch (error) {
                    listDiv.innerHTML = '<div class="empty-list">Ошибка при загрузке документов</div>';
                    showMessage('Ошибка при загрузке документов', 'error');
                }
            }

            function updateStats() {
                const totalCount = texts.length;
                const totalSize = texts.reduce((sum, text) => sum + text.size, 0);
                const totalSizeKB = (totalSize / 1024).toFixed(2);

                document.getElementById('totalCount').textContent = totalCount;
                document.getElementById('totalSize').textContent = totalSizeKB + ' KB';
            }

            function renderTexts() {
                const listDiv = document.getElementById('textsList');

                if (texts.length === 0) {
                    listDiv.innerHTML = '<div class="empty-list">Нет текстовых документов</div>';
                    return;
                }

                listDiv.innerHTML = texts.map(text => {
                    const date = new Date(text.created_at);
                    const dateStr = date.toLocaleDateString('ru-RU', {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    });

                    return `
                        <div class="text-item">
                            <div class="text-item-header">
                                <div class="text-item-name">${escapeHtml(text.filename)}</div>
                                <div class="text-item-size">${text.size_kb} KB</div>
                            </div>
                            <div class="text-item-date">${dateStr}</div>
                            <div class="text-item-actions">
                                <button class="text-item-btn btn-download" onclick="downloadText('${escapeHtml(text.filename)}')">
                                    Скачать
                                </button>
                                <button class="text-item-btn btn-delete" onclick="openDeleteModal('${escapeHtml(text.filename)}')">
                                    Удалить
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function downloadText(filename) {
                window.open(`/texts/${encodeURIComponent(filename)}`, '_blank');
            }

            function openDeleteModal(filename) {
                deleteFilename = filename;
                document.getElementById('modalFilename').textContent = filename;
                document.getElementById('deleteModal').classList.add('show');
            }

            function closeDeleteModal() {
                deleteFilename = null;
                document.getElementById('deleteModal').classList.remove('show');
            }

            async function confirmDelete() {
                if (!deleteFilename) return;

                try {
                    const response = await fetch(`/api/texts/${encodeURIComponent(deleteFilename)}`, {
                        method: 'DELETE'
                    });

                    const data = await response.json();

                    if (response.ok) {
                        showMessage('Документ успешно удален', 'success');
                        closeDeleteModal();
                        await loadTexts();
                    } else {
                        showMessage(data.detail || 'Ошибка при удалении документа', 'error');
                    }
                } catch (error) {
                    showMessage('Ошибка при удалении документа', 'error');
                }
            }

            function showMessage(text, type) {
                const messageDiv = document.getElementById('message');
                messageDiv.textContent = text;
                messageDiv.className = `message show ${type}`;
                setTimeout(() => {
                    messageDiv.classList.remove('show');
                }, 3000);
            }

            loadTexts();
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
        "converted_dir": str(CONVERTED_DIR.absolute()),
        "texts_dir": str(TEXTS_DIR.absolute())
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


# Разрешенные расширения текстовых файлов
TEXT_EXTENSIONS = {'.txt', '.doc', '.docx', '.md', '.rtf'}


def is_text_file(filename: str) -> bool:
    """Проверяет, является ли файл текстовым документом"""
    ext = Path(filename).suffix.lower()
    return ext in TEXT_EXTENSIONS


@app.get("/api/texts")
async def list_texts():
    """
    GET /api/texts - возвращает список всех текстовых документов
    
    Returns:
        JSON с массивом текстовых документов (имя, размер, дата создания, URL)
    """
    try:
        texts = []
        
        # Получаем абсолютный путь к директории
        if TEXTS_DIR.is_absolute():
            texts_path = TEXTS_DIR
        else:
            texts_path = Path.cwd() / TEXTS_DIR
        
        # Нормализуем путь
        texts_path = texts_path.resolve()
        
        if not texts_path.exists():
            logger.warning(f"Директория текстов не существует: {texts_path}")
            return JSONResponse(content={"texts": []})
        
        # Проходим по всем файлам в директории
        for file_path in texts_path.iterdir():
            if file_path.is_file() and is_text_file(file_path.name):
                try:
                    file_size = file_path.stat().st_size
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    text_url = f"{PUBLIC_BASE_URL}/texts/{file_path.name}"
                    
                    texts.append({
                        "filename": file_path.name,
                        "size": file_size,
                        "size_kb": round(file_size / 1024, 2),
                        "created_at": file_mtime.isoformat(),
                        "url": text_url
                    })
                except Exception as e:
                    logger.warning(f"Ошибка при обработке файла {file_path.name}: {e}")
                    continue
        
        # Сортируем по дате создания (новые первыми)
        texts.sort(key=lambda x: x['created_at'], reverse=True)
        
        return JSONResponse(content={"texts": texts})
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка текстов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка текстов: {str(e)}")


@app.delete("/api/texts/{filename}")
async def delete_text(filename: str):
    """
    DELETE /api/texts/{filename} - удаляет текстовый документ
    
    Args:
        filename: Имя файла для удаления
        
    Returns:
        JSON с результатом удаления
    """
    try:
        # Проверяем, что это текстовый файл
        if not is_text_file(filename):
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат файла")
        
        # Получаем абсолютный путь к директории
        if TEXTS_DIR.is_absolute():
            texts_path = TEXTS_DIR
        else:
            texts_path = Path.cwd() / TEXTS_DIR
        
        texts_path = texts_path.resolve()
        file_path = texts_path / filename
        
        # Нормализуем путь для безопасности
        file_path = file_path.resolve()
        
        # Проверяем, что файл находится в правильной директории (безопасность)
        if not str(file_path).startswith(str(texts_path)):
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        
        # Проверяем, что файл существует
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден")
        
        # Удаляем файл
        file_path.unlink()
        
        logger.info(f"✅ Текстовый документ удален: {filename}")
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Документ {filename} успешно удален"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении текстового документа: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении документа: {str(e)}")


@app.get("/texts/{filename}")
async def get_text_file(filename: str):
    """
    GET /texts/{filename} - возвращает текстовый файл для скачивания
    
    Args:
        filename: Имя файла
        
    Returns:
        Файл для скачивания
    """
    try:
        # Получаем абсолютный путь к директории
        if TEXTS_DIR.is_absolute():
            texts_path = TEXTS_DIR
        else:
            texts_path = Path.cwd() / TEXTS_DIR
        
        texts_path = texts_path.resolve()
        file_path = texts_path / filename
        
        # Нормализуем путь для безопасности
        file_path = file_path.resolve()
        
        # Проверяем, что файл находится в правильной директории (безопасность)
        if not str(file_path).startswith(str(texts_path)):
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        
        # Проверяем, что файл существует
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении текстового файла: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении файла: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    logger.info(f"📁 Директория для загруженных видео: {VIDEOS_DIR.absolute()}")
    logger.info(f"📁 Директория для сконвертированных видео: {CONVERTED_DIR.absolute()}")
    logger.info(f"🌐 Публичный URL: {PUBLIC_BASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

