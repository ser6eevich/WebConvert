# 🔍 Проверка запущенных процессов

## Проверка процессов WebConvert

Выполните эти команды для диагностики:

```bash
# 1. Проверьте процессы WebConvert
ps aux | grep WebConvert

# 2. Проверьте процессы bot.py в WebConvert
ps aux | grep "WebConvert.*bot.py"

# 3. Проверьте все процессы Python
ps aux | grep python | grep -v grep

# 4. Проверьте статус systemd сервисов
sudo systemctl status WebConvert
sudo systemctl status webapp

# 5. Проверьте, что слушает на порту 8000
sudo netstat -tulpn | grep 8000
```

## Если видите несколько процессов WebConvert

Остановите все:

```bash
# Остановите systemd сервис
sudo systemctl stop WebConvert

# Убейте все процессы WebConvert
pkill -f "WebConvert.*bot.py"
pkill -f "/root/WebConvert"

# Проверьте, что процессов нет
ps aux | grep WebConvert | grep -v grep

# Запустите только через systemd
sudo systemctl start WebConvert
```

## Проверка webapp

```bash
# Статус
sudo systemctl status webapp

# Если не запущен
sudo systemctl start webapp

# Проверка порта
sudo netstat -tulpn | grep 8000
```
