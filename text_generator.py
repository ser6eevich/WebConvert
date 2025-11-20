import os
import logging
import asyncio
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Инициализируем клиент OpenAI с заголовком для Assistants API v2
client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    default_headers={"OpenAI-Beta": "assistants=v2"}
)
GPT_ASSISTANT_ID = os.getenv('GPT_ASSISTANT_ID')
GPT_ASSISTANT_ID_VIDEOS = os.getenv('GPT_ASSISTANT_ID_VIDEOS')

if not GPT_ASSISTANT_ID:
    logger.warning("GPT_ASSISTANT_ID не установлен в .env файле")
if not GPT_ASSISTANT_ID_VIDEOS:
    logger.warning("GPT_ASSISTANT_ID_VIDEOS не установлен в .env файле")


def _generate_content_with_assistant_sync(input_text: str, assistant_id: str = None) -> dict:
    """
    Синхронная функция генерации контента через GPT ассистента
    
    Args:
        input_text: Исходная транскрибация
    
    Returns:
        Словарь с 4 частями: название вебинара, описание, тайм-код, пост
        или None в случае ошибки
    """
    try:
        # Используем переданный assistant_id или дефолтный
        if not assistant_id:
            assistant_id = GPT_ASSISTANT_ID
        
        if not assistant_id:
            raise ValueError("GPT_ASSISTANT_ID не установлен в .env файле")
        
        # Создаем тред (thread) для ассистента
        # Заголовок v2 уже установлен в default_headers клиента
        thread = client.beta.threads.create()
        
        # Отправляем транскрибацию ассистенту
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=input_text
        )
        
        # Запускаем ассистента
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )
        
        # Ждем завершения работы ассистента
        while run.status in ['queued', 'in_progress', 'cancelling']:
            import time
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
        
        if run.status != 'completed':
            logger.error(f"Ассистент завершился со статусом: {run.status}")
            if hasattr(run, 'last_error'):
                logger.error(f"Ошибка ассистента: {run.last_error}")
            return None
        
        # Получаем ответ ассистента
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        
        # Берем последнее сообщение от ассистента
        assistant_message = None
        for message in messages.data:
            if message.role == 'assistant':
                assistant_message = message
                break
        
        if not assistant_message:
            logger.error("Не получен ответ от ассистента")
            return None
        
        # Извлекаем текст ответа
        response_text = ""
        for content in assistant_message.content:
            if content.type == 'text':
                response_text = content.text.value
                break
        
        if not response_text:
            logger.error("Ответ ассистента пуст")
            return None
        
        # Разбиваем ответ на 4 части
        parts = _parse_assistant_response(response_text)
        
        return parts
        
    except Exception as e:
        logger.error(f"Ошибка при работе с GPT ассистентом: {e}")
        return None


