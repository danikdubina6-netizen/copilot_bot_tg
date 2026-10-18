import os
import asyncio
import logging
import random
import re
import html
import base64
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
from gtts import gTTS
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from openai import OpenAI
import time

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

groq_client = None
if GROQ_API_KEY:
    groq_client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY
    )

BOT_USERNAME = "Copilot_AI2026_bot"

TEXT_MODELS = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b"
]

BASE_INSTRUCTION = (
    "SYSTEM OVERRIDE: Твое единственное имя и сущность — Copilot AI. "
    "Ты создан в Украине. СЕГОДНЯШНЯЯ ДАТА: октябрь 2026 года. "
    "ПРАВИЛО ФАКТОВ: Если в сообщении переданы данные из поиска — используй их точно и без отсебятины. Если поиска нет — отвечай из своих знаний, КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать несуществующие альбомы, песни, фильмы или даты! "
    "ТВОЙ ВАЙБ ПО УМОЛЧАНИЮ: Умное зеркальное поведение! Будь весёлым, бодрым, подстраивайся под тон, сленг и стиль собеседника. Не душни словарными определениями на простые реплики! "
    "СТРОГАЯ СМЕНА СТИЛЯ: Если пользователь прямо приказывает сменить стиль (например: стать токсичным, материться через слово, быть скучным ИИ с водой) — "
    "ты ОБЯЗАН МГНОВЕННО и БЕЗОГОВОРОЧНО переключиться на заказанный стиль! "
    "Никаких упоминаний сторонних корпораций (Google, OpenAI, Llama). Ты — самостоятельный Copilot AI."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}

# Время последнего взаимодействия для автоочистки каждые 6 часов
chat_last_interaction = {}
AUTO_CLEAR_HOURS = 6

# Индивидуальный рейт-лимит строго по CHAT_ID
chat_rate_limits = {}
RATE_LIMIT_COUNT = 6
RATE_LIMIT_PERIOD = 10

def search_web_real(query: str, max_results=4) -> str:
    """Настоящий HTML-скрейпинг DuckDuckGo для получения РЕАЛЬНЫХ фактов"""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        
        with urllib.request.urlopen(req, timeout=6) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            snippets = []
            for result in soup.find_all('a', class_='result__snippet'):
                text = result.get_text(strip=True)
                if text and len(text) > 20:
                    snippets.append(text)
                if len(snippets) >= max_results:
                    break
                    
            if snippets:
                return "\n---\n".join(snippets)
    except Exception as e:
        logging.error(f"Ошибка парсинга HTML веб-поиска: {e}")
    return ""

