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
PORT = int(os.getenv('WEBAPP_PORT', '8000'))

# Создаем директорию для видео, если её нет
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Директория для видео: {VIDEOS_DIR.absolute()}")

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
                background: var(--tg-theme-bg-color, #ffffff);
                color: var(--tg-theme-text-color, #000000);
                padding: 20px;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }
            .container {
                max-width: 500px;
                width: 100%;
                background: var(--tg-theme-secondary-bg-color, #f0f0f0);
                border-radius: 12px;
                padding: 30px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                text-align: center;
                margin-bottom: 20px;
                color: var(--tg-theme-text-color, #000000);
            }
            .upload-area {
                border: 2px dashed var(--tg-theme-button-color, #3390ec);
                border-radius: 8px;
                padding: 40px 20px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
                background: var(--tg-theme-bg-color, #ffffff);
            }
            .upload-area:hover {
                border-color: var(--tg-theme-button-color, #3390ec);
                background: var(--tg-theme-secondary-bg-color, #f5f5f5);
            }
            .upload-area.dragover {
                border-color: var(--tg-theme-button-color, #3390ec);
                background: var(--tg-theme-hint-color, #999999);
            }
            input[type="file"] {
                display: none;
            }
            .file-label {
                display: block;
                cursor: pointer;
                color: var(--tg-theme-button-color, #3390ec);
                font-weight: 500;
            }
            .file-info {
                margin-top: 15px;
                padding: 10px;
                background: var(--tg-theme-bg-color, #ffffff);
                border-radius: 6px;
                display: none;
            }
            .file-info.show {
                display: block;
            }
            button {
                width: 100%;
                padding: 12px 24px;
                margin-top: 20px;
                background: var(--tg-theme-button-color, #3390ec);
                color: var(--tg-theme-button-text-color, #ffffff);
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                transition: background 0.3s;
            }
            button:hover:not(:disabled) {
                opacity: 0.9;
            }
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .progress {
                width: 100%;
                height: 8px;
                background: var(--tg-theme-secondary-bg-color, #f0f0f0);
                border-radius: 4px;
                margin-top: 15px;
                overflow: hidden;
                display: none;
            }
            .progress.show {
                display: block;
            }
            .progress-bar {
                height: 100%;
                background: var(--tg-theme-button-color, #3390ec);
                width: 0%;
                transition: width 0.3s;
            }
            .message {
                margin-top: 15px;
                padding: 12px;
                border-radius: 6px;
                display: none;
            }
            .message.show {
                display: block;
            }
            .message.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .message.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .video-url {
                margin-top: 15px;
                padding: 12px;
                background: var(--tg-theme-bg-color, #ffffff);
                border-radius: 6px;
                word-break: break-all;
                display: none;
            }
            .video-url.show {
                display: block;
            }
            .send-button {
                margin-top: 15px;
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
                background: #dc3545;
                color: #ffffff;
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
            
            <div class="videos-list">
                <h2>📹 Загруженные видео</h2>
                <button type="button" class="btn-refresh" onclick="loadVideosList()">
                    🔄 Обновить список
                </button>
                <div id="videosListContainer">
                    <div class="loading">Загрузка списка видео...</div>
                </div>
            </div>
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
                            
                            // Обновляем список видео после успешной загрузки
                            setTimeout(() => {
                                loadVideosList();
                            }, 500);
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

            // Загрузка списка видео
            async function loadVideosList() {
                const container = document.getElementById('videosListContainer');
                container.innerHTML = '<div class="loading">Загрузка списка видео...</div>';
                
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
                                <div style="font-size: 0.85em; color: var(--tg-theme-hint-color, #999999);">
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
                    container.innerHTML = `<div class="message error show">Ошибка: ${escapeHtml(error.message)}</div>`;
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
    
    template = Template(html_template)
    return template.render(max_file_size=MAX_FILE_SIZE)


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
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
        
        # Формируем публичный URL
        video_url = f"{PUBLIC_BASE_URL}/videos/{unique_filename}"
        
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


@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    return {"status": "ok", "videos_dir": str(VIDEOS_DIR.absolute())}


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
    logger.info(f"📁 Директория для видео: {VIDEOS_DIR.absolute()}")
    logger.info(f"🌐 Публичный URL: {PUBLIC_BASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

