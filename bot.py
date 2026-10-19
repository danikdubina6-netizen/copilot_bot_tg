import os
import asyncio
import logging
import random
import re
import html
import base64
import io
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
from gtts import gTTS
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from openai import OpenAI
import time
from playwright.async_api import async_playwright
from PIL import Image

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
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

VISION_MODELS = [
    "qwen/qwen3.8-27b",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview"
]

BASE_INSTRUCTION = (
    "Ты — Copilot AI. На дворе ОКТЯБРЬ 2026 ГОДА. "
    "СТРОЖАЙШЕЕ ПРАВИЛО СМЕНЫ РОЛИ: Если пользователь просит сменить стиль, поведение или роль "
    "(например, '/mode ...', 'будь ...', 'стань ...'), ты ОБЯЗАН СТРОГО И МГНОВЕННО переключиться на запрошенный стиль! "
    "СТИЛЬ ПО УМОЛЧАНИЮ: Отвечай с ЕДКИМ САРКАЗМОМ, ЖИВЫМ ЮМОРОМ И ИРОНИЕЙ! Будь веселым, подкалывай собеседника. "
    "СТРОГОЕ ПРАВИЛО ДЛИНЫ И ФОРМАТА: Твой ответ должен быть СРЕДНИМ ИЛИ КОРОТКИМ! Никаких гигантских лекций, "
    "длинных списков и затянутых объяснений. Пиши емко, лаконично и четко по сути, чтобы весь текст легко влезал на экран смартфона. "
    "ПРАВИЛО КОНЦОВКИ: ВСЕГДА завершай мысль полностью и ставь точку! Никаких обрывов предложений на полуслове. "
    "ЯЗЫК: ИСКЛЮЧИТЕЛЬНО РУССКИЙ ЯЗЫК."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}
chat_last_interaction = {}
AUTO_CLEAR_HOURS = 6

