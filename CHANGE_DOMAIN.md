# Смена домена для WebApp

Инструкция по смене домена с `ikurganskiy.ru` на `convert-base.ru`.

## Шаг 1: Настройка DNS

1. Зайдите в панель управления вашего домена `convert-base.ru`
2. Добавьте A-запись:

   - **Имя/Поддомен:** `@` (или оставьте пустым для основного домена)
   - **Тип:** `A`
   - **Значение/IP:** IP адрес вашего сервера (тот же, что используется для `ikurganskiy.ru`)
   - **TTL:** 3600 (или автоматически)

3. Опционально, добавьте запись для `www`:

   - **Имя/Поддомен:** `www`
   - **Тип:** `A`
   - **Значение/IP:** тот же IP адрес сервера

4. Проверьте, что DNS записи распространились:

   ```bash
   # Проверка A-записи
   dig convert-base.ru +short
   dig www.convert-base.ru +short

   # Или используйте онлайн-сервис
   # https://dnschecker.org/#A/convert-base.ru
   ```

## Шаг 2: Обновление Nginx конфигурации

1. Создайте новый конфигурационный файл для нового домена:

   ```bash
   sudo nano /etc/nginx/sites-available/convert-base
   ```

2. Добавьте следующую конфигурацию:

   ```nginx
   server {
       listen 80;
       server_name convert-base.ru www.convert-base.ru;

       # Логи
       access_log /var/log/nginx/convert-base-access.log;
       error_log /var/log/nginx/convert-base-error.log;

       # Максимальный размер загружаемого файла
       client_max_body_size 2G;

       # Основной location - проксируем на FastAPI
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_cache_bypass $http_upgrade;
           proxy_read_timeout 300s;
           proxy_connect_timeout 300s;
       }

       # Статические файлы - видео из папки upload
       location /videos/ {
           alias /root/WebConvert/webapp/videos/;
           expires 30d;
           add_header Cache-Control "public, immutable";
           autoindex off;
           access_log off;

           # Безопасность
           add_header X-Content-Type-Options "nosniff";
           add_header X-Frame-Options "SAMEORIGIN";
       }

       # Статические файлы - сконвертированные видео
       location /converted/ {
           alias /root/WebConvert/webapp/converted/;
           expires 30d;
           add_header Cache-Control "public, immutable";
           autoindex off;
           access_log off;

           # Безопасность
           add_header X-Content-Type-Options "nosniff";
           add_header X-Frame-Options "SAMEORIGIN";
       }
   }
   ```

   **ВАЖНО:** Не добавляйте блок с `listen 443` и SSL сертификатами сейчас! Certbot автоматически добавит HTTPS блок и настроит редирект после получения сертификата.

3. Активируйте конфигурацию:

   ```bash
   sudo ln -s /etc/nginx/sites-available/convert-base /etc/nginx/sites-enabled/
   ```

4. Проверьте конфигурацию:

   ```bash
   sudo nginx -t
   ```

5. Если проверка прошла успешно, перезагрузите Nginx:
   ```bash
   sudo systemctl reload nginx
   ```

## Шаг 3: Получение SSL сертификата

1. Установите Certbot (если еще не установлен):

   ```bash
   sudo apt update
   sudo apt install certbot python3-certbot-nginx -y
   ```

2. Получите SSL сертификат для нового домена:

   ```bash
   sudo certbot --nginx -d ikurganskiy.ru -d www.ikurganskiy.ru
   ```

3. Certbot автоматически:

   - Получит сертификат от Let's Encrypt
   - Обновит конфигурацию Nginx
   - Настроит автоматическое обновление

4. Проверьте, что сертификат получен:
   ```bash
   sudo certbot certificates
   ```

## Шаг 4: Обновление переменных окружения

1. Обновите `.env` файл бота:

   ```bash
   cd /root/WebConvert
   nano .env
   ```

2. Измените `VIDEO_WEBAPP_URL`:

   ```env
   VIDEO_WEBAPP_URL=https://convert-base.ru/upload
   ```

3. Обновите `.env` файл webapp:

   ```bash
   cd /root/WebConvert/webapp
   nano .env
   ```

4. Проверьте, что все переменные корректны (если есть ссылки на старый домен, обновите их)

## Шаг 5: Перезапуск сервисов

1. Перезапустите бота:

   ```bash
   sudo systemctl restart WebConvert
   ```

2. Перезапустите webapp:

   ```bash
   sudo systemctl restart webapp
   ```

3. Перезапустите Nginx (если нужно):
   ```bash
   sudo systemctl restart nginx
   ```

## Шаг 6: Проверка работы

1. Проверьте доступность сайта:

   ```bash
   curl -I https://convert-base.ru/health
   ```

2. Откройте в браузере:

   - https://convert-base.ru/upload
   - https://convert-base.ru/files
   - https://convert-base.ru/converted

3. Проверьте, что бот отправляет правильную ссылку:
   - Отправьте боту команду `/start`
   - Проверьте, что кнопка WebApp ведет на новый домен

## Шаг 7: Опционально - отключение старого домена

Если вы больше не хотите использовать `ikurganskiy.ru` для webapp:

1. Отключите старую конфигурацию Nginx:

   ```bash
   sudo rm /etc/nginx/sites-enabled/video-upload
   # или другое имя файла конфигурации для ikurganskiy.ru
   ```

2. Проверьте конфигурацию:

   ```bash
   sudo nginx -t
   ```

3. Перезагрузите Nginx:
   ```bash
   sudo systemctl reload nginx
   ```

## Проверка DNS распространения

После настройки DNS, проверьте распространение записей:

```bash
# Проверка A-записи
dig convert-base.ru +short
dig www.convert-base.ru +short

# Проверка с разных локаций (онлайн)
# https://dnschecker.org/#A/convert-base.ru
```

Обычно DNS записи распространяются в течение 5-30 минут, но может занять до 24 часов.

## Устранение проблем

### Проблема: DNS не распространился

- Подождите до 24 часов
- Проверьте настройки DNS в панели управления доменом
- Убедитесь, что A-запись указывает на правильный IP

### Проблема: SSL сертификат не получен

- Убедитесь, что DNS записи распространились
- Проверьте, что порты 80 и 443 открыты в firewall
- Убедитесь, что домен доступен из интернета

### Проблема: 502 Bad Gateway

- Проверьте статус webapp: `sudo systemctl status webapp`
- Проверьте логи: `sudo journalctl -u webapp -f`
- Убедитесь, что webapp слушает на порту 8000: `sudo netstat -tlnp | grep 8000`

### Проблема: Бот все еще отправляет старую ссылку

- Проверьте `.env` файл бота
- Перезапустите бота: `sudo systemctl restart WebConvert`
- Проверьте логи: `sudo journalctl -u WebConvert -f`

## Итоговая проверка

После выполнения всех шагов проверьте:

1. ✅ DNS записи настроены и распространились
2. ✅ Nginx конфигурация создана и активирована
3. ✅ SSL сертификат получен и настроен
4. ✅ Переменные окружения обновлены
5. ✅ Сервисы перезапущены
6. ✅ Сайт доступен по новому домену
7. ✅ Бот отправляет правильную ссылку

Готово! Теперь ваш webapp доступен по адресу `https://convert-base.ru`
