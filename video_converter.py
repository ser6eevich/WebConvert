import os
import asyncio
import ffmpeg
import logging
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Проверяем, указан ли путь к FFmpeg вручную
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')  # По умолчанию ищем в PATH


async def convert_video_to_mp4(input_path: str, file_id: str) -> str:
    """
    Конвертирует видео в MP4 с разрешением 1920x1080
    
    Args:
        input_path: Путь к исходному видео файлу
        file_id: ID файла для создания уникального имени выходного файла
    
    Returns:
        Путь к сконвертированному файлу или None в случае ошибки
    """
    try:
        output_path = f"converted/{file_id}_converted.mp4"
        
        # Проверяем существование входного файла
        if not os.path.exists(input_path):
            logger.error(f"Входной файл не найден: {input_path}")
            return None
        
        # Запускаем конвертацию в отдельном потоке
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _convert_video_sync,
            input_path,
            output_path
        )
        
        if os.path.exists(output_path):
            logger.info(f"Видео успешно сконвертировано: {output_path}")
            return output_path
        else:
            logger.error("Файл не был создан после конвертации")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при конвертации видео: {e}")
        return None


def _convert_video_sync(input_path: str, output_path: str):
    """
    Синхронная функция конвертации видео через FFmpeg
    
    Args:
        input_path: Путь к исходному видео
        output_path: Путь для сохранения результата
    """
    try:
        # Если указан кастомный путь к FFmpeg, устанавливаем его
        if FFMPEG_PATH != 'ffmpeg' and os.path.exists(FFMPEG_PATH):
            # Устанавливаем путь к FFmpeg для библиотеки ffmpeg-python
            import ffmpeg
            ffmpeg_path = os.path.dirname(FFMPEG_PATH)
            os.environ['PATH'] = ffmpeg_path + os.pathsep + os.environ.get('PATH', '')
            logger.info(f"Используется FFmpeg из: {FFMPEG_PATH}")
        
        # Загружаем видео
        probe = ffmpeg.probe(input_path)
        video_streams = [s for s in probe['streams'] if s['codec_type'] == 'video']
        
        if not video_streams:
            raise ValueError("В файле не найден видеопоток")
        
        video_info = video_streams[0]
        
        # Проверяем кодек и формат для WEBM файлов
        codec_name = video_info.get('codec_name', '').lower()
        format_name = probe.get('format', {}).get('format_name', '').lower()
        
        # Логируем информацию о формате для отладки
        logger.info(f"Формат файла: {format_name}, Кодек видео: {codec_name}")
        
        # Для WEBM файлов (VP8, VP9) FFmpeg обрабатывает их автоматически
        # Но можно добавить специальную обработку, если нужно
        if 'webm' in format_name or codec_name in ['vp8', 'vp9']:
            logger.info(f"Обнаружен WEBM файл с кодеком {codec_name}. FFmpeg автоматически декодирует VP8/VP9.")
        
        # Получаем исходные размеры
        width = int(video_info.get('width', 1920))
        height = int(video_info.get('height', 1080))
        
        # Вычисляем масштабирование с сохранением пропорций
        # Целевой размер: 1920x1080
        target_width = 1920
        target_height = 1080
        
        # Вычисляем соотношение сторон
        input_aspect = width / height
        target_aspect = target_width / target_height
        
        if input_aspect > target_aspect:
            # Видео шире - подгоняем по ширине
            new_width = target_width
            new_height = int(target_width / input_aspect)
            # Центрируем по вертикали
            y_offset = (target_height - new_height) // 2
            x_offset = 0
        else:
            # Видео выше - подгоняем по высоте
            new_height = target_height
            new_width = int(target_height * input_aspect)
            # Центрируем по горизонтали
            x_offset = (target_width - new_width) // 2
            y_offset = 0
        
        # Создаем пайплайн FFmpeg
        # Для WEBM файлов (VP8, VP9) FFmpeg автоматически декодирует их
        # FFmpeg поддерживает WEBM из коробки, никаких дополнительных настроек не требуется
        stream = ffmpeg.input(input_path)
        
        # Масштабируем и добавляем черные полосы (letterbox/pillarbox) если нужно
        if new_width != target_width or new_height != target_height:
            # Сначала масштабируем
            stream = ffmpeg.filter(stream, 'scale', new_width, new_height)
            # Затем добавляем паддинг для достижения точного размера 1920x1080
            stream = ffmpeg.filter(
                stream,
                'pad',
                target_width,
                target_height,
                x_offset,
                y_offset,
                color='black'
            )
        else:
            # Просто масштабируем до нужного размера
            stream = ffmpeg.filter(stream, 'scale', target_width, target_height)
        
        # Настраиваем выходной поток
        # Для больших файлов используем более быстрый preset и оптимизированные настройки
        stream = ffmpeg.output(
            stream,
            output_path,
            vcodec='libx264',
            acodec='aac',
            video_bitrate='5000k',
            audio_bitrate='192k',
            preset='fast',  # Изменено с 'medium' на 'fast' для ускорения конвертации больших файлов
            movflags='faststart',  # Для быстрого воспроизведения в браузере
            pix_fmt='yuv420p',  # Совместимость с большинством устройств
            threads=0  # Использовать все доступные ядра процессора для ускорения
        )
        
        # Запускаем конвертацию
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        logger.info(f"Конвертация завершена: {input_path} -> {output_path}")
        
    except ffmpeg.Error as e:
        stderr_output = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        logger.error(f"FFmpeg ошибка: {stderr_output}")
        
        # Более подробная информация об ошибке
        if 'codec' in stderr_output.lower():
            raise ValueError("Неподдерживаемый кодек видео. Попробуйте другой формат.")
        elif 'invalid' in stderr_output.lower() or 'no such file' in stderr_output.lower():
            raise ValueError("Файл поврежден или не найден.")
        elif 'permission' in stderr_output.lower():
            raise PermissionError("Нет прав на запись в выходную директорию.")
        else:
            raise RuntimeError(f"Ошибка FFmpeg: {stderr_output[:200]}")
    except Exception as e:
        logger.error(f"Ошибка при синхронной конвертации: {e}", exc_info=True)
        raise

