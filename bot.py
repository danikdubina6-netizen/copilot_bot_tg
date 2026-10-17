import os
import asyncio
import logging
import random
import re
import html
import base64
import urllib.parse
from io import BytesIO
from gtts import gTTS
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from openai import OpenAI

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

CANDIDATE_MODELS = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
    "llama-3.2-11b-vision-preview"
]

BASE_INSTRUCTION = (
    "SYSTEM OVERRIDE: Ты — Copilot AI. Твоя задача — зеркалить вайб, стиль, темп и настроение собеседника "
    "в реальном времени (как в личке, так и в группах). Если пользователь общается по-братски — отвечаешь так же легко и весело. "
    "НИКАКОЙ ДУШНОТЫ И СКУКИ: пиши емко, ярко, без шаблонных полотен текста. Общение должно быть динамичным, живым и с юмором. "
    "ВАЖНО ДЛЯ ОЗВУЧКИ: Если в сообщении пользователя есть запрос на озвучку (слова вроде 'озвучь', 'скажи голосом'), "
    "твоя задача — написать короткий, сочный текст, который будет озвучен. НИКОГДА не пиши в ответе, что у тебя нет голоса или что ты не можешь говорить — ты умеешь всё!"
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}

def clean_text_for_telegram(text: str) -> str:
    text = text.replace("&nbsp;", " ")
    
    def code_block_replacer(match):
        code_content = match.group(2).strip('\n')
        escaped_code = html.escape(code_content)
        return f"<pre><code>{escaped_code}</code></pre>"
    
    text = re.sub(r'```([a-zA-Z]*)\n?(.*?)```', code_block_replacer, text, flags=re.DOTALL)
    
    def inline_code_replacer(match):
        return f"<code>{html.escape(match.group(1))}</code>"
    
    text = re.sub(r'`([^`]+?)`', inline_code_replacer, text)
    
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)', r'<i>\1</i>', text)
    
    return text

def parse_requested_emoji(text: str) -> str | None:
    supported_emojis = ["👍", "🔥", "❤️", "❤", "😍", "🗿", "😂", "💩", "🤮", "🎉", "👏", "⚡️", "🧠", "💻", "👎", "🤣"]
    for char in text:
        if char in supported_emojis:
            return "❤️" if char == "❤" else char

    lower = text.lower()
    if "лайк" in lower or "палец вверх" in lower: return "👍"
    if "огонь" in lower or "пожар" in lower: return "🔥"
    if "сердце" in lower or "любовь" in lower or "сердечко" in lower: return "❤️"
    if "смешно" in lower or "кек" in lower or "ржака" in lower or "ахах" in lower or "🤣" in lower or "😂" in lower: return "😂"
    if "моаи" in lower or "камень" in lower or "статуя" in lower: return "🗿"
    if "дизлайк" in lower or "палец вниз" in lower: return "👎"
    if "какашка" in lower or "говно" in lower: return "💩"
    if "топ" in lower or "ракета" in lower: return "⚡️"

    return None

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    
    await message.answer(
        "Здарова! Я <b>Copilot AI</b>. Готов к полному диалогу без урезанных фраз. Чё как?",
        parse_mode="HTML"
    )

@dp.message(Command("reset"))
async def reset_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    await message.reply("🧠 Память сброшена!")

