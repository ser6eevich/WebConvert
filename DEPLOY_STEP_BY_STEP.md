# 🚀 Пошаговая инструкция: от локального тестирования до развертывания на сервере

Эта инструкция проведет вас через весь процесс: от проверки конвертера до полного развертывания на сервере с вашим доменом.

## 📋 План действий

1. ✅ Проверка конвертера локально
2. 📦 Подготовка файлов к загрузке
3. 🖥️ Настройка сервера
4. 🌐 Настройка DNS (привязка домена)
5. 📤 Загрузка файлов на сервер
6. ⚙️ Настройка Web App с доменом
7. ✅ Финальная проверка

---

## ✅ Шаг 1: Проверка конвертера локально

### 1.1. Проверьте, что FFmpeg установлен

```bash
ffmpeg -version
```

Если команда не работает, установите FFmpeg (см. `FFMPEG_INSTALL_WINDOWS.md`).

### 1.2. Проверьте настройки бота

Убедитесь, что в `.env` файле (в корне проекта) есть все необходимые переменные:

```env
TELEGRAM_BOT_TOKEN=ваш_токен_бота
OPENAI_API_KEY=ваш_openai_ключ
GPT_ASSISTANT_ID=asst_xxxxx
GPT_ASSISTANT_ID_VIDEOS=asst_xxxxx
```

### 1.3. Запустите бота локально

```bash
python bot.py
```

### 1.4. Протестируйте конвертер

1. Откройте Telegram бота
2. Нажмите `/start`
3. Нажмите "📹 Конвертер"
4. Отправьте небольшое видео (до 50MB) или ссылку на видео
5. Дождитесь конвертации

**Ожидаемый результат:** Бот должен скачать видео, сконвертировать его в MP4 1920x1080 и отправить обратно.

### 1.5. Если конвертер работает

✅ **Отлично!** Переходите к следующему шагу.

❌ **Если не работает:**

- Проверьте логи бота на ошибки
- Убедитесь, что FFmpeg установлен и доступен
- Проверьте, что видео файл не поврежден

---

## 📦 Шаг 2: Подготовка файлов к загрузке

### 2.1. Создайте список файлов для загрузки

Вам нужно загрузить на сервер:

```
telegram-bot/
├── bot.py
├── video_converter.py
├── text_generator.py
├── requirements.txt
├── .env (с настройками)
└── webapp/
    ├── server.py
    ├── requirements.txt
    └── .env (с настройками для backend)
```

### 2.2. Подготовьте `.env` файлы

#### A. `.env` для бота (в корне проекта)

```env
TELEGRAM_BOT_TOKEN=ваш_токен_бота
OPENAI_API_KEY=ваш_openai_ключ
GPT_ASSISTANT_ID=asst_xxxxx
GPT_ASSISTANT_ID_VIDEOS=asst_xxxxx

# Локальный Bot API (если используете)
TELEGRAM_LOCAL_API_URL=http://localhost:8081

# URL для Web App (пока оставьте пустым, настроим позже)
VIDEO_WEBAPP_URL=https://ваш-домен.com/upload
```

**Важно:** Замените `ваш-домен.com` на ваш реальный домен!

#### B. `webapp/.env` для backend

Создайте файл `webapp/.env`:

```env
# Публичный URL вашего домена (БЕЗ слеша в конце!)
PUBLIC_BASE_URL=https://ваш-домен.com

# Директория для сохранения видео
VIDEOS_DIR=videos

# Порт для backend сервера
WEBAPP_PORT=8000

# Максимальный размер файла в байтах (2GB)
MAX_FILE_SIZE=2147483648
```

**Важно:** Замените `ваш-домен.com` на ваш реальный домен!

### 2.3. Проверьте структуру проекта

Убедитесь, что у вас есть папка `webapp/` с файлами:

- `webapp/server.py`
- `webapp/requirements.txt`
- `webapp/.env` (создайте, если нет)

---

## 🖥️ Шаг 3: Настройка сервера

### 3.1. Подключитесь к серверу

