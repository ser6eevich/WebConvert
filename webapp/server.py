"""
Backend сервер для загрузки видео через Telegram Web App
Использует FastAPI для обработки HTTP запросов
"""
import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
from dotenv import load_dotenv

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
    file_path = VIDEOS_DIR / filename
    
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


if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    logger.info(f"📁 Директория для видео: {VIDEOS_DIR.absolute()}")
    logger.info(f"🌐 Публичный URL: {PUBLIC_BASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

