import os
import asyncio
import ffmpeg
import logging
import subprocess
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Проверяем, указан ли путь к FFmpeg вручную
# Если FFMPEG_PATH не указан в .env, используем 'ffmpeg' из системного PATH
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')  # По умолчанию ищем в PATH

# Если указан путь, нормализуем его
if FFMPEG_PATH != 'ffmpeg':
    FFMPEG_PATH = os.path.expanduser(FFMPEG_PATH)

# Определяем пути к ffmpeg и ffprobe
def _get_ffmpeg_paths():
    """
    Определяет пути к ffmpeg и ffprobe
    
    Returns:
        tuple: (ffmpeg_path, ffprobe_path)
    """
    ffmpeg_path = None
    ffprobe_path = None
    
    # Если указан кастомный путь
    if FFMPEG_PATH != 'ffmpeg' and os.path.exists(FFMPEG_PATH):
        ffmpeg_path = FFMPEG_PATH
        # Ищем ffprobe в той же директории
        ffmpeg_dir = os.path.dirname(FFMPEG_PATH)
        if FFMPEG_PATH.endswith('.exe'):
            ffprobe_path = os.path.join(ffmpeg_dir, 'ffprobe.exe')
        else:
            ffprobe_path = os.path.join(ffmpeg_dir, 'ffprobe')
        
        # Если ffprobe не найден в той же директории, ищем в PATH
        if not os.path.exists(ffprobe_path):
            ffprobe_path = shutil.which('ffprobe') or 'ffprobe'
    else:
        # Ищем в системном PATH
        ffmpeg_path = shutil.which('ffmpeg') or 'ffmpeg'
        ffprobe_path = shutil.which('ffprobe') or 'ffprobe'
    
    return ffmpeg_path, ffprobe_path


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
        # Получаем пути к ffmpeg и ffprobe
        ffmpeg_path, ffprobe_path = _get_ffmpeg_paths()
        
        # Настраиваем пути для библиотеки ffmpeg-python
        if FFMPEG_PATH != 'ffmpeg' and os.path.exists(FFMPEG_PATH):
            # Если указан кастомный путь, добавляем директорию в PATH
            ffmpeg_dir = os.path.dirname(FFMPEG_PATH)
            if ffmpeg_dir:
                os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
            logger.info(f"Используется FFmpeg из: {ffmpeg_path}, ffprobe из: {ffprobe_path}")
        else:
            # Используем FFmpeg из системного PATH
            logger.info(f"Используется FFmpeg из системного PATH: {ffmpeg_path}, ffprobe: {ffprobe_path}")
        
        # Настраиваем ffmpeg-python для использования правильных путей
        # Библиотека ffmpeg-python использует переменные окружения или ищет в PATH
        # Убеждаемся, что ffprobe доступен
        if ffprobe_path and ffprobe_path != 'ffprobe':
            # Если путь к ffprobe указан явно, добавляем его директорию в PATH
            ffprobe_dir = os.path.dirname(ffprobe_path)
            if ffprobe_dir:
                os.environ['PATH'] = ffprobe_dir + os.pathsep + os.environ.get('PATH', '')
        
        # Проверяем доступность ffprobe
        try:
            result = subprocess.run(
                [ffprobe_path, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.warning(f"ffprobe найден, но не работает: {ffprobe_path}")
                raise RuntimeError(f"ffprobe не работает. Проверьте установку FFmpeg.")
        except FileNotFoundError:
            logger.error(f"ffprobe не найден по пути: {ffprobe_path}")
            raise RuntimeError(f"ffprobe не найден. Установите FFmpeg: sudo apt install ffmpeg")
        
        # Настраиваем библиотеку ffmpeg-python для использования правильного пути к ffprobe
        # Библиотека ищет ffprobe в PATH, поэтому мы уже добавили директорию в PATH выше
        # Но можно также явно указать путь через переменную окружения
        if ffprobe_path and ffprobe_path != 'ffprobe':
            # Если путь к ffprobe указан явно, убеждаемся, что он в PATH
            ffprobe_dir = os.path.dirname(ffprobe_path)
            if ffprobe_dir and ffprobe_dir not in os.environ.get('PATH', '').split(os.pathsep):
                os.environ['PATH'] = ffprobe_dir + os.pathsep + os.environ.get('PATH', '')
                logger.info(f"Добавлена директория ffprobe в PATH: {ffprobe_dir}")
        
        # Загружаем видео через ffmpeg.probe
        # Библиотека ffmpeg-python будет использовать ffprobe из PATH
        # Если ffprobe все еще не найден, попробуем использовать явный путь
        try:
            probe = ffmpeg.probe(input_path)
        except FileNotFoundError as e:
            # Если ffprobe не найден, попробуем использовать явный путь
            if 'ffprobe' in str(e).lower():
                logger.error(f"ffprobe не найден библиотекой ffmpeg-python. Путь: {ffprobe_path}")
                logger.error(f"PATH: {os.environ.get('PATH', '')[:200]}")
                raise RuntimeError(
                    f"ffprobe не найден. Проверьте установку:\n"
                    f"  which ffprobe\n"
                    f"  sudo apt install ffmpeg"
                )
            raise
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