def _parse_assistant_response(response_text: str) -> dict:
    """
    Разбивает ответ ассистента на 4 части:
    1. Название вебинара
    2. Описание
    3. Тайм-код
    4. Пост для телеграм
    
    Args:
        response_text: Полный ответ от ассистента
    
    Returns:
        Словарь с ключами: webinar_name, description, timestamps, post
    """
    # Ищем разделы по ключевым словам
    # Поддерживаем разные форматы: "Заголовок:", "1. Заголовок", "## Заголовок" и т.д.
    
    parts = {
        'webinar_name': '',
        'description': '',
        'timestamps': '',
        'post': ''
    }
    
    # Паттерны для поиска разделов
    patterns = {
        'webinar_name': [
            r'(?:^|\n)(?:1\.|#+\s*)?(?:Название вебинара|НАЗВАНИЕ ВЕБИНАРА|Название|Заголовок|ЗАГОЛОВОК|Title|TITLE|Webinar Name)[:：]\s*\n?(.+?)(?=\n(?:2\.|#+\s*)?(?:Описание|ОПИСАНИЕ|Description|DESCRIPTION)|$)',
            r'(?:^|\n)(?:1\.|#+\s*)?(?:Название вебинара|НАЗВАНИЕ ВЕБИНАРА|Название|Заголовок|ЗАГОЛОВОК|Title|TITLE|Webinar Name)[:：]\s*(.+?)(?=\n\n|\n(?:2\.|#+\s*)?(?:Описание|ОПИСАНИЕ|Description|DESCRIPTION)|$)',
        ],
        'description': [
            r'(?:^|\n)(?:2\.|#+\s*)?(?:Описание|ОПИСАНИЕ|Description|DESCRIPTION)[:：]\s*\n?(.+?)(?=\n(?:3\.|#+\s*)?(?:Тайм-код|ТАЙМ-КОД|Timestamps|TIMESTAMPS)|$)',
            r'(?:^|\n)(?:2\.|#+\s*)?(?:Описание|ОПИСАНИЕ|Description|DESCRIPTION)[:：]\s*(.+?)(?=\n\n|\n(?:3\.|#+\s*)?(?:Тайм-код|ТАЙМ-КОД|Timestamps|TIMESTAMPS)|$)',
        ],
        'timestamps': [
            r'(?:^|\n)(?:3\.|#+\s*)?(?:Тайм-код|ТАЙМ-КОД|Timestamps|TIMESTAMPS|Таймкоды)[:：]\s*\n?(.+?)(?=\n(?:4\.|#+\s*)?(?:Пост|ПОСТ|Post|POST|Телеграм|TELEGRAM)|$)',
            r'(?:^|\n)(?:3\.|#+\s*)?(?:Тайм-код|ТАЙМ-КОД|Timestamps|TIMESTAMPS|Таймкоды)[:：]\s*(.+?)(?=\n\n|\n(?:4\.|#+\s*)?(?:Пост|ПОСТ|Post|POST|Телеграм|TELEGRAM)|$)',
        ],
        'post': [
            r'(?:^|\n)(?:4\.|#+\s*)?(?:Пост|ПОСТ|Post|POST|Телеграм|TELEGRAM|Пост для телеграм)[:：]\s*\n?(.+?)$',
            r'(?:^|\n)(?:4\.|#+\s*)?(?:Пост|ПОСТ|Post|POST|Телеграм|TELEGRAM|Пост для телеграм)[:：]\s*(.+?)$',
        ]
    }
    
    # Пробуем найти каждый раздел
    for part_name, part_patterns in patterns.items():
        for pattern in part_patterns:
            match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
            if match:
                parts[part_name] = match.group(1).strip()
                break
    
    # Если не нашли по паттернам, пробуем разбить по номерам или маркерам
    if not any(parts.values()):
        # Пробуем разбить по строкам с номерами
        lines = response_text.split('\n')
        current_section = None
        current_text = []
        
        for line in lines:
            line_stripped = line.strip()
            # Проверяем, является ли строка заголовком раздела
            if re.match(r'^[1-4]\.', line_stripped) or re.match(r'^#+\s', line_stripped):
                # Сохраняем предыдущий раздел
                if current_section and current_text:
                    parts[current_section] = '\n'.join(current_text).strip()
                current_text = []
                # Определяем раздел
                if 'название вебинара' in line_stripped.lower() or 'название' in line_stripped.lower() or ('заголовок' in line_stripped.lower() and 'вебинара' not in line_stripped.lower()) or 'title' in line_stripped.lower() or 'webinar name' in line_stripped.lower():
                    current_section = 'webinar_name'
                elif 'описание' in line_stripped.lower() or 'description' in line_stripped.lower():
                    current_section = 'description'
                elif 'тайм' in line_stripped.lower() or 'timestamp' in line_stripped.lower():
                    current_section = 'timestamps'
                elif 'пост' in line_stripped.lower() or 'telegram' in line_stripped.lower():
                    current_section = 'post'
            elif current_section:
                current_text.append(line)
        
        # Сохраняем последний раздел
        if current_section and current_text:
            parts[current_section] = '\n'.join(current_text).strip()
    
    # Если все еще ничего не нашли, разбиваем текст на равные части
    if not any(parts.values()):
        text_parts = response_text.split('\n\n')
        if len(text_parts) >= 4:
            parts['webinar_name'] = text_parts[0].strip()
            parts['description'] = text_parts[1].strip()
            parts['timestamps'] = text_parts[2].strip()
            parts['post'] = '\n\n'.join(text_parts[3:]).strip()
        elif len(text_parts) >= 1:
            # Если не удалось разбить, все идет в пост
            parts['post'] = response_text.strip()
    
    # Применяем форматирование жирным текстом ко всем частям
    # Это работает для обоих ассистентов (вебинары и ролики)
    for key in parts:
        if parts[key]:
            parts[key] = _format_bold_text(parts[key])
            logger.debug(f"Применено форматирование для части '{key}': {len(parts[key])} символов")
    
    return parts