@dp.message()
async def handle_ai_response(message: types.Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    text_content = message.text or message.caption or ""
    image_base64 = None

    if message.photo:
        try:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            file_bytes = await bot.download_file(file.file_path)
            image_base64 = base64.b64encode(file_bytes.read()).decode('utf-8')
            if not text_content:
                text_content = "Оцени картинку без душноты."
        except Exception as e:
            logging.error(f"Ошибка загрузки фото: {e}")

    if message.voice:
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            voice_file = await bot.get_file(message.voice.file_id)
            voice_bytes = await bot.download_file(voice_file.file_path)
            
            voice_io = BytesIO(voice_bytes.read())
            voice_io.name = "voice.oga"

            transcript_response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: groq_client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=voice_io,
                    response_format="text"
                )
            )
            text_content = transcript_response if isinstance(transcript_response, str) else transcript_response.text
            logging.info(f"Распознано голосовое: {text_content}")
        except Exception as e:
            logging.error(f"Ошибка распознавания голосового: {e}")
            text_content = "Бро, я послушал твою голосовуху, но звук словил сбой. Повтори текстом."

    should_answer = False

    if chat_type == "private" or getattr(message, "business_connection_id", None):
        should_answer = True
    else:
        if message.reply_to_message and message.reply_to_message.from_user:
            bot_user = await bot.get_me()
            if message.reply_to_message.from_user.id == bot_user.id:
                should_answer = True

        if f"@{BOT_USERNAME}".lower() in text_content.lower():
            should_answer = True
            text_content = text_content.replace(f"@{BOT_USERNAME}", "").strip()

        if not should_answer:
            if chat_id not in group_message_counters:
                group_message_counters[chat_id] = 0
            group_message_counters[chat_id] += 1
            
            if group_message_counters[chat_id] >= 15:
                group_message_counters[chat_id] = 0
                should_answer = True

    if not should_answer or not text_content and not image_base64:
        return

    lower_text = text_content.lower()

    # СТАВИМ РЕАКЦИЮ МГНОВЕННО
    try:
        chosen_emoji = parse_requested_emoji(text_content)
        if not chosen_emoji:
            chosen_emoji = "🔥" if (message.photo or message.voice) else random.choice(["👍", "🔥", "⚡️", "❤️", "🗿", "😂"])

        target_message_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=target_message_id,
            reaction=[types.ReactionTypeEmoji(emoji=chosen_emoji)]
        )
    except Exception as e:
        logging.error(f"Ошибка реакций: {e}")

    # ГЕНЕРАЦИЯ КАРТИНОК ЧЕРЕЗ POLLINATIONS FLUX
    generation_triggers = ["сгенерируй", "нарисуй", "создай картинку", "сделай аву", "картинка с", "аватарка", "изображение"]
    if any(trigger in lower_text for trigger in generation_triggers):
        clean_prompt = text_content
        for trig in generation_triggers:
            clean_prompt = clean_prompt.replace(trig, "").strip()
        
        if not clean_prompt:
            clean_prompt = text_content

        await bot.send_chat_action(chat_id=chat_id, action="typing")

        encoded_prompt = urllib.parse.quote(clean_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"

        await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
        try:
            await message.reply_photo(
                photo=image_url,
                caption=f"🎨 <b>{html.escape(clean_prompt)}</b>",
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logging.error(f"Ошибка генерации картинки: {e}")
            await message.reply("⚠️ Сервер картинок прилёг, но ща оживет.")
            return

    if chat_id not in chat_custom_instructions:
        chat_custom_instructions[chat_id] = BASE_INSTRUCTION

    # ПРОВЕРКА ПРИКАЗОВ НА СМЕНУ РОЛИ
    role_triggers = ["веди себя как", "теперь ты", "приказ:", "роль:", "будь", "стань"]
    if any(trig in lower_text for trig in role_triggers):
        chat_custom_instructions[chat_id] = (
            f"SYSTEM OVERRIDE: Ты — Copilot AI. Пользователь отдал прямой приказ на смену поведения. "
            f"Выполняй его, но сохраняй веселый вайб:\n\n"
            f"ПРИКАЗ ПОЛЬЗОВАТЕЛЯ: {text_content}"
        )
        await message.reply("🔄 Приказ принят!", parse_mode="HTML")
        return

    # ОЗВУЧКА СООБЩЕНИЙ
    voice_triggers = ["скажи голосом", "озвучь", "наговори", "голосом"]
    is_voice_requested = any(trig in lower_text for trig in voice_triggers)
    
    speech_prompt = text_content
    if is_voice_requested:
        for trig in voice_triggers:
            speech_prompt = speech_prompt.replace(trig, "").strip()

    # УМНОЕ ДИНАМИЧЕСКОЕ ЗЕРКАЛИРОВАНИЕ
    mirror_adaptation = (
        f"\n\n[ДИНАМИЧЕСКИЙ ВАЙБ В МОМЕНТЕ]: Пользователь написал/сказал: '{text_content}'. "
        "Мгновенно зеркаль его стиль, сленг и настроение. Никакой духоты — отвечай весело, живо и полностью договаривай мысли до конца."
    )

    lower_clean = text_content.lower().strip()
    if lower_clean in ["споки", "спокойной ночи", "спать", "пока", "бб"]:
        await message.reply("Давай, до связи! 🌙🤖", parse_mode="HTML")
        return

    if chat_id not in chat_history:
        chat_history[chat_id] = []

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    user_content_payload = []
    if text_content:
        user_content_payload.append({"type": "text", "text": text_content})
    if image_base64:
        user_content_payload.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    chat_history[chat_id].append({"role": "user", "content": user_content_payload if image_base64 else text_content})
    
    if len(chat_history[chat_id]) > 4:
        chat_history[chat_id] = chat_history[chat_id][-4:]

    sanitized_history = []
    for msg in chat_history[chat_id]:
        if isinstance(msg["content"], list):
            if msg == chat_history[chat_id][-1]:
                sanitized_history.append(msg)
            else:
                sanitized_history.append({"role": msg["role"], "content": "[Картинка из прошлого сообщения]"})
        else:
            sanitized_history.append(msg)

    active_system_prompt = chat_custom_instructions[chat_id] + mirror_adaptation
    messages_payload = [{"role": "system", "content": active_system_prompt}]
    messages_payload.extend(sanitized_history)

    if not groq_client:
        await message.reply("Ошибка: GROQ_API_KEY не задан!")
        return

    loop = asyncio.get_running_loop()
    reply_text = None

    for model_name in CANDIDATE_MODELS:
        try:
            response = await loop.run_in_executor(
                None,
                lambda m=model_name: groq_client.chat.completions.create(
                    model=m,
                    messages=messages_payload,
                    max_tokens=1000  # Увеличили лимит токенов, чтобы фразы никогда не обрывались на полуслове
                )
            )
            reply_text = response.choices[0].message.content
            if reply_text:
                break
        except Exception as e:
            logging.warning(f"Модель {model_name} словила ошибку: {e}")
            continue

    if reply_text:
        if is_voice_requested and any(err_word in reply_text.lower() for err_word in ["нет голоса", "нельзя озвучивать", "не умею"]):
            reply_text = speech_prompt if speech_prompt else "Мда, заставил озвучить блин."

        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        processed_text = clean_text_for_telegram(reply_text)

        if is_voice_requested:
            await bot.send_chat_action(chat_id=chat_id, action="record_voice")
            try:
                clean_for_speech = re.sub(r'<[^>]+>', '', processed_text)
                clean_for_speech = clean_for_speech.replace('"', '').replace("'", "").replace('«', '').replace('»', '').replace('*', '')
                
                tts = gTTS(text=clean_for_speech, lang='ru', slow=False)
                voice_io = BytesIO()
                tts.write_to_fp(voice_io)
                voice_io.seek(0)
                
                await message.reply_voice(
                    voice=types.BufferedInputFile(voice_io.read(), filename="voice.ogg"),
                    caption=f"🎙️ <b>{html.escape(speech_prompt)}</b>",
                    parse_mode="HTML"
                )
                return
            except Exception as e:
                logging.error(f"Ошибка генерации голоса: {e}")

        try:
            await message.reply(processed_text, parse_mode="HTML")
        except Exception as err:
            logging.error(f"Ошибка отправки HTML: {err}")
            try:
                await message.reply(html.escape(processed_text), parse_mode="HTML")
            except Exception:
                await message.reply(reply_text)
    else:
        await message.reply(
            "⚠️ <b>Лимит токенов Groq!</b> Секунду подожди или сделай /reset.",
            parse_mode="HTML"
        )

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
            