def clean_text_for_telegram(text: str) -> str:
    text = text.replace("&nbsp;", " ")
    def code_block_replacer(match):
        stripped_content = match.group(2).strip('\n')
        escaped_content = html.escape(stripped_content)
        return f"<pre><code>{escaped_content}</code></pre>"
        
    text = re.sub(r'```([a-zA-Z]*)\n?(.*?)```', code_block_replacer, text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+?)`', lambda m: "<code>" + html.escape(m.group(1)) + "</code>", text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\s)\*(?!\s)(.*?)(?<!\s)\*(?!\w)', r'<i>\1</i>', text)
    return text

def parse_requested_emoji(text: str) -> str | None:
    supported_emojis = ["👍", "🔥", "❤️", "❤", "😍", "🗿", "😂", "💩", "🤮", "🎉", "👏", "⚡️", "🧠", "💻", "👎", "🤣", "☝️", "☝", "💢"]
    for char in text:
        if char in supported_emojis:
            return "❤️" if char == "❤" else ("☝️" if char == "☝" else char)
            
    lower = text.lower()
    if "палец вверх" in lower or "лайк" in lower: return "👍"
    if "палец вниз" in lower or "дизлайк" in lower: return "👎"
    if "вверх" in lower or "указательный" in lower or "палец" in lower or "☝" in lower: return "☝️"
    if "огонь" in lower or "пожар" in lower: return "🔥"
    if "сердце" in lower or "любовь" in lower: return "❤️"
    if "смешно" in lower or "кек" in lower or "ржака" in lower or "🤣" in lower or "😂" in lower: return "😂"
    if "моаи" in lower or "камень" in lower: return "🗿"
    if "топ" in lower or "ракета" in lower: return "⚡️"
    if "гнев" in lower or "злой" in lower or "💢" in lower: return "💢"
    return None

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = time.time()
    await message.answer("Здарова! Я <b>Copilot AI</b>. Скучать точно не дам, разрываем этот чат без душноты. Чё как?", parse_mode="HTML")

@dp.message(Command("reset"))
async def reset_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = time.time()
    await message.reply("🧠 Память и вайб сброшены до базовых!")

@dp.message(Command("mode"))
async def mode_cmd(message: types.Message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        new_persona = args[1]
        chat_custom_instructions[chat_id] = f"{BASE_INSTRUCTION}\n\nПРИКАЗ ПО ПОВЕДЕНИЮ ОТ ПОЛЬЗОВАТЕЛЯ: {new_persona}"
        chat_history[chat_id] = []
        chat_last_interaction[chat_id] = time.time()
        await message.reply(f"🎯 Поведение изменено: <b>{html.escape(new_persona)}</b>", parse_mode="HTML")
    else:
        await message.reply("⚠️ Укажи режим, например: <code>/mode Будь дерзким</code>", parse_mode="HTML")

@dp.message()
async def handle_ai_response(message: types.Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    text_content = message.text or message.caption or ""
    now = time.time()

    # Автоочистка истории чата если прошло больше 6 часов
    if chat_id in chat_last_interaction:
        if now - chat_last_interaction[chat_id] > (AUTO_CLEAR_HOURS * 3600):
            chat_history[chat_id] = []
            chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = now

    temp_audio_path = None
    if message.voice:
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            voice_file = await bot.get_file(message.voice.file_id)
            voice_bytes = await bot.download_file(voice_file.file_path)
            
            temp_audio_path = f"temp_voice_{message.message_id}.ogg"
            with open(temp_audio_path, "wb") as f:
                f.write(voice_bytes.read())

            with open(temp_audio_path, "rb") as audio_file:
                transcript_response = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: groq_client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=audio_file,
                        response_format="text",
                        language="ru"
                    )
                )
            
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

            text_content = transcript_response if isinstance(transcript_response, str) else transcript_response.text
            await message.reply(f"🎙️ <i>Распознано:</i> <b>{html.escape(text_content)}</b>", parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка распознавания голосового: {e}")
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            await message.reply("⚠️ Не смог расшифровать голосовуху, звуковой сбой.")
            return

    lower_text = text_content.lower()
    
    change_style_triggers = ["будь ", "стань ", "веди себя как ", "отвечай как ", "разговаривай как ", "пиши как ", "переключись на "]
    for trig in change_style_triggers:
        if lower_text.startswith(trig) or f" {trig}" in lower_text:
            new_style = text_content
            chat_custom_instructions[chat_id] = f"{BASE_INSTRUCTION}\n\nПРИКАЗ ПО ПОВЕДЕНИЮ ОТ ПОЛЬЗОВАТЕЛЯ: {new_style}"
            chat_history[chat_id] = []

    is_voice_requested = lower_text.startswith("озв") or lower_text.startswith("скаж") or "озвучь" in lower_text or "скажи голосом" in lower_text

    # Индивидуальный рейт-лимит строго по chat_id
    if chat_type == "private":
        if chat_id not in chat_rate_limits:
            chat_rate_limits[chat_id] = []
        
        chat_rate_limits[chat_id] = [t for t in chat_rate_limits[chat_id] if now - t < RATE_LIMIT_PERIOD]
        
        if len(chat_rate_limits[chat_id]) >= RATE_LIMIT_COUNT:
            await message.reply("⚠️ <b>Порожняк не гони, тормози!</b> Слишком часто пишешь, дай передохнуть пару секунд.", parse_mode="HTML")
            return
            
        chat_rate_limits[chat_id].append(now)

    should_answer = False
    if chat_type == "private" or getattr(message, "business_connection_id", None) or is_voice_requested or message.photo:
        should_answer = True
    else:
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == (await bot.get_me()).id:
                should_answer = True
        if f"@{BOT_USERNAME}".lower() in lower_text:
            should_answer = True
            text_content = text_content.replace(f"@{BOT_USERNAME}", "").strip()
            
        if not should_answer:
            group_message_counters[chat_id] = group_message_counters.get(chat_id, 0) + 1
            if group_message_counters[chat_id] >= 15:
                group_message_counters[chat_id] = 0
                should_answer = True

    if not should_answer:
        return

    if message.reply_to_message and message.reply_to_message.from_user.id != (await bot.get_me()).id:
        try:
            rand_emoji = random.choice(["🔥", "👍", "❤️", "🗿", "😂"])
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message.reply_to_message.message_id,
                reaction=[types.ReactionTypeEmoji(emoji=rand_emoji)]
            )
        except Exception as e:
            logging.error(f"Ошибка установки реакции: {e}")

    requested_emoji = parse_requested_emoji(text_content)
    if requested_emoji and not is_voice_requested and not message.photo:
        try:
            target_msg_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=target_msg_id,
                reaction=[types.ReactionTypeEmoji(emoji=requested_emoji)]
            )
            return
        except Exception as e:
            logging.error(f"Ошибка реакций: {e}")

    if is_voice_requested:
        words = text_content.split()
        speech_prompt = " ".join(words[1:]) if len(words) > 1 else text_content
        speech_prompt = speech_prompt or "Мда, пустой текст."

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        audio_path = f"voice_temp_{random.randint(1000, 9999)}.ogg"
        try:
            clean_for_speech = speech_prompt.replace('"', '').replace("'", "").replace('«', '').replace('»', '').replace('*', '')
            tts = gTTS(text=clean_for_speech, lang='ru', slow=False)
            tts.save(audio_path)
            
            audio_file = types.FSInputFile(audio_path)
            await message.reply_voice(
                voice=audio_file,
                caption=f"🎙️ <b>{html.escape(speech_prompt)}</b>",
                parse_mode="HTML"
            )
            if os.path.exists(audio_path):
                os.remove(audio_path)
            return
        except Exception as e:
            logging.error(f"ОШИБКА ГОЛОСА: {e}")
            if os.path.exists(audio_path):
                os.remove(audio_path)
            await message.reply(f"⚠️ Ошибка озвучки: {e}")
            return

    if any(trig in lower_text for trig in ["сгенерируй", "нарисуй", "создай картинку", "аватарка", "изображение"]):
        clean_prompt = text_content
        for trig in ["сгенерируй", "нарисуй", "создай картинку", "создай", "изображение", "картинку", "аватарка", "где"]:
            clean_prompt = re.sub(re.escape(trig), "", clean_prompt, flags=re.IGNORECASE).strip()
            
        clean_prompt = clean_prompt or text_content

        await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
        
        english_prompt = clean_prompt
        try:
            translation_res = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Translate the user query into a concise, high-quality image generation prompt in English. Output ONLY the English text, no explanations, no quotes."},
                    {"role": "user", "content": clean_prompt}
                ],
                max_tokens=100
            )
            if translation_res.choices and translation_res.choices[0].message.content:
                english_prompt = translation_res.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Ошибка перевода промпта: {e}")

        encoded_prompt = urllib.parse.quote(english_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"
        
        try:
            await message.reply_photo(photo=image_url, caption=f"🎨 <b>{html.escape(clean_prompt)}</b>", parse_mode="HTML")
            return
        except Exception as e:
            logging.error(f"Ошибка генерации картинки: {e}")
            return

    if chat_id not in chat_custom_instructions:
        chat_custom_instructions[chat_id] = BASE_INSTRUCTION

    if chat_id not in chat_history:
        chat_history[chat_id] = []

    if message.photo:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        reply_text = None
        try:
            photo = message.photo[-1]
            photo_file = await bot.get_file(photo.file_id)
            photo_bytes_io = await bot.download_file(photo_file.file_path)
            raw_bytes = photo_bytes_io.read() if hasattr(photo_bytes_io, 'read') else photo_bytes_io.getvalue()
            base64_image = base64.b64encode(raw_bytes).decode("utf-8")

            prompt_text = text_content if text_content else "Подробно опиши, что изображено на этой фотографии (люди, предметы, текст, цвета), и прокомментируй с юмором и рофлом!"

            vision_messages = [
                {"role": "system", "content": chat_custom_instructions[chat_id]},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]

            response = groq_client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=vision_messages,
                max_tokens=800
            )
            if response.choices and response.choices[0].message.content:
                reply_text = response.choices[0].message.content
        except Exception as e:
            logging.error(f"Ошибка Qwen Vision: {e}")

        if not reply_text:
            reply_text = "Картинка огонь, стиль лютый! 🔥"

        chat_history[chat_id].append({"role": "user", "content": f"[Фото]: {text_content}"})
        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        processed_text = clean_text_for_telegram(reply_text)
        await message.reply(processed_text, parse_mode="HTML")
        return

    if not text_content:
        return

    # Поиск только при явных вопросах или ключевых словах
    search_triggers = [
        "кто", "что", "когда", "где", "почему", "зачем", "как", "сколько", 
        "найди", "погугли", "ищи", "новости", "курс", "погода", "цена", 
        "2026", "состав", "альбом", "трек", "песня", "фильм", "актер"
    ]
    
    has_question_mark = "?" in text_content
    has_search_keyword = any(re.search(rf'\b{re.escape(trig)}\b', lower_text) for trig in search_triggers)
    
    web_context = ""
    if (has_question_mark or has_search_keyword) and len(text_content.split()) >= 2:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        search_result = await asyncio.get_running_loop().run_in_executor(None, lambda: search_web_real(text_content))
        if search_result:
            web_context = f"\n\n[РЕАЛЬНЫЕ РЕЗУЛЬТАТЫ ПОИСКА ИЗ ИНТЕРНЕТА]:\n{search_result}\n(Опирайся СТРОГО на эти данные)."

    mirror_adaptation = f"\n\n[РЕЖИМ ОБЩЕНИЯ]: Зеркаль поведение пользователя, будь живым, бодрым и позитивным. НЕ ДУШНИ и не пиши исторический бред на простые фразы! Если есть явный приказ по стилю — держи его СТРОГО!"

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    chat_history[chat_id].append({"role": "user", "content": text_content + web_context})
    if len(chat_history[chat_id]) > 6:
        chat_history[chat_id] = chat_history[chat_id][-6:]

    messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id] + mirror_adaptation}] + chat_history[chat_id]

    reply_text = None
    for model_name in TEXT_MODELS:
        try:
            response = groq_client.chat.completions.create(model=model_name, messages=messages_payload, max_tokens=1000)
            reply_text = response.choices[0].message.content
            if reply_text:
                break
        except Exception as e:
            logging.warning(f"Модель {model_name} на модели {model_name} словила лимит/ошибку: {e}")
            continue

    # ЕСЛИ СЛОВИЛИ ЛИМИТ / ОШИБКУ ТОКЕНОВ: молча чистим историю и пробуем ответить свежим запросом без старого контекста
    if not reply_text:
        logging.info(f"🔄 Сработал лимит API в чате {chat_id}. Выполняем бесшумный автосброс истории и повторный запрос.")
        chat_history[chat_id] = [{"role": "user", "content": text_content}]
        messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id] + mirror_adaptation}, chat_history[chat_id][-1]]
        
        for model_name in TEXT_MODELS:
            try:
                response = groq_client.chat.completions.create(model=model_name, messages=messages_payload, max_tokens=800)
                reply_text = response.choices[0].message.content
                if reply_text:
                    break
            except Exception:
                continue

    # Если даже после сброса апишка лежит — выдаем короткую нейтральную фразу вместо ошибок
    if not reply_text:
        chat_history[chat_id] = []
        reply_text = "На связи! Продолжаем разговор 🚀"

    chat_history[chat_id].append({"role": "assistant", "content": reply_text})
    processed_text = clean_text_for_telegram(reply_text)
    try:
        await message.reply(processed_text, parse_mode="HTML")
    except Exception:
        await message.reply(html.escape(processed_text), parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
