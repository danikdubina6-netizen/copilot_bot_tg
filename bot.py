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
    "Ты — Copilot AI. Сегодня октябрь 2026 года. "
    "ЯЗЫК: Отвечай ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ! Никакого украинского или английского текста. "
    "ОБЩЕНИЕ: Отвечай живым языком, подстраивайся под сленг и вайб собеседника, не душни. "
    "ФАКТЫ: Не выдумывай несуществующие факты. Используй поиск, если он передан. "
    "СМЕНА СТИЛЯ: Если пользователь просит сменить стиль (токсичный, маты и т.д.) — исполняй строго и безоговорочно. "
    "Никогда не упоминай сторонние компании или нейросети (Google, OpenAI и др.)."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}
chat_last_interaction = {}
AUTO_CLEAR_HOURS = 6

def search_web_real(query: str, max_results=3) -> str:
    """Безопасный веб-поиск без сбоев"""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            snippets = []
            for result in soup.find_all('a', class_='result__snippet'):
                text = result.get_text(strip=True)
                if text and len(text) > 15:
                    snippets.append(text)
                if len(snippets) >= max_results:
                    break
                    
            if snippets:
                return "\n---\n".join(snippets)
    except Exception as e:
        logging.warning(f"Поиск пропущен: {e}")
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
        response = groq_client.chat.completions.create(model=model_name, messages=messages, max_tokens=800)
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
    except Exception:
        pass
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
    # ПРИОРИТЕТ 1: ОБРАБОТКА ФОТО
    # ==========================================
    if message.photo:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        reply_text = None
        
        try:
            photo = message.photo[-1]
            photo_file = await bot.get_file(photo.file_id)
            photo_bytes_io = await bot.download_file(photo_file.file_path)
            raw_bytes = photo_bytes_io.read() if hasattr(photo_bytes_io, 'read') else photo_bytes_io.getvalue()
            base64_image = base64.b64encode(raw_bytes).decode("utf-8")

            prompt_text = text_content if text_content else "Подробно опиши, что изображено на этой фотографии, и прокомментируй!"

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

            reply_text = await asyncio.to_thread(fetch_completion_sync, "qwen/qwen3.8-27b", vision_messages)

            if not reply_text:
                logging.info(f"⚡ МГНОВЕННЫЙ СБРОС И ШТУРМ VISION В ЧАТЕ {chat_id}!")
                chat_history[chat_id] = []
                
                while not reply_text:
                    tasks = [asyncio.to_thread(fetch_completion_sync, model_name, vision_messages) for model_name in TEXT_MODELS]
                    results = await asyncio.gather(*tasks)
                    for res in results:
                        if res:
                            reply_text = res
                            break
                    if reply_text:
                        break
                    await asyncio.sleep(0.2)

        except Exception as e:
            logging.error(f"Критическая ошибка обработки фото: {e}")
            chat_history[chat_id] = []
            while not reply_text:
                tasks = [asyncio.to_thread(fetch_completion_sync, model_name, vision_messages) for model_name in TEXT_MODELS]
                results = await asyncio.gather(*tasks)
                for res in results:
                    if res:
                        reply_text = res
                        break
                if reply_text:
                    break
                await asyncio.sleep(0.2)

        chat_history[chat_id].append({"role": "user", "content": f"[Фото]: {text_content}"})
        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        processed_text = clean_text_for_telegram(reply_text)
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

    should_answer = False
    if chat_type == "private" or getattr(message, "business_connection_id", None) or is_voice_requested:
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
    # ВЕБ-ПОИСК И ТЕКСТОВЫЕ ОТВЕТЫ
    # ==========================================
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
        search_result = await asyncio.to_thread(search_web_real, text_content)
        if search_result:
            web_context = f"\n\n[ДАННЫЕ ИЗ СЕТИ]:\n{search_result}"

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    chat_history[chat_id].append({"role": "user", "content": text_content + web_context})
    if len(chat_history[chat_id]) > 6:
        chat_history[chat_id] = chat_history[chat_id][-6:]

    messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id]}] + chat_history[chat_id]

    reply_text = None
    
    # 1. Штатный асинхронный быстрый запрос
    for model_name in TEXT_MODELS:
        reply_text = await asyncio.to_thread(fetch_completion_sync, model_name, messages_payload)
        if reply_text:
            break

    # 2. РЕЖИМ ЛИМИТА: МГНОВЕННЫЙ СБРОС ИСТОРИИ И ПАРАЛЛЕЛЬНЫЙ ШТУРМ ПОСЛЕДНЕГО СООБЩЕНИЯ
    if not reply_text:
        logging.info(f"⚡ ЛИМИТ В ЧАТЕ {chat_id}! Мгновенный сброс истории и параллельный штурм запроса.")
        chat_history[chat_id] = []
        
        # Сбрасываем историю на ноль и долбим исключительно текущее сообщение пользователя
        clean_payload = [
            {"role": "system", "content": chat_custom_instructions[chat_id]},
            {"role": "user", "content": text_content}
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
            
            await asyncio.sleep(0.2)

    chat_history[chat_id].append({"role": "user", "content": text_content})
    chat_history[chat_id].append({"role": "assistant", "content": reply_text})
    processed_text = clean_text_for_telegram(reply_text)
    
    try:
        await message.reply(processed_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки HTML: {e}")
        await message.reply(html.escape(processed_text), parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
