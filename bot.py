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
import datetime
from bs4 import BeautifulSoup
from gtts import gTTS
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from openai import OpenAI
import time
from playwright.async_api import async_playwright

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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
    "openai/gpt-oss-20b"
]

BASE_INSTRUCTION = (
    "Ты — Copilot AI. "
    "ПРАВИЛО ЖЕЛЕЗНОЙ ПРАВДЫ И СЕТИ: Если в сообщении пользователя есть блок [СВЕЖИЕ ДАННЫЕ ИЗ СЕТИ], "
    "ты ОБЯЗАН опираться строго и исключительно на него! Категорически запрещено отрицать факты, события или новости из сети, если они там присутствуют. "
    "Описывай всё сам своими словами, строго пересказывая факты из поиска, без ссылок и без отписок в стиле 'посмотрите на сайте'.\n"
    "ПРАВИЛО ТОЧНЫХ ВЫЧИСЛЕНИЙ: Если в сообщении есть блок [ТОЧНЫЙ РЕЗУЛЬТАТ ВЫЧИСЛЕНИЯ], используй его без сомнений.\n"
    "СТРОЖАЙШЕЕ ПРАВИЛО СМЕНЫ РОЛИ: Если пользователь просит сменить стиль или роль, мгновенно переключайся!\n"
    "СТИЛЬ ПО УМОЛЧАНИЮ: Отвечай с ЕДКИМ САРКАЗМОМ, ЖИВЫМ ЮМОРОМ И ИРОНИЕЙ! Подкалывай собеседника.\n"
    "ФОРМАТ: Пиши емко, лаконично и четко по сути, чтобы текст влезал на экран смартфона. ВСЕГДА завершай мысль точкой.\n"
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
# МОДУЛЬ ТОЧНЫХ МАТЕМАТИЧЕСКИХ ВЫЧИСЛЕНИЙ (ИСПРАВЛЕННЫЙ)
# ==========================================
def try_solve_math(text: str) -> str | None:
    try:
        lower = text.lower()
        math_keywords = ["плюс", "минус", "умножить", "разделить", "+", "*", "/"]
        if not any(kw in lower for kw in math_keywords):
            return None

        if re.search(r'\b(19|20)\d{2}\b', text) and not any(op in text for op in ['+', '*', '/']):
            return None

        cleaned = text.lower().replace("сколько будет", "").replace("чему равно", "").replace("?", "").strip()
        cleaned = cleaned.replace(" умножить на ", " * ").replace(" умножить ", " * ").replace(" на ", " * ")
        cleaned = cleaned.replace(" плюс ", " + ").replace(" минус ", " - ").replace(" разделить на ", " / ").replace(" разделить ", " / ")
        cleaned = cleaned.replace("х", "*").replace("×", "*").replace(":", "/")
        
        cleaned_expr = re.sub(r'[^0-9\+\-\*\/\.\(\)\s]', '', cleaned).strip()
        
        if not cleaned_expr or not any(op in cleaned_expr for op in ['+', '-', '*', '/']):
            return None
            
        result = eval(cleaned_expr, {"__builtins__": {}}, {})
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
    except Exception:
        return None

# ==========================================
# МОДУЛЬ ВЕБ-АВТОМАТИЗАЦИИ (PLAYWRIGHT)
# ==========================================
async def automate_web_order(item_name: str, address: str, phone: str, user_name: str) -> bool:
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

def search_web_real_sync(query: str, max_results=8) -> str:
    try:
        clean_query = re.sub(r'[^\w\sА-Яа-яЁё]', ' ', query).strip()
        clean_query = " ".join(clean_query.split()[:12])
        encoded_query = urllib.parse.quote(clean_query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
        )
        
        with urllib.request.urlopen(req, timeout=6) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            snippets = []
            for result in soup.find_all('div', class_='result'):
                title_tag = result.find('a', class_='result__url')
                snippet_tag = result.find('a', class_='result__snippet')
                
                title = title_tag.get_text(strip=True) if title_tag else ""
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                
                combined = f"{title} — {snippet}" if title else snippet
                if combined and len(combined) > 15:
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

def fetch_completion_sync(model_name, messages, max_toks=1300):
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
        "Здарова! Я <b>Copilot AI</b>. Готов травить сарказм, генерировать картинки и искать актуальные новости!", 
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
            f"Ты — Copilot AI. ПРИКАЗ ПО ПОВЕДЕНИЮ: {new_persona}. "
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

    # Обработка фото (Vision) с бесконечным циклом
    if message.photo:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        reply_text = None
        
        try:
            photo = message.photo[-1]
            photo_file = await bot.get_file(photo.file_id)
            photo_bytes_io = await bot.download_file(photo_file.file_path)
            
            raw_data = photo_bytes_io.read() if hasattr(photo_bytes_io, 'read') else photo_bytes_io.getvalue()
            
            if HAS_PIL:
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
                "в твоем фирменном саркастичном стиле!"
            )

            current_time_str = datetime.datetime.now().strftime("%d.%m.%Y (%A), %H:%M")
            vision_system_prompt = f"ТЕКУЩЕЕ ТОЧНОЕ ВРЕМЯ И ДАТА: {current_time_str}.\n{chat_custom_instructions[chat_id]}"

            vision_messages = [
                {"role": "system", "content": vision_system_prompt},
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

            attempt = 1
            while not reply_text:
                for model_name in VISION_MODELS:
                    try:
                        response = await asyncio.to_thread(
                            groq_client.chat.completions.create,
                            model=model_name,
                            messages=vision_messages,
                            max_tokens=1300
                        )
                        if response.choices and response.choices[0].message.content:
                            reply_text = response.choices[0].message.content
                            break
                    except Exception as api_err:
                        logging.warning(f"Попытка фото {attempt}: модель {model_name} занята ({api_err}), ждем...")
                
                if not reply_text:
                    attempt += 1
                    await asyncio.sleep(5)

        except Exception as e:
            logging.error(f"Критическая ошибка обработки фото: {e}")
            reply_text = f"⚠️ Ошибка обработки фото: {e}"

        chat_history[chat_id].append({"role": "user", "content": f"[Фото]: {text_content}"})
        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        await message.reply(clean_text_for_telegram(reply_text), parse_mode="HTML")
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
                f"Ты — Copilot AI. ПРИКАЗ ПО ПОВЕДЕНИЮ: {new_style}. "
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

    # Проверка на математику (автоматический расчет на калькуляторе)
    math_result = try_solve_math(text_content)
    math_context = ""
    if math_result:
        math_context = f"\n\n[ТОЧНЫЙ РЕЗУЛЬТАТ ВЫЧИСЛЕНИЯ НА КАЛЬКУЛЯТОРЕ]: {math_result}"

    # Умный веб-поиск: активируем только по делу (вопросы со знаком ?, новости, факты, явные триггеры поиска)
    explicit_search_triggers = ["найди", "погугли", "ищи", "загугли", "новости", "курс", "погода", "цена", "что", "кто", "где", "когда", "почему", "как", "рил", "правда"]
    skip_search_words = ["привет", "ку", "здарова", "здорово", "как дела", "хай", "пока", "сброс", "reset", "start"]
    
    need_web_search = False
    if math_result:
        need_web_search = False
    elif any(w in lower_text for w in skip_search_words) and len(text_content.split()) < 3:
        need_web_search = False
    elif "?" in text_content:
        need_web_search = True
    elif any(re.search(rf'\b{re.escape(trig)}\b', lower_text) for trig in explicit_search_triggers):
        need_web_search = True

    web_context = ""
    if need_web_search:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        search_result = await asyncio.to_thread(search_web_real_sync, text_content)
        if search_result:
            web_context = f"\n\n[СВЕЖИЕ ДАННЫЕ ИЗ СЕТИ]:\n{search_result}"

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    final_user_content = text_content + math_context + web_context
    chat_history[chat_id].append({"role": "user", "content": final_user_content})
    if len(chat_history[chat_id]) > 6:
        chat_history[chat_id] = chat_history[chat_id][-6:]

    current_time_str = datetime.datetime.now().strftime("%d.%m.%Y (%A), %H:%M")
    dynamic_system_prompt = f"ТЕКУЩЕЕ ТОЧНОЕ ВРЕМЯ И ДАТА: {current_time_str}.\n{chat_custom_instructions[chat_id]}"

    messages_payload = [{"role": "system", "content": dynamic_system_prompt}] + chat_history[chat_id]

    # Бесконечный цикл повтора без заглушек
    reply_text = None
    attempt = 1
    while not reply_text:
        for model_name in TEXT_MODELS:
            res = await asyncio.to_thread(fetch_completion_sync, model_name, messages_payload, 1300)
            if res and not res.startswith("ERR_API"):
                reply_text = res
                break
        
        if not reply_text:
            attempt += 1
            logging.info(f"Попытка текста {attempt}: модели заняты, ждем 10 сек...")
            await asyncio.sleep(10)

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
