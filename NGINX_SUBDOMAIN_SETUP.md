# 🌐 Настройка поддомена для Web App

Если на основном домене уже работает другой сайт, лучше использовать поддомен для Web App.

## 📋 Варианты решения

### Вариант 1: Поддомен (рекомендуется)

Используйте поддомен, например: `webapp.ikurganskiy.ru` или `upload.ikurganskiy.ru`

### Вариант 2: Путь на том же домене

Используйте путь, например: `ikurganskiy.ru/webapp/` (но это сложнее настроить)

## 🚀 Вариант 1: Настройка поддомена (рекомендуется)

### Шаг 1: Настройте DNS для поддомена

В панели управления доменом добавьте A-запись для поддомена:

- **Type:** `A Record`
- **Host:** `webapp` (или `upload`)
- **Value:** IP адрес вашего сервера (тот же, что для основного домена)
- **TTL:** `Automatic`

Пример:

- `webapp.ikurganskiy.ru` → IP сервера
- Или `upload.ikurganskiy.ru` → IP сервера

### Шаг 2: Создайте отдельную конфигурацию Nginx для поддомена

```bash
sudo nano /etc/nginx/sites-available/webapp-ikurganskiy
```

Добавьте следующую конфигурацию:

```nginx
server {
    listen 80;
    server_name webapp.ikurganskiy.ru;  # Или upload.ikurganskiy.ru

    # Логи
    access_log /var/log/nginx/webapp-access.log;
    error_log /var/log/nginx/webapp-error.log;

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

### Шаг 3: Активируйте конфигурацию

```bash
sudo ln -s /etc/nginx/sites-available/webapp-ikurganskiy /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Шаг 4: Настройте SSL для поддомена

```bash
sudo certbot --nginx -d webapp.ikurganskiy.ru
```

### Шаг 5: Обновите .env файлы

**В `webapp/.env`:**

```env
PUBLIC_BASE_URL=https://webapp.ikurganskiy.ru
```

**В `.env` бота (корень проекта):**

```env
VIDEO_WEBAPP_URL=https://webapp.ikurganskiy.ru/upload
```

### Шаг 6: Перезапустите сервисы

```bash
sudo systemctl restart webapp
sudo systemctl restart WebConvert
```

## 🔄 Вариант 2: Использование пути на том же домене

Если хотите использовать путь на основном домене (например, `ikurganskiy.ru/webapp/`), нужно:

1. Обновить конфигурацию основного сайта
2. Добавить location `/webapp/` в существующую конфигурацию
3. Это сложнее, так как нужно координировать с существующим сайтом

**Рекомендую использовать поддомен** - это проще и чище.

## ✅ Проверка

После настройки поддомена:

1. **Проверьте DNS:**

   ```bash
   nslookup webapp.ikurganskiy.ru
   ```

2. **Проверьте доступность:**

   ```bash
   curl -I http://webapp.ikurganskiy.ru/health
   ```

3. **После настройки SSL:**

   ```bash
   curl -I https://webapp.ikurganskiy.ru/health
   ```

4. **Проверьте в браузере:**
   - `https://webapp.ikurganskiy.ru/upload`
   - `https://webapp.ikurganskiy.ru/files`
   - `https://webapp.ikurganskiy.ru/converted`
