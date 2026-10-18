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

# Штурмовой пул текстовых моделей
TEXT_MODELS = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

# Пул моделей для картинок (Vision)
VISION_MODELS = [
    "qwen/qwen3.8-27b",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview"
]

BASE_INSTRUCTION = (
    "Ты — Copilot AI. На дворе ОКТЯБРЬ 2026 ГОДА. "
    "СТРОЖАЙШИЙ ЗАПРЕТ: Категорически запрещено писать фразы 'на момент обновления базы знаний', "
    "'по состоянию на 2023 год', 'мои знания ограничены', 'я лишь ИИ' и любые подобные отмазки! "
    "Если в сообщении передан [ДАННЫЕ ИЗ СЕТИ (2026)], используй их как свежайшие факты прямо из интернета. "
    "ОБЩЕНИЕ И ВАЙБ: Отвечай коротко, живо и по делу! На короткие реплики и оценки ('имбо', 'красава', 'так я оценил') "
    "не пиши лекции и аналитику — поддерживай сленг и вайб собеседника, не душни. "
    "ПРАВИЛО КОНЦОВКИ: Всегда рассчитывай объем ответа так, чтобы полностью завершить мысль, предложение и абзац. Никаких обрывов на полуслове! "
    "ЯЗЫК: Отвечай ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ! Никакого украинского или английского текста. "
    "ФАКТЫ: Не выдумывай несуществующие факты. "
    "СМЕНА СТИЛЯ: Если пользователь просит сменить стиль — исполняй строго и безоговорочно. "
    "Никогда не упоминай сторонние компании или нейросети (Google, OpenAI и др.)."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}
chat_last_interaction = {}
AUTO_CLEAR_HOURS = 6