```bash
ssh root@ВАШ_IP_АДРЕС
```

Или если создали пользователя:

```bash
ssh botuser@ВАШ_IP_АДРЕС
```

### 3.2. Обновите систему

```bash
sudo apt update
sudo apt upgrade -y
```

### 3.3. Установите необходимые пакеты

```bash
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git ufw
```

### 3.4. Настройте файрвол

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

### 3.5. Создайте пользователя (если еще не создали)

```bash
adduser botuser
usermod -aG sudo botuser
su - botuser
```

---

## 🌐 Шаг 4: Настройка DNS (привязка домена к серверу)

Этот шаг нужно сделать **ДО** загрузки файлов, чтобы DNS успел обновиться.

### 4.1. Узнайте IP адрес вашего сервера

На сервере выполните:

```bash
curl ifconfig.me
```

Или посмотрите в панели управления вашего VPS провайдера.

**Запишите IP адрес!** (например: `157.230.123.45`)

### 4.2. Настройте DNS записи

Войдите в панель управления вашего регистратора домена (Namecheap, GoDaddy, Reg.ru и т.д.).

#### Для Namecheap:

1. Войдите в аккаунт
2. Domain List → Manage (рядом с вашим доменом)
3. Перейдите в раздел **"Advanced DNS"**
4. Найдите секцию **"Host Records"**

5. **Добавьте A-запись для основного домена:**

   - Type: `A Record`
   - Host: `@` (или оставьте пустым)
   - Value: **IP адрес вашего сервера**
   - TTL: `Automatic` (или 300)
   - Нажмите "Save"

6. **Добавьте A-запись для www:**
   - Type: `A Record`
   - Host: `www`
   - Value: **IP адрес вашего сервера**
   - TTL: `Automatic`
   - Нажмите "Save"

#### Для других регистраторов:

Ищите раздел "DNS Management", "DNS Settings" или "Управление DNS".

Добавьте две A-записи:

- `@` → IP адрес сервера
- `www` → IP адрес сервера

### 4.3. Проверьте DNS

Подождите 5-30 минут (DNS обновляется не мгновенно), затем проверьте:

1. Откройте https://dnschecker.org/
2. Введите ваш домен
3. Выберите тип записи: `A`
4. Нажмите "Search"
5. Убедитесь, что все серверы показывают ваш IP адрес

**Важно:** Не продолжайте, пока DNS не обновится!

---

## 📤 Шаг 5: Загрузка файлов на сервер

### 5.1. Создайте директории на сервере

```bash
# Создаем директорию для бота
mkdir -p ~/telegram-bot
cd ~/telegram-bot

# Создаем директорию для Web App
mkdir -p ~/video-upload-webapp
```

### 5.2. Загрузите файлы бота

**Вариант A: Через SCP (с вашего компьютера)**

На вашем компьютере (Windows PowerShell или терминал):

```powershell
# Загрузите основные файлы бота
scp bot.py video_converter.py text_generator.py requirements.txt botuser@ВАШ_IP:/home/botuser/telegram-bot/

# Загрузите .env файл (будет запрошен пароль)
scp .env botuser@ВАШ_IP:/home/botuser/telegram-bot/
```

**Вариант B: Через SFTP (FileZilla, WinSCP)**

1. Установите FileZilla: https://filezilla-project.org/
2. Подключитесь:
   - Host: `sftp://ВАШ_IP`
   - Username: `botuser`
   - Password: ваш пароль
3. Перетащите файлы:
   - `bot.py`, `video_converter.py`, `text_generator.py`, `requirements.txt` → `/home/botuser/telegram-bot/`
   - `.env` → `/home/botuser/telegram-bot/`

**Вариант C: Через Git (если проект в репозитории)**

```bash
cd ~/telegram-bot
git clone https://github.com/ваш-username/ваш-репозиторий.git .
```

### 5.3. Загрузите файлы Web App backend

```powershell
# Загрузите файлы Web App
scp -r webapp/* botuser@ВАШ_IP:/home/botuser/video-upload-webapp/webapp/
```