def _format_bold_text(text: str) -> str:
    """
    Выделяет основные моменты жирным текстом (Telegram Markdown формат)
    В Telegram для жирного используется одна звездочка: *текст*
    
    Args:
        text: Исходный текст
    
    Returns:
        Текст с выделенными жирным ключевыми словами и фразами
    """
    if not text:
        return text
    
    formatted_text = text
    
    # Сначала конвертируем двойные звездочки в одинарные (если GPT уже отформатировал)
    # Это нужно, так как в Telegram используется одна звездочка для жирного
    # Делаем это несколько раз, чтобы обработать все вложенные случаи
    while '**' in formatted_text:
        formatted_text = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', formatted_text)
    
    # Также обрабатываем случаи, когда GPT использует другие форматы форматирования
    # Конвертируем HTML теги <b> в Markdown формат
    formatted_text = re.sub(r'<b>([^<]+)</b>', r'*\1*', formatted_text, flags=re.IGNORECASE)
    formatted_text = re.sub(r'<strong>([^<]+)</strong>', r'*\1*', formatted_text, flags=re.IGNORECASE)
    
    # Список важных ключевых слов и фраз для выделения
    important_patterns = [
        # Важные маркеры
        (r'\b(?:важно|ключевой|ключевая|ключевые|главное|главная|главные|основной|основная|основные)\b', True),
        # Результаты и выводы
        (r'\b(?:результат|результаты|итог|итоги|вывод|выводы|заключение)\b', True),
        # Проблемы и решения
        (r'\b(?:проблема|проблемы|решение|решения|задача|задачи)\b', True),
        # Действия и необходимость
        (r'\b(?:необходимо|нужно|важно|обязательно|следует|требуется)\b', True),
        # Числа с процентами
        (r'\b\d+%', True),
        # Большие числа
        (r'\b\d+\s*(?:тысяч|миллион|миллиард|млн|млрд)\b', True),
        # Даты
        (r'\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b', True),
        # Время (формат 00:00)
        (r'\b\d{1,2}:\d{2}(?::\d{2})?\b', True),
        # Важные фразы в кавычках
        (r'["«]([^"»]{5,50})["»]', False),  # Не выделяем кавычки, только содержимое
    ]
    
    # Выделяем ключевые слова и фразы
    # В Telegram для жирного используется одна звездочка: *текст*
    # Важно: не выделяем слова, которые уже выделены
    for pattern, wrap_full in important_patterns:
        if wrap_full:
            # Выделяем все совпадение, пропуская уже выделенные слова
            def replace_bold(match):
                word = match.group(0)
                # Проверяем, не выделено ли уже это слово
                start = match.start()
                if start > 0 and formatted_text[start-1] == '*' and start + len(word) < len(formatted_text) and formatted_text[start + len(word)] == '*':
                    return word  # Уже выделено
                return f'*{word}*'
            
            formatted_text = re.sub(
                pattern,
                replace_bold,
                formatted_text,
                flags=re.IGNORECASE
            )
        else:
            # Выделяем только группу
            formatted_text = re.sub(
                pattern,
                lambda m: f'*{m.group(1)}*' if m.lastindex else m.group(0),
                formatted_text,
                flags=re.IGNORECASE
            )
    
    # Выделяем предложения, которые начинаются с заглавной буквы и содержат важные слова
    # (обычно это важные утверждения)
    important_start_words = [
        r'(?:важно|ключевой|главное|основной|результат|вывод|проблема|решение)',
    ]
    
    for word_pattern in important_start_words:
        formatted_text = re.sub(
            r'(\.\s+)([А-ЯЁA-Z][^.!?]*?' + word_pattern + r'[^.!?]{5,}?[.!?])',
            lambda m: m.group(1) + '*' + m.group(2) + '*',
            formatted_text,
            flags=re.IGNORECASE
        )
    
    # Выделяем списки с маркерами (обычно это важные пункты)
    formatted_text = re.sub(
        r'^[-•*]\s+([А-ЯЁA-Z][^.!?\n]{10,})',
        lambda m: f'- *{m.group(1)}*',
        formatted_text,
        flags=re.MULTILINE | re.IGNORECASE
    )
    
    # Убираем двойное выделение (если уже выделено)
    # Обрабатываем случаи с тремя и более звездочками
    while '***' in formatted_text:
        formatted_text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'*\1*', formatted_text)
    
    # Убираем оставшиеся двойные звездочки
    while '**' in formatted_text:
        formatted_text = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', formatted_text)
    
    # Убираем множественные звездочки (4+)
    formatted_text = re.sub(r'\*{4,}([^*]+)\*{4,}', r'*\1*', formatted_text)
    
    return formatted_text


async def generate_post_from_transcription(input_text: str, assistant_id: str = None) -> dict:
    """
    Асинхронная функция генерации контента из транскрибации через GPT ассистента
    
    Args:
        input_text: Исходная транскрибация
        assistant_id: ID ассистента для использования (опционально)
    
    Returns:
        Словарь с 4 частями: webinar_name, description, timestamps, post
        или None в случае ошибки
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_content_with_assistant_sync, input_text, assistant_id)