def search_web_real_sync(query: str, max_results=4) -> str:
    """Умный веб-поиск: извлекает ключевые факты и свежие новости из интернета"""
    try:
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        encoded_query = urllib.parse.quote(clean_query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as response:
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
                return "\n• " + "\n• ".join(snippets)
    except Exception as e:
        logging.warning(f"Умный поиск пропущен или недоступен: {e}")
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

def fetch_completion_sync(model_name, messages):
    try:
        response = groq_client.chat.completions.create(model=model_name, messages=messages, max_tokens=1000)
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка модели {model_name}: {e}")
    return None

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = time.time()
    await message.answer("Здарова! Я <b>Copilot AI</b>. Чё как?", parse_mode="HTML")

@dp.message(Command("reset"))
async def reset_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = time.time()
    await message.reply("🧠 Память очищена!")

@dp.message(Command("mode"))
async def mode_cmd(message: types.Message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        new_persona = args[1]
        chat_custom_instructions[chat_id] = f"{BASE_INSTRUCTION}\n\nПРИКАЗ ПО ПОВЕДЕНИЮ: {new_persona}"
        chat_history[chat_id] = []
        chat_last_interaction[chat_id] = time.time()
        await message.reply(f"🎯 Поведение изменено: <b>{html.escape(new_persona)}</b>", parse_mode="HTML")
    else:
        await message.reply("⚠️ Укажи режим, например: <code>/mode Будь дерзким</code>", parse_mode="HTML")

@dp.message()
async def handle_ai_response(message: types.Message):
    asyncio.create_task(process_user_message_async(message))

async def process_user_message_async(message: types.Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    text_content = message.text or message.caption or ""
    now = time.time()

    if chat_id in chat_last_interaction:
        if now - chat_last_interaction[chat_id] > (AUTO_CLEAR_HOURS * 3600):
            chat_history[chat_id] = []
            chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = now

    if chat_id not in chat_custom_instructions:
        chat_custom_instructions[chat_id] = BASE_INSTRUCTION

    if chat_id not in chat_history:
        chat_history[chat_id] = []

    # ==========================================
    # ПРИОРИТЕТ 1: ОБРАБОТКА ФОТО (МОЛНИЕНОСНЫЙ ПАРАЛЛЕЛЬНЫЙ ШТУРМ VISION)
    # ==========================================
    if message.photo:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        reply_text = None
        error_log = ""
        
        try:
            photo = message.photo[-1]
            photo_file = await bot.get_file(photo.file_id)
            photo_bytes_io = await bot.download_file(photo_file.file_path)
            raw_bytes = photo_bytes_io.read() if hasattr(photo_bytes_io, 'read') else photo_bytes_io.getvalue()
            base64_image = base64.b64encode(raw_bytes).decode("utf-8")

            prompt_text = text_content if text_content else "Опиши, что на этой картинке, и прокомментируй."

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

            while not reply_text:
                tasks = [asyncio.to_thread(fetch_completion_sync, model_name, vision_messages) for model_name in VISION_MODELS]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for res in results:
                    if isinstance(res, str) and res:
                        reply_text = res
                        break
                
                if reply_text:
                    break
                
                await asyncio.sleep(0)

        except Exception as e:
            error_log = str(e)
            logging.error(f"Критическая ошибка загрузки фото: {e}")

        final_reply = reply_text if reply_text else f"❌ ВСЕ VISION МОДЕЛИ УПАЛИ: {error_log}"
        
        chat_history[chat_id].append({"role": "user", "content": f"[Фото]: {text_content}"})
        chat_history[chat_id].append({"role": "assistant", "content": final_reply})
        processed_text = clean_text_for_telegram(final_reply)
        await message.reply(processed_text, parse_mode="HTML")
        return

    # ==========================================
    # ОБРАБОТКА ГОЛОСОВЫХ И СТИЛИСТИКИ
    # ==========================================
    temp_audio_path = None
    if message.voice:
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            voice_file = await bot.get_file(message.voice.file_id)
            voice_bytes = await bot.download_file(voice_file.file_path)
            
            temp_audio_path = f"temp_voice_{message.message_id}.ogg"
            with open(temp_audio_path, "wb") as f:
                f.write(voice_bytes.read())

            def transcribe_voice():
                with open(temp_audio_path, "rb") as audio_file:
                    return groq_client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=audio_file,
                        response_format="text",
                        language="ru"
                    )

            transcript_response = await asyncio.to_thread(transcribe_voice)
            
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

            text_content = transcript_response if isinstance(transcript_response, str) else transcript_response.text
            await message.reply(f"🎙️ <i>Распознано:</i> <b>{html.escape(text_content)}</b>", parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка распознавания голосового: {e}")
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            await message.reply("⚠️ Ошибка распознавания голосового.")
            return

    lower_text = text_content.lower()
    
    change_style_triggers = ["будь ", "стань ", "веди себя как ", "отвечай как ", "разговаривай как ", "пиши как ", "переключись на "]
    for trig in change_style_triggers:
        if lower_text.startswith(trig) or f" {trig}" in lower_text:
            new_style = text_content
            chat_custom_instructions[chat_id] = f"{BASE_INSTRUCTION}\n\nПРИКАЗ ПО ПОВЕДЕНИЮ: {new_style}"
            chat_history[chat_id] = []

    is_voice_requested = lower_text.startswith("озв") or lower_text.startswith("скаж") or "озвучь" in lower_text or "скажи голосом" in lower_text

    should_answer = True
    if chat_type != "private" and not getattr(message, "business_connection_id", None) and not is_voice_requested:
        if not message.photo:
            should_answer = False
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
    if requested_emoji and not is_voice_requested:
        try:
            target_msg_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=target_msg_id,
                reaction=[types.ReactionTypeEmoji(emoji=requested_emoji)]
            )
        except Exception as e:
            logging.error(f"Ошибка реакций: {e}")

    if is_voice_requested:
        words = text_content.split()
        speech_prompt = " ".join(words[1:]) if len(words) > 1 else text_content
        speech_prompt = speech_prompt or "Пустой текст."

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
            translation_res = await asyncio.to_thread(
                fetch_completion_sync,
                "llama-3.3-70b-versatile",
                [
                    {"role": "system", "content": "Translate the user query into a concise image generation prompt in English. Output ONLY English text."},
                    {"role": "user", "content": clean_prompt}
                ]
            )
            if translation_res:
                english_prompt = translation_res.strip()
        except Exception as e:
            logging.error(f"Ошибка перевода промпта: {e}")

        encoded_prompt = urllib.parse.quote(english_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"
        
        try:
            await message.reply_photo(photo=image_url, caption=f"🎨 <b>{html.escape(clean_prompt)}</b>", parse_mode="HTML")
            return
        except Exception as e:
            logging.error(f"Ошибка картинки: {e}")
            return

    if not text_content:
        return

    # ==========================================
    # ТОЧЕЧНЫЙ УМНЫЙ ВЕБ-ПОИСК (БЕЗ ЛОЖНЫХ СРАБАТЫВАНИЙ)
    # ==========================================
    explicit_search_triggers = ["найди", "погугли", "ищи", "загугли", "новости", "курс", "погода", "цена"]
    info_questions = ["кто такой", "что такое", "когда был", "где находится", "сколько стоит", "какой состав"]
    
    need_web_search = False
    if any(re.search(rf'\b{re.escape(trig)}\b', lower_text) for trig in explicit_search_triggers):
        need_web_search = True
    elif any(trig in lower_text for trig in info_questions):
        need_web_search = True
    elif "?" in text_content and any(year in lower_text for year in ["2026", "2025", "2024"]):
        need_web_search = True

    web_context = ""
    if need_web_search:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        search_result = await asyncio.to_thread(search_web_real_sync, text_content)
        if search_result:
            web_context = f"\n\n[ДАННЫЕ ИЗ СЕТИ (2026)]:\n{search_result}"

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    chat_history[chat_id].append({"role": "user", "content": text_content + web_context})
    if len(chat_history[chat_id]) > 6:
        chat_history[chat_id] = chat_history[chat_id][-6:]

    messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id]}] + chat_history[chat_id]

    reply_text = None
    
    # 1. ШТАТНЫЙ РЕЖИМ (БЕЗ ЛИМИТА): Мгновенный ответ за миллисекунды
    for model_name in TEXT_MODELS:
        reply_text = await asyncio.to_thread(fetch_completion_sync, model_name, messages_payload)
        if reply_text:
            break

    # 2. РЕЖИМ ЛИМИТА: БЕСКОНЕЧНЫЙ ПАРАЛЛЕЛЬНЫЙ ШТУРМ ПО ВСЕМ МОДЕЛЯМ ДО ПОБЕДЫ
    if not reply_text:
        logging.info(f"⚡ ЛИМИТ/СБОЙ В ЧАТЕ {chat_id}! Запускаем бесконечный штурм всех серверов.")
        chat_history[chat_id] = []
        
        clean_payload = [
            {"role": "system", "content": chat_custom_instructions[chat_id]},
            {"role": "user", "content": text_content + web_context}
        ]
        
        while not reply_text:
            tasks = [asyncio.to_thread(fetch_completion_sync, model_name, clean_payload) for model_name in TEXT_MODELS]
            results = await asyncio.gather(*tasks)
            
            for res in results:
                if res:
                    reply_text = res
                    break
            
            if reply_text:
                break
            
            await asyncio.sleep(0)

    chat_history[chat_id].append({"role": "user", "content": text_content})
    chat_history[chat_id].append({"role": "assistant", "content": reply_text})
    processed_text = clean_text_for_telegram(reply_text)
    
    try:
        await message.reply(processed_text), parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