Или через FileZilla:

- `webapp/server.py` → `/home/botuser/video-upload-webapp/webapp/`
- `webapp/requirements.txt` → `/home/botuser/video-upload-webapp/webapp/`
- `webapp/.env` → `/home/botuser/video-upload-webapp/webapp/`

### 5.4. Проверьте загрузку

На сервере:

```bash
ls -la ~/telegram-bot/
ls -la ~/video-upload-webapp/webapp/
```

Должны быть все файлы.

---

## ⚙️ Шаг 6: Настройка на сервере

### 6.1. Настройка бота

```bash
cd ~/telegram-bot

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install --upgrade pip
pip install -r requirements.txt

# Проверьте .env файл
nano .env
```

Убедитесь, что в `.env` указан правильный домен:

```env
VIDEO_WEBAPP_URL=https://ваш-домен.com/upload
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 6.2. Настройка Web App backend

```bash
cd ~/video-upload-webapp

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
cd webapp
pip install --upgrade pip
pip install -r requirements.txt

# Создайте директорию для видео
cd ~/video-upload-webapp
mkdir -p videos
chmod 755 videos

# Проверьте .env файл
nano webapp/.env
```

Убедитесь, что в `webapp/.env` указан правильный домен:

```env
PUBLIC_BASE_URL=https://ваш-домен.com
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 6.3. Протестируйте запуск (вручную)

#### Тест backend:

```bash
cd ~/video-upload-webapp/webapp
source ~/video-upload-webapp/venv/bin/activate
python server.py
```

Если всё работает, остановите: `Ctrl+C`

#### Тест бота:

```bash
cd ~/telegram-bot
source venv/bin/activate
python bot.py
```

Если всё работает, остановите: `Ctrl+C`

---

## 🌐 Шаг 7: Настройка Nginx и SSL

### 7.1. Создайте конфигурацию Nginx

```bash
sudo nano /etc/nginx/sites-available/video-upload
```

Добавьте следующее (замените `ваш-домен.com` на ваш домен):

```nginx
server {
    listen 80;
    server_name ikurganskiy.ru www.ikurganskiy.ru;

    # Логи
    access_log /var/log/nginx/video-upload-access.log;
    error_log /var/log/nginx/video-upload-error.log;

    # Максимальный размер загружаемого файла (2GB)
    client_max_body_size 2G;
    client_body_timeout 300s;

    # Проксирование на backend
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Таймауты для больших файлов
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # Раздача статических видео файлов
    location /videos/ {
        alias /home/botuser/video-upload-webapp/videos/;

        # Заголовки для видео
        add_header Content-Type video/mp4;
        add_header Accept-Ranges bytes;

        # Кэширование
        expires 30d;
        add_header Cache-Control "public, immutable";

        # CORS
        add_header Access-Control-Allow-Origin *;
    }
}
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 7.2. Активируйте конфигурацию

```bash
sudo ln -s /etc/nginx/sites-available/video-upload /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Удалите дефолтную конфигурацию
```

### 7.3. Проверьте конфигурацию

```bash
sudo nginx -t
```

Должно быть: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

### 7.4. Перезапустите Nginx

```bash
sudo systemctl restart nginx
```

### 7.5. Получите SSL сертификат (HTTPS)

```bash
sudo certbot --nginx -d ваш-домен.com -d www.ваш-домен.com
```

Следуйте инструкциям:

- Введите email
- Согласитесь с условиями (A)
- Выберите, перенаправлять ли HTTP на HTTPS (рекомендуется: 2)

### 7.6. Проверьте автообновление сертификата

```bash
sudo certbot renew --dry-run
```

---

## 🔄 Шаг 8: Настройка автозапуска

### 8.1. Создайте service для бота

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

Добавьте:

```ini
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/telegram-bot
Environment="PATH=/home/botuser/telegram-bot/venv/bin"
ExecStart=/home/botuser/telegram-bot/venv/bin/python /home/botuser/telegram-bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 8.2. Создайте service для Web App backend

