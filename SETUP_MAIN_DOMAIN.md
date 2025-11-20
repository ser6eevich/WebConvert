# 🌐 Настройка основного домена для Web App

Инструкция по настройке основного домена `ikurganskiy.ru` для Web App бота WebConvert.

## 🔧 Шаг 1: Обновите конфигурацию Nginx

Откройте файл конфигурации:

```bash
sudo nano /etc/nginx/sites-available/video-upload
```

Замените содержимое на следующее:

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

    # Раздача статических видео файлов (загруженные)
    location /videos/ {
        alias /root/WebConvert/webapp/videos/;
        autoindex off;
        add_header Content-Type video/mp4;
        add_header Accept-Ranges bytes;
        expires 30d;
        add_header Cache-Control "public, immutable";
        add_header Access-Control-Allow-Origin *;
        access_log off;
    }

    # Раздача сконвертированных видео файлов
    location /converted/ {
        alias /root/WebConvert/webapp/converted/;
        autoindex off;
        add_header Content-Type video/mp4;
        add_header Accept-Ranges bytes;
        expires 30d;
        add_header Cache-Control "public, immutable";
        add_header Access-Control-Allow-Origin *;
        access_log off;
    }
}
```

**Важно:**

- Если используете другого пользователя (не `root`), замените `/root/WebConvert` на правильный путь
- Все директивы `location` должны быть **внутри** блока `server { }`

## 🔧 Шаг 2: Проверьте и активируйте конфигурацию

```bash
# Убедитесь, что конфигурация активирована
sudo ln -sf /etc/nginx/sites-available/video-upload /etc/nginx/sites-enabled/

# Удалите другие конфигурации для этого домена (если есть)
# Проверьте, какие конфигурации активны
ls -la /etc/nginx/sites-enabled/

# Если есть конфигурация для Milo-bot, временно отключите её:
# sudo rm /etc/nginx/sites-enabled/milo-bot-config  # Замените на реальное имя файла

# Проверьте синтаксис
sudo nginx -t
```

## 🔧 Шаг 3: Перезапустите Nginx

```bash
sudo systemctl restart nginx
sudo systemctl status nginx
```

## 🔧 Шаг 4: Настройте SSL (если еще не настроен)

```bash
sudo certbot --nginx -d ikurganskiy.ru -d www.ikurganskiy.ru
```

Если SSL уже настроен, certbot обновит конфигурацию автоматически.

## 🔧 Шаг 5: Обновите .env файлы

### В `webapp/.env`:

```env
PUBLIC_BASE_URL=https://ikurganskiy.ru
VIDEOS_DIR=videos
CONVERTED_DIR=converted
WEBAPP_PORT=8000
MAX_FILE_SIZE=2147483648
```

### В `.env` бота (корень проекта `/root/WebConvert/.env`):

```env
TELEGRAM_BOT_TOKEN=ваш_токен
OPENAI_API_KEY=ваш_ключ
GPT_ASSISTANT_ID=asst_xxxxx
GPT_ASSISTANT_ID_VIDEOS=asst_xxxxx
TELEGRAM_LOCAL_API_URL=http://72.56.73.219:8081
VIDEO_WEBAPP_URL=https://ikurganskiy.ru/upload
WEBAPP_CONVERTED_DIR=webapp/converted
```

**Важно:**

- `VIDEO_WEBAPP_URL` должен быть с `https://` и заканчиваться на `/upload`
- `PUBLIC_BASE_URL` должен быть с `https://` и БЕЗ слеша в конце

## 🔧 Шаг 6: Перезапустите сервисы

```bash
sudo systemctl restart webapp
sudo systemctl restart WebConvert
sudo systemctl restart nginx
```

## ✅ Проверка

1. **Проверьте доступность:**

   ```bash
   curl -I https://ikurganskiy.ru/health
   curl -I https://ikurganskiy.ru/upload
   ```

2. **Проверьте в браузере:**

   - `https://ikurganskiy.ru/upload` - должна открыться страница загрузки
   - `https://ikurganskiy.ru/files` - список всех файлов
   - `https://ikurganskiy.ru/converted` - список сконвертированных видео

3. **Проверьте бота:**
   - Откройте бота в Telegram
   - Нажмите кнопку "🎬 Загрузить видео"
   - Должна открыться Web App

## 🐛 Если что-то не работает

### Проверьте логи:

```bash
# Логи Nginx
sudo tail -f /var/log/nginx/error.log

# Логи webapp
sudo journalctl -u webapp -f

# Логи бота
sudo journalctl -u WebConvert -f
```

### Проверьте, что порт 8000 слушается:

```bash
sudo netstat -tulpn | grep 8000
```

### Проверьте, что webapp запущен:

```bash
sudo systemctl status webapp
```

## 📝 Примечания

- Если на домене был настроен Milo-bot, его конфигурация Nginx должна быть отключена или перемещена на другой домен/поддомен
- Убедитесь, что Milo-bot использует свой отдельный домен (как вы упомянули)
- Основной домен `ikurganskiy.ru` теперь будет обслуживать Web App бота WebConvert
