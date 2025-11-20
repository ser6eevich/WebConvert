# 🔧 Исправление ошибки Nginx конфигурации

Ошибка `"location" directive is not allowed here` означает, что директива `location` находится не внутри блока `server`.

## 🔍 Диагностика

Проверьте конфигурацию:

```bash
# Посмотрите на строку 51 и окружающий код
sudo sed -n '45,55p' /etc/nginx/sites-available/video-upload

# Или откройте весь файл
sudo nano /etc/nginx/sites-available/video-upload
```

## ✅ Правильная конфигурация Nginx

Замените содержимое файла `/etc/nginx/sites-available/video-upload` на следующее:

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

        # ВАЖНО: Отключаем проверку индексов
        autoindex off;

        # Заголовки для видео
        add_header Content-Type video/mp4;
        add_header Accept-Ranges bytes;

        # Кэширование
        expires 30d;
        add_header Cache-Control "public, immutable";

        # CORS
        add_header Access-Control-Allow-Origin *;

        # Разрешаем доступ к файлам
        access_log off;
    }

    # Раздача сконвертированных видео файлов
    location /converted/ {
        alias /root/WebConvert/webapp/converted/;

        # ВАЖНО: Отключаем проверку индексов
        autoindex off;

        # Заголовки для видео
        add_header Content-Type video/mp4;
        add_header Accept-Ranges bytes;

        # Кэширование
        expires 30d;
        add_header Cache-Control "public, immutable";

        # CORS
        add_header Access-Control-Allow-Origin *;

        # Разрешаем доступ к файлам
        access_log off;
    }
}
```

**Важно:**

- Замените `ваш-домен.com` на ваш реальный домен в двух местах!
- Если используете другого пользователя (не `root`), замените `/root/WebConvert` на правильный путь
- Все директивы `location` должны быть **внутри** блока `server { }`

## 🔧 Шаги исправления

### 1. Откройте файл конфигурации

```bash
sudo nano /etc/nginx/sites-available/video-upload
```

### 2. Замените содержимое на правильную конфигурацию выше

### 3. Проверьте синтаксис

```bash
sudo nginx -t
```

Должно быть: `syntax is ok` и `test is successful`

### 4. Если синтаксис правильный, перезапустите Nginx

```bash
sudo systemctl restart nginx
```

### 5. Проверьте статус

```bash
sudo systemctl status nginx
```

## 🐛 Частые ошибки

### Ошибка 1: Незакрытая фигурная скобка

Убедитесь, что все блоки правильно закрыты:

- `server { ... }` - один раз
- Каждая `location { ... }` - правильно закрыта

### Ошибка 2: location вне server

Все директивы `location` должны быть внутри блока `server { }`:

```nginx
server {
    # Правильно
    location / {
        ...
    }
}

# Неправильно - location вне server
location / {
    ...
}
```

### Ошибка 3: Дублирование server

Убедитесь, что в файле только один блок `server { }` (или несколько, но правильно структурированных).

## ✅ Проверка после исправления

1. **Проверьте синтаксис:**

   ```bash
   sudo nginx -t
   ```

2. **Проверьте доступность:**

   ```bash
   curl -I https://ваш-домен.com/health
   curl -I https://ваш-домен.com/videos/имя_файла.mp4
   curl -I https://ваш-домен.com/converted/имя_файла.mp4
   ```

3. **Проверьте логи на ошибки:**
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```