```bash
sudo nano /etc/systemd/system/video-upload-webapp.service
```

Добавьте:

```ini
[Unit]
Description=Video Upload WebApp Backend
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/video-upload-webapp/webapp
Environment="PATH=/home/botuser/video-upload-webapp/venv/bin"
ExecStart=/home/botuser/video-upload-webapp/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 8.3. Активируйте и запустите сервисы

```bash
# Обновите systemd
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable telegram-bot
sudo systemctl enable video-upload-webapp

# Запустите сервисы
sudo systemctl start telegram-bot
sudo systemctl start video-upload-webapp
```

### 8.4. Проверьте статус

```bash
sudo systemctl status telegram-bot
sudo systemctl status video-upload-webapp
```

Оба должны показывать `active (running)`

---

## ✅ Шаг 9: Финальная проверка

### 9.1. Проверьте доступность сайта

Откройте в браузере: `https://ваш-домен.com/upload`

Должна открыться страница загрузки видео.

### 9.2. Проверьте health endpoint

```bash
curl https://ваш-домен.com/health
```

Должен вернуться JSON: `{"status":"ok",...}`

### 9.3. Проверьте бота в Telegram

1. Откройте Telegram бота
2. Отправьте `/start`
3. **Должна появиться кнопка "🎬 Загрузить видео"**
4. Нажмите на неё
5. Должна открыться Web App страница загрузки

### 9.4. Протестируйте загрузку видео

1. На странице Web App выберите видео файл
2. Нажмите "Загрузить видео"
3. Дождитесь загрузки
4. Нажмите "Отправить ссылку в Telegram"
5. Бот должен отправить вам сообщение с прямой ссылкой на видео

### 9.5. Протестируйте конвертер

1. Отправьте боту видео (через обычную отправку)
2. Бот должен сконвертировать его в MP4 1920x1080

---

## 🐛 Устранение неполадок

### Бот не запускается

```bash
# Проверьте логи
sudo journalctl -u telegram-bot -n 50

# Проверьте .env файл
cat ~/telegram-bot/.env
```

### Backend не запускается

```bash
# Проверьте логи
sudo journalctl -u video-upload-webapp -n 50

# Проверьте .env файл
cat ~/video-upload-webapp/webapp/.env
```

### Web App не открывается

1. Проверьте DNS: https://dnschecker.org/
2. Проверьте, что Nginx работает: `sudo systemctl status nginx`
3. Проверьте логи Nginx: `sudo tail -f /var/log/nginx/video-upload-error.log`
4. Проверьте, что backend работает: `sudo systemctl status video-upload-webapp`

### Ошибка SSL

```bash
# Проверьте сертификат
sudo certbot certificates

# Обновите сертификат вручную
sudo certbot renew
```

---

## 📝 Полезные команды

### Просмотр логов

```bash
# Логи бота
sudo journalctl -u telegram-bot -f

# Логи backend
sudo journalctl -u video-upload-webapp -f

# Логи Nginx
sudo tail -f /var/log/nginx/video-upload-error.log
```

### Перезапуск сервисов

```bash
sudo systemctl restart telegram-bot
sudo systemctl restart video-upload-webapp
sudo systemctl restart nginx
```

### Обновление кода

```bash
# Остановите сервисы
sudo systemctl stop telegram-bot
sudo systemctl stop video-upload-webapp

# Обновите файлы (через git pull или scp)

# Переустановите зависимости (если нужно)
cd ~/telegram-bot
source venv/bin/activate
pip install -r requirements.txt

cd ~/video-upload-webapp/webapp
source ~/video-upload-webapp/venv/bin/activate
pip install -r requirements.txt

# Запустите сервисы
sudo systemctl start telegram-bot
sudo systemctl start video-upload-webapp
```

---

## 🎉 Готово!

Теперь ваш бот работает на сервере 24/7 с вашим доменом!

**Что дальше:**

- Настройте резервное копирование
- Настройте мониторинг (опционально)
- Регулярно обновляйте систему: `sudo apt update && sudo apt upgrade`
