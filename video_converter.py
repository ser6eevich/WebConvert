import os
import asyncio
import ffmpeg
import logging
import subprocess
import shutil
import time
import re
import threading
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

# Настройки скорости конвертации
# FFMPEG_PRESET: ultrafast, veryfast, faster, fast, medium, slow, slower, veryslow
# Чем быстрее preset, тем быстрее конвертация, но больше размер файла
FFMPEG_PRESET = os.getenv('FFMPEG_PRESET', 'veryfast')  # По умолчанию veryfast (баланс скорости и качества)

# Hardware acceleration (аппаратное ускорение)
# FFMPEG_HWACCEL: auto, nvenc, vaapi, videotoolbox, none
# auto - автоматически определяет доступное ускорение
FFMPEG_HWACCEL = os.getenv('FFMPEG_HWACCEL', 'auto').lower()

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


def _detect_hardware_acceleration(ffmpeg_path: str) -> dict:
    """
    Определяет доступное аппаратное ускорение для FFmpeg
    
    Returns:
        dict: {
            'type': 'nvenc' | 'vaapi' | 'videotoolbox' | None,
            'encoder': 'h264_nvenc' | 'h264_vaapi' | 'h264_videotoolbox' | None,
            'available': bool
        }
    """
    result = {
        'type': None,
        'encoder': None,
        'available': False
    }
    
    try:
        # Проверяем доступные кодеки
        check_cmd = [ffmpeg_path, '-hide_banner', '-encoders']
        process = subprocess.run(
            check_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        encoders_output = process.stdout + process.stderr
        logger.debug(f"Доступные кодеки (первые 500 символов): {encoders_output[:500]}")
        
        # NVIDIA NVENC (для GPU NVIDIA)
        if 'h264_nvenc' in encoders_output or 'hevc_nvenc' in encoders_output:
            # Проверяем реальную доступность NVENC - пытаемся запустить тестовую команду
            # Это нужно, потому что энкодер может быть в списке, но драйверы/библиотеки могут отсутствовать
            try:
                test_cmd = [
                    ffmpeg_path, '-hide_banner', '-f', 'lavfi', '-i', 'testsrc=duration=0.1:size=320x240:rate=1',
                    '-c:v', 'h264_nvenc', '-preset', 'fast', '-frames:v', '1',
                    '-f', 'null', '-'
                ]
                test_process = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                # Если команда выполнилась успешно или ошибка не связана с загрузкой библиотеки
                if test_process.returncode == 0 or 'Cannot load libnvidia-encode.so' not in test_process.stderr:
                    result['type'] = 'nvenc'
                    result['encoder'] = 'h264_nvenc'
                    result['available'] = True
                    logger.info("✅ Обнаружено аппаратное ускорение: NVIDIA NVENC (проверено реальным тестом)")
                    return result
                else:
                    logger.warning("⚠️ NVENC найден в списке энкодеров, но libnvidia-encode.so недоступна (нет драйверов/GPU)")
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
                logger.warning(f"⚠️ Не удалось проверить реальную доступность NVENC: {e}")
                # Не помечаем как доступный, если тест не прошел
        
        # Intel/AMD VAAPI (для Linux с Intel/AMD GPU)
        if 'h264_vaapi' in encoders_output:
            result['type'] = 'vaapi'
            result['encoder'] = 'h264_vaapi'
            result['available'] = True
            logger.info("✅ Обнаружено аппаратное ускорение: VAAPI")
            return result
        
        # Apple VideoToolbox (для macOS)
        if 'h264_videotoolbox' in encoders_output:
            result['type'] = 'videotoolbox'
            result['encoder'] = 'h264_videotoolbox'
            result['available'] = True
            logger.info("✅ Обнаружено аппаратное ускорение: VideoToolbox")
            return result
        
        logger.info("ℹ️ Аппаратное ускорение не обнаружено, используется программное кодирование")
        
    except Exception as e:
        logger.warning(f"⚠️ Не удалось проверить аппаратное ускорение: {e}")
    
    return result


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


def _convert_video_sync(input_path: str, output_path: str, target_width: int = 1920, target_height: int = 1080,
                        ffmpeg_path: str = None, ffprobe_path: str = None, force_cpu: bool = False):
    """
    Синхронная функция конвертации видео через FFmpeg
    
    Args:
        input_path: Путь к исходному видео
        output_path: Путь для сохранения результата
        target_width: Целевая ширина (по умолчанию 1920)
        target_height: Целевая высота (по умолчанию 1080)
        ffmpeg_path: Путь к ffmpeg (если None, определяется автоматически)
        ffprobe_path: Путь к ffprobe (если None, определяется автоматически)
        force_cpu: Принудительно использовать CPU (libx264) вместо аппаратного ускорения
    """
    try:
        # Получаем пути к ffmpeg и ffprobe (если не переданы)
        if ffmpeg_path is None or ffprobe_path is None:
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
        
        # Получаем длительность видео для расчета прогресса
        duration = float(probe.get('format', {}).get('duration', 0))
        if not duration:
            # Пытаемся получить из видеопотока
            duration = float(video_info.get('duration', 0))
        if not duration:
            logger.warning("Не удалось определить длительность видео, прогресс будет приблизительным")
            duration = 0
        
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
        input_stream = ffmpeg.input(input_path)
        
        # Получаем видео и аудио потоки отдельно
        video_stream = input_stream['v']  # Явно указываем видео поток
        audio_stream = input_stream['a']  # Аудио поток (если есть)
        
        # Масштабируем и добавляем черные полосы (letterbox/pillarbox) если нужно
        if new_width != target_width or new_height != target_height:
            # Сначала масштабируем видео
            video_stream = ffmpeg.filter(video_stream, 'scale', new_width, new_height)
            # Затем добавляем паддинг для достижения точного размера 1920x1080
            video_stream = ffmpeg.filter(
                video_stream,
                'pad',
                target_width,
                target_height,
                x_offset,
                y_offset,
                color='black'
            )
        else:
            # Просто масштабируем видео до нужного размера
            video_stream = ffmpeg.filter(video_stream, 'scale', target_width, target_height)
        
        # Определяем аппаратное ускорение (если включено)
        hw_accel = None
        video_codec = 'libx264'
        hw_output_options = {}
        
        logger.info(f"🔍 Настройки ускорения: FFMPEG_HWACCEL={FFMPEG_HWACCEL}, FFMPEG_PRESET={FFMPEG_PRESET}, force_cpu={force_cpu}")
        
        # Если force_cpu=True, принудительно используем CPU
        if force_cpu:
            video_codec = 'libx264'
            logger.info("ℹ️ Принудительно используется программное кодирование (libx264)")
        elif FFMPEG_HWACCEL != 'none':
            hw_accel = _detect_hardware_acceleration(ffmpeg_path)
            logger.info(f"🔍 Результат проверки ускорения: {hw_accel}")
            
            if FFMPEG_HWACCEL == 'auto' and hw_accel['available']:
                video_codec = hw_accel['encoder']
                logger.info(f"🚀 Используется аппаратное ускорение: {hw_accel['type']} (encoder: {hw_accel['encoder']})")
            elif FFMPEG_HWACCEL == 'nvenc':
                if hw_accel['type'] == 'nvenc':
                    video_codec = 'h264_nvenc'
                    logger.info("🚀 Используется NVIDIA NVENC")
                else:
                    logger.warning(f"⚠️ NVENC запрошен, но не найден. Доступно: {hw_accel}")
            elif FFMPEG_HWACCEL == 'vaapi' and hw_accel['type'] == 'vaapi':
                video_codec = 'h264_vaapi'
                logger.info("🚀 Используется VAAPI")
            elif FFMPEG_HWACCEL == 'videotoolbox' and hw_accel['type'] == 'videotoolbox':
                video_codec = 'h264_videotoolbox'
                logger.info("🚀 Используется VideoToolbox")
            else:
                logger.info(f"ℹ️ Аппаратное ускорение '{FFMPEG_HWACCEL}' недоступно, используется программное кодирование")
        else:
            logger.info("ℹ️ Аппаратное ускорение отключено (FFMPEG_HWACCEL=none), используется программное кодирование")
        
        # Настройки для аппаратного ускорения
        if video_codec == 'h264_nvenc':
            # NVIDIA NVENC настройки
            # Важно: для NVENC некоторые параметры передаются через дополнительные опции
            hw_output_options = {
                'preset': 'fast',  # fast, medium, slow для NVENC
                'rc': 'vbr',  # Variable bitrate
                'cq': '23',  # Constant quality (18-28, меньше = лучше качество)
                'b:v': '5000k',  # Максимальный битрейт
                'maxrate': '6000k',
                'bufsize': '10000k',
            }
        elif video_codec == 'h264_vaapi':
            # VAAPI настройки
            hw_output_options = {
                'qp': '23',  # Quality parameter (0-51, меньше = лучше)
            }
        elif video_codec == 'h264_videotoolbox':
            # VideoToolbox настройки
            hw_output_options = {
                'allow_sw': '1',
                'realtime': '1',
                'b:v': '5000k',
            }
        else:
            # Программное кодирование (libx264) - используем настройки из переменных окружения
            hw_output_options = {
                'preset': FFMPEG_PRESET,  # Настраиваемый preset для скорости
                'tune': 'fastdecode',  # Оптимизация для быстрого декодирования
            }
        
        # Настраиваем выходной поток
        # Для больших файлов используем более быстрый preset и оптимизированные настройки
        # Используем c:a вместо acodec, чтобы избежать проблем с библиотекой ffmpeg-python
        output_kwargs = {
            'c:a': 'aac',  # Используем c:a вместо acodec для совместимости
            'b:a': '192k',  # Используем b:a вместо audio_bitrate
            'movflags': 'faststart',  # Для быстрого воспроизведения в браузере
        }
        
        # Для NVENC pix_fmt должен быть установлен отдельно или не указан (NVENC сам выберет)
        if video_codec != 'h264_nvenc':
            output_kwargs['pix_fmt'] = 'yuv420p'  # Совместимость с большинством устройств
        
        # Добавляем видеокодек - используем c:v вместо vcodec для совместимости
        output_kwargs['c:v'] = video_codec
        
        # Добавляем битрейт (если не указан в hw_output_options)
        if 'b:v' not in hw_output_options and video_codec == 'libx264':
            output_kwargs['b:v'] = '5000k'
        
        # Добавляем настройки для программного кодирования
        if video_codec == 'libx264':
            output_kwargs['threads'] = 0  # Использовать все доступные ядра процессора
            output_kwargs.update(hw_output_options)
        else:
            # Для аппаратного ускорения добавляем специфичные опции
            output_kwargs.update(hw_output_options)
        
        # Логируем используемые настройки перед компиляцией
        logger.info(f"⚙️ Настройки конвертации: codec={video_codec}, preset={FFMPEG_PRESET if video_codec == 'libx264' else hw_output_options.get('preset', 'N/A')}")
        
        # Создаем выходной поток с явным маппингом видео и аудио
        # Используем video_stream для видео и audio_stream для аудио (если есть)
        try:
            # Пытаемся включить аудио, если оно есть
            stream = ffmpeg.output(video_stream, audio_stream, output_path, **output_kwargs)
        except:
            # Если аудио нет, используем только видео
            stream = ffmpeg.output(video_stream, output_path, **output_kwargs)
        
        # Запускаем конвертацию с отслеживанием прогресса
        # Используем subprocess для чтения stderr в реальном времени
        
        # Получаем команду FFmpeg из потока
        try:
            cmd = ffmpeg.compile(stream, overwrite_output=True)
            # Логируем команду для отладки (первые 300 символов)
            cmd_str = ' '.join(cmd)
            logger.info(f"🔧 Команда FFmpeg (первые 300 символов): {cmd_str[:300]}...")
        except Exception as compile_error:
            logger.error(f"❌ Ошибка при компиляции команды FFmpeg: {compile_error}")
            logger.error(f"❌ Параметры output_kwargs: {output_kwargs}")
            raise RuntimeError(f"Ошибка при формировании команды FFmpeg: {compile_error}")
        
        # Логируем начало конвертации
        if duration > 0:
            logger.info(f"🎬 Начало конвертации. Длительность видео: {int(duration // 60)}м {int(duration % 60)}с")
        else:
            logger.info("🎬 Начало конвертации. Длительность видео неизвестна, прогресс будет приблизительным")
        
        # Запускаем процесс
        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Функция для парсинга прогресса из stderr
        def parse_progress(line):
            """Парсит строку прогресса FFmpeg и возвращает текущее время"""
            # Формат: frame=  123 fps= 25 q=28.0 size=    1024kB time=00:00:05.00 bitrate=1677.7kbits/s speed=1.0x
            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if time_match:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2))
                seconds = float(time_match.group(3))
                current_time = hours * 3600 + minutes * 60 + seconds
                return current_time
            return None
        
        # Читаем stderr в отдельном потоке
        last_log_time = 0
        log_interval = 5  # Логируем каждые 5 секунд
        stderr_lines = []
        error_occurred = False
        
        def read_stderr():
            nonlocal last_log_time, error_occurred
            try:
                for line in iter(process.stderr.readline, ''):
                    if not line:
                        break
                    stderr_lines.append(line)
                    
                    # Проверяем на ошибки
                    if 'error' in line.lower() or 'failed' in line.lower():
                        error_occurred = True
                    
                    # Парсим прогресс
                    if 'time=' in line:
                        current_time = parse_progress(line)
                        if current_time and duration > 0:
                            # Вычисляем процент
                            percent = min(100, (current_time / duration) * 100)
                            elapsed_time = current_time
                            remaining_time = max(0, duration - current_time)
                            
                            # Логируем каждые N секунд или при значительном изменении процента
                            now = time.time()
                            if now - last_log_time >= log_interval or percent >= 99.9:
                                # Форматируем время
                                elapsed_min = int(elapsed_time // 60)
                                elapsed_sec = int(elapsed_time % 60)
                                elapsed_str = f"{elapsed_min}м {elapsed_sec}с"
                                
                                remaining_min = int(remaining_time // 60)
                                remaining_sec = int(remaining_time % 60)
                                remaining_str = f"{remaining_min}м {remaining_sec}с" if remaining_time > 1 else "менее минуты"
                                
                                logger.info(
                                    f"🔄 Прогресс конвертации: {percent:.1f}% | "
                                    f"Прошло: {elapsed_str} | "
                                    f"Осталось: ~{remaining_str}"
                                )
                                last_log_time = now
            except Exception as e:
                logger.error(f"Ошибка при чтении stderr: {e}")
        
        # Запускаем чтение stderr в отдельном потоке
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        # Ждем завершения процесса
        process.wait()
        
        # Ждем завершения потока чтения stderr
        stderr_thread.join(timeout=1)
        
        # Проверяем код возврата
        if process.returncode != 0:
            # Берем весь stderr для логирования
            stderr_output = ''.join(stderr_lines)
            logger.error(f"FFmpeg завершился с ошибкой (код {process.returncode})")
            logger.error(f"Полный stderr FFmpeg:\n{stderr_output}")
            
            # Проверяем, является ли это ошибкой NVENC (нет драйверов/библиотек)
            nvenc_error_indicators = [
                'Cannot load libnvidia-encode.so',
                'Error while opening encoder',
                'The minimum required Nvidia driver',
                'libnvidia-encode'
            ]
            
            is_nvenc_error = any(indicator in stderr_output for indicator in nvenc_error_indicators)
            
            # Если это ошибка NVENC и мы пытались использовать NVENC, переключаемся на libx264
            if is_nvenc_error and video_codec == 'h264_nvenc':
                logger.warning("⚠️ NVENC недоступен (нет драйверов/GPU), автоматически переключаюсь на libx264 (CPU)")
                # Рекурсивно вызываем конвертацию с libx264
                return _convert_video_sync(
                    input_path, output_path, target_width, target_height,
                    ffmpeg_path, ffprobe_path, force_cpu=True
                )
            
            # Для исключения берем хвост (последние 4000 символов), где обычно находится реальная ошибка
            MAX_LEN = 4000
            if len(stderr_output) > MAX_LEN:
                trimmed = stderr_output[-MAX_LEN:]  # Берем хвост
            else:
                trimmed = stderr_output
            
            raise RuntimeError(f"FFmpeg ошибка:\n{trimmed}")
        
        if error_occurred:
            logger.warning("В процессе конвертации были обнаружены предупреждения")
        
        logger.info(f"✅ Конвертация завершена: {input_path} -> {output_path}")
        
    except ffmpeg.Error as e:
        stderr_output = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        logger.error(f"FFmpeg ошибка (полный stderr):\n{stderr_output}")
        
        # Для исключения берем хвост (последние 4000 символов), где обычно находится реальная ошибка
        MAX_LEN = 4000
        if len(stderr_output) > MAX_LEN:
            trimmed = stderr_output[-MAX_LEN:]  # Берем хвост
        else:
            trimmed = stderr_output
        
        # Более подробная информация об ошибке
        if 'codec' in stderr_output.lower():
            raise ValueError(f"Неподдерживаемый кодек видео. Попробуйте другой формат.\n{trimmed}")
        elif 'invalid' in stderr_output.lower() or 'no such file' in stderr_output.lower():
            raise ValueError(f"Файл поврежден или не найден.\n{trimmed}")
        elif 'permission' in stderr_output.lower():
            raise PermissionError(f"Нет прав на запись в выходную директорию.\n{trimmed}")
        else:
            raise RuntimeError(f"Ошибка FFmpeg:\n{trimmed}")
    except Exception as e:
        logger.error(f"Ошибка при синхронной конвертации: {e}", exc_info=True)
        raise