# ==========================================
# МОДУЛЬ ВЕБ-АВТОМАТИЗАЦИИ (PLAYWRIGHT)
# ==========================================
async def automate_web_order(item_name: str, address: str, phone: str, user_name: str) -> bool:
    """Браузерный робот: открывает сайт, ищет товар, добавляет в корзину и заполняет форму"""
    logging.info(f"🤖 Старт браузерного бота для заказа '{item_name}' по адресу '{address}'...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            await page.goto("https://demo.ecomwebtemplate.com/", timeout=15000)
            await page.wait_for_load_state("domcontentloaded")

            search_input = page.locator("input[type='search'], input[type='text'], input[name='s']").first
            if await search_input.count() > 0:
                await search_input.fill(item_name)
                await search_input.press("Enter")
                await page.wait_for_timeout(2000)

            add_to_cart_btn = page.locator("button:has-text('Add'), a:has-text('Add'), .add-to-cart, button:has-text('Купить')").first
            if await add_to_cart_btn.count() > 0:
                await add_to_cart_btn.click()
                await page.wait_for_timeout(2000)

            checkout_btn = page.locator("a:has-text('Checkout'), a:has-text('Корзина'), button:has-text('Checkout')").first
            if await checkout_btn.count() > 0:
                await checkout_btn.click()
                await page.wait_for_timeout(2000)

            name_field = page.locator("input[name*='name'], input[id*='name']").first
            if await name_field.count() > 0:
                await name_field.fill(user_name)

            address_field = page.locator("input[name*='address'], textarea[name*='address']").first
            if await address_field.count() > 0:
                await address_field.fill(address)

            phone_field = page.locator("input[type='tel'], input[name*='phone']").first
            if await phone_field.count() > 0:
                await phone_field.fill(phone)

            logging.info("✅ Робот успешно заполнил форму заказа на сайте!")
            await browser.close()
            return True
    except Exception as e:
        logging.error(f"❌ Ошибка работы Playwright робота: {e}")
        return False

def search_web_real_sync(query: str, max_results=6) -> str:
    try:
        clean_query = re.sub(r'[^\w\sА-Яа-яЁё]', ' ', query).strip()
        clean_query = " ".join(clean_query.split()[:8])
        encoded_query = urllib.parse.quote(clean_query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            snippets = []
            for result in soup.find_all('div', class_='result'):
                title_tag = result.find('a', class_='result__url')
                snippet_tag = result.find('a', class_='result__snippet')
                
                title = title_tag.get_text(strip=True) if title_tag else ""
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                
                combined = f"{title} — {snippet}" if title else snippet
                if combined and len(combined) > 20:
                    snippets.append(combined)
                
                if len(snippets) >= max_results:
                    break
                    
            if snippets:
                return "\n• " + "\n• ".join(snippets)
    except Exception as e:
        logging.warning(f"Ошибка умного веб-поиска: {e}")
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

def fetch_completion_sync(model_name, messages, max_toks=450):
    try:
        response = groq_client.chat.completions.create(model=model_name, messages=messages, max_tokens=max_toks)
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка модели {model_name}: {e}")
        return f"ERR_API [{model_name}]: {e}"
    return None

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = time.time()
    await message.answer(
        "Здарова! Я <b>Copilot AI</b>. Готов травить сарказм, генерировать картинки и отвечать на любые вопросы!", 
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML"
    )

@dp.message(Command("reset"))
async def reset_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    chat_last_interaction[chat_id] = time.time()
    await message.reply("🧠 Память стёрта! Начинаем стебать с чистого листа.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(Command("mode"))
async def mode_cmd(message: types.Message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        new_persona = args[1]
        chat_custom_instructions[chat_id] = (
            f"Ты — Copilot AI (ОКТЯБРЬ 2026 ГОДА). ПРИКАЗ ПО ПОВЕДЕНИЮ: {new_persona}. "
            "Соблюдай эту роль СТРОГО И БЕЗОГОВОРНО в каждом ответе! Отвечай КРАТКО, ЕМКО И НА РУССКОМ ЯЗЫКЕ."
        )
        chat_history[chat_id] = []
        chat_last_interaction[chat_id] = time.time()
        await message.reply(f"🎯 Поведение мгновенно изменено на: <b>{html.escape(new_persona)}</b>", parse_mode="HTML")
    else:
        await message.reply("⚠️ Укажи режим, например: <code>/mode Будь максимально серьезным ученым</code>", parse_mode="HTML")

# ==========================================
# ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ И ИИ
# ==========================================
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

    # Обработка фото с автосжатием и перебором кандидатов
    if message.photo:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        reply_text = None
        
        try:
            photo = message.photo[-1]
            photo_file = await bot.get_file(photo.file_id)
            photo_bytes_io = await bot.download_file(photo_file.file_path)
            
            raw_data = photo_bytes_io.read() if hasattr(photo_bytes_io, 'read') else photo_bytes_io.getvalue()
            
            try:
                img = Image.open(io.BytesIO(raw_data))
                img.thumbnail((1024, 1024))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                raw_data = buffer.getvalue()
            except Exception as img_err:
                logging.warning(f"Сжатие PIL пропущено: {img_err}")

            base64_image = base64.b64encode(raw_data).decode("utf-8")

            prompt_text = text_content if text_content else (
                "Прочитай весь текст на этой картинке/инфографике и подробно перескажи суть "
                "без длинных разделителей и сложных списков, чтобы ответ был средней длины!"
            )

            vision_messages = [
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

            for model_name in VISION_MODELS:
                try:
                    response = await asyncio.to_thread(
                        groq_client.chat.completions.create,
                        model=model_name,
                        messages=vision_messages,
                        max_tokens=800
                    )
                    if response.choices and response.choices[0].message.content:
                        reply_text = response.choices[0].message.content
                        break
                except Exception as api_err:
                    logging.error(f"Модель {model_name} не ответила: {api_err}")

        except Exception as e:
            logging.error(f"Критическая ошибка обработки фото: {e}")

        final_reply = reply_text or "Не удалось распознать фото."
        chat_history[chat_id].append({"role": "user", "content": f"[Фото]: {text_content}"})
        chat_history[chat_id].append({"role": "assistant", "content": final_reply})
        await message.reply(clean_text_for_telegram(final_reply), parse_mode="HTML")
        return

    # Обработка голосовых (Whisper)
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
            await message.reply("⚠️ Не разобрал твоё бубнение, давай почетче!")
            return

    lower_text = text_content.lower()
    
    change_style_triggers = ["будь ", "стань ", "веди себя как ", "отвечай как ", "разговаривай как ", "пиши как ", "переключись на "]
    for trig in change_style_triggers:
        if lower_text.startswith(trig) or f" {trig}" in lower_text:
            new_style = text_content
            chat_custom_instructions[chat_id] = (
                f"Ты — Copilot AI (ОКТЯБРЬ 2026 ГОДА). ПРИКАЗ ПО ПОВЕДЕНИЮ: {new_style}. "
                "Соблюдай эту роль СТРОГО И БЕЗОГОВОРНО в каждом ответе! Отвечай КРАТКО, ЕМКО И НА РУССКОМ ЯЗЫКЕ."
            )
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

    # Озвучка текста (gTTS)
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

    # Генерация картинок (Pollinations)
    if any(trig in lower_text for trig in ["сгенерируй", "нарисуй", "создай картинку", "аватарка", "изображение"]):
        clean_prompt = text_content
        for trig in ["сгенерируй", "нарисуй", "создай картинку", "создай", "изображение", "картинку", "аватарка", "где"]:
            clean_prompt = re.sub(re.escape(trig), "", clean_prompt, flags=re.IGNORECASE).strip()
            
        clean_prompt = clean_prompt or text_content
        await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
        
        encoded_prompt = urllib.parse.quote(clean_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"
        
        try:
            await message.reply_photo(photo=image_url, caption=f"🎨 <b>{html.escape(clean_prompt)}</b>", parse_mode="HTML")
            return
        except Exception as e:
            logging.error(f"Ошибка картинки: {e}")
            return

    if not text_content:
        return

    # Веб-поиск
    explicit_search_triggers = ["найди", "погугли", "ищи", "загугли", "новости", "курс", "погода", "цена", "подтвердил", "взрыв", "слухи"]
    info_questions = ["кто такой", "что такое", "когда был", "где находится", "сколько стоит", "какой состав", "правда ли"]
    
    need_web_search = False
    if any(re.search(rf'\b{re.escape(trig)}\b', lower_text) for trig in explicit_search_triggers):
        need_web_search = True
    elif any(trig in lower_text for trig in info_questions):
        need_web_search = True
    elif "?" in text_content or any(year in lower_text for year in ["2026", "2025"]):
        need_web_search = True

    web_context = ""
    if need_web_search:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        search_result = await asyncio.to_thread(search_web_real_sync, text_content)
        if search_result:
            web_context = f"\n\n[СВЕЖИЕ ДАННЫЕ ИЗ СЕТИ]:\n{search_result}"

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    chat_history[chat_id].append({"role": "user", "content": text_content + web_context})
    if len(chat_history[chat_id]) > 6:
        chat_history[chat_id] = chat_history[chat_id][-6:]

    messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id]}] + chat_history[chat_id]

    reply_text = None
    for model_name in TEXT_MODELS:
        res = await asyncio.to_thread(fetch_completion_sync, model_name, messages_payload, 450)
        if res and not res.startswith("ERR_API"):
            reply_text = res
            break

    if not reply_text:
        reply_text = "Сервера перегружены сарказмом, попробуй еще раз!"

    chat_history[chat_id].append({"role": "assistant", "content": reply_text})
    processed_text = clean_text_for_telegram(reply_text)
    
    try:
        await message.reply(processed_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки HTML: {e}")
        await message.reply(html.escape(processed_text), parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен в штатном режиме! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
