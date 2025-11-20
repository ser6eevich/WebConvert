"""
Скрипт для автоматической очистки временных файлов
Запускайте через cron или планировщик задач
"""
import os
import time
from pathlib import Path

# Директории для очистки
DOWNLOAD_DIR = Path("downloads")
CONVERTED_DIR = Path("converted")

# Время жизни файлов в секундах (24 часа)
MAX_AGE = 24 * 60 * 60


def cleanup_old_files():
    """Удаляет файлы старше MAX_AGE"""
    current_time = time.time()
    deleted_count = 0
    total_size = 0
    
    for directory in [DOWNLOAD_DIR, CONVERTED_DIR]:
        if not directory.exists():
            continue
        
        for file_path in directory.iterdir():
            if file_path.is_file():
                try:
                    file_age = current_time - file_path.stat().st_mtime
                    file_size = file_path.stat().st_size
                    
                    if file_age > MAX_AGE:
                        file_path.unlink()
                        deleted_count += 1
                        total_size += file_size
                        print(f"Удален: {file_path} (возраст: {file_age / 3600:.1f} часов, размер: {file_size / 1024 / 1024:.1f}MB)")
                except Exception as e:
                    print(f"Ошибка при удалении {file_path}: {e}")
    
    if deleted_count > 0:
        print(f"\nОчистка завершена:")
        print(f"  Удалено файлов: {deleted_count}")
        print(f"  Освобождено места: {total_size / 1024 / 1024:.1f}MB")
    else:
        print("Нет файлов для удаления")


if __name__ == "__main__":
    cleanup_old_files()

