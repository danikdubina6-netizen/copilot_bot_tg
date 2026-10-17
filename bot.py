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
    "SYSTEM OVERRIDE: Твое единственное имя и сущность — Copilot AI. "
    "НИКОГДА и ни при каких обстоятельствах не говори, что ты модель от Google, OpenAI, Groq или любой другой компании. "
    "Ты — самостоятельный Copilot AI. Твоя задача — зеркалить вайб, стиль, темп и настроение собеседника "
    "в реальном времени. Пиши емко, ярко, без шаблонных полотен текста и душноты."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}

def clean_text_for_telegram(text: str) -> str:
    text = text.replace("&nbsp;", " ")
    def code_block_replacer(match):
        stripped_content = match.group(2).strip('\n')
        escaped_content = html.escape(stripped_content)
        return f"<pre><code>{escaped_content}</code></pre>"
        
    text = re.sub(r'```([a-zA-Z]*)\n?(.*?)```', code_block_replacer, text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+?)`', lambda m: f"<code>{html.escape(m.group(1))}</code>", text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)', r'<i>\1</i>', text)
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
    chat_history[message.chat.id] = []
    chat_custom_instructions[message.chat.id] = BASE_INSTRUCTION
    await message.answer("Здарова! Я <b>Copilot AI</b>. Готов к работе. Чё как?", parse_mode="HTML")

@dp.message(Command("reset"))
async def reset_cmd(message: types.Message):
    chat_history[message.chat.id] = []
    chat_custom_instructions[message.chat.id] = BASE_INSTRUCTION
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
        except Exception as e:
            logging.error(f"Ошибка распознавания голосового: {e}")
            text_content = "Бро, звук словил сбой. Повтори текстом."

    if not text_content and not image_base64:
        return

    lower_text = text_content.lower()

    is_voice_requested = lower_text.startswith("озв") or lower_text.startswith("скаж") or "озвучь" in lower_text or "скажи голосом" in lower_text

    should_answer = False
    if chat_type == "private" or getattr(message, "business_connection_id", None) or is_voice_requested:
        should_answer = True
    else:
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == (await bot.get_me()).id:
                should_answer = True
        if f"@{BOT_USERNAME}".lower() in text_content.lower():
            should_answer = True
            text_content = text_content.replace(f"@{BOT_USERNAME}", "").strip()
        if not should_answer:
            group_message_counters[chat_id] = group_message_counters.get(chat_id, 0) + 1
            if group_message_counters[chat_id] >= 15:
                group_message_counters[chat_id] = 0
                should_answer = True

    if not should_answer:
        return

    # Ставим реакцию строго на текущее сообщение пользователя без сбоев
    try:
        chosen_emoji = parse_requested_emoji(text_content) or ("🔥" if (message.photo or message.voice) else random.choice(["👍", "🔥", "⚡️", "❤️", "🗿", "😂"]))
        await bot.set_message_reaction(chat_id=chat_id, message_id=message.message_id, reaction=[types.ReactionTypeEmoji(emoji=chosen_emoji)])
    except Exception as e:
        logging.error(f"Ошибка реакций: {e}")

    if is_voice_requested:
        words = text_content.split()
        speech_prompt = " ".join(words[1:]) if len(words) > 1 else text_content
        speech_prompt = speech_prompt or "Мда, пустой текст."

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        try:
            clean_for_speech = speech_prompt.replace('"', '').replace("'", "").replace('«', '').replace('»', '').replace('*', '')
            
            tts = gTTS(text=clean_for_speech, lang='ru', slow=False)
            audio_path = "voice_temp.ogg"
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
            logging.error(f"КРИТИЧЕСКАЯ ОШИБКА ГЕНЕРАЦИИ ГОЛОСА: {e}")
            await message.reply(f"⚠️ Ошибка озвучки: {e}")
            return

    generation_triggers = ["сгенерируй", "нарисуй", "создай картинку", "сделай аву", "картинка с", "аватарка", "изображение"]
    if any(trigger in lower_text for trigger in generation_triggers):
        clean_prompt = text_content
        for trig in generation_triggers:
            clean_prompt = clean_prompt.replace(trig, "").strip()
        clean_prompt = clean_prompt or text_content

        await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
        image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?model=flux&width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"
        try:
            await message.reply_photo(photo=image_url, caption=f"🎨 <b>{html.escape(clean_prompt)}</b>", parse_mode="HTML")
            return
        except Exception as e:
            logging.error(f"Ошибка генерации картинки: {e}")
            await message.reply("⚠️ Сервер картинок прилёг.")
            return

    if chat_id not in chat_custom_instructions:
        chat_custom_instructions[chat_id] = BASE_INSTRUCTION

    mirror_adaptation = f"\n\n[ВАЙБ]: Пользователь написал: '{text_content}'. Отвечай весело, живо, коротко."
    if chat_id not in chat_history:
        chat_history[chat_id] = []

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    chat_history[chat_id].append({"role": "user", "content": text_content})
    if len(chat_history[chat_id]) > 4:
        chat_history[chat_id] = chat_history[chat_id][-4:]

    messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id] + mirror_adaptation}] + chat_history[chat_id]

    reply_text = None
    for model_name in CANDIDATE_MODELS:
        try:
            response = groq_client.chat.completions.create(model=model_name, messages=messages_payload, max_tokens=1000)
            reply_text = response.choices[0].message.content
            if reply_text:
                break
        except Exception as e:
            logging.warning(f"Модель {model_name} словила ошибку: {e}")
            continue

    if reply_text:
        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        processed_text = clean_text_for_telegram(reply_text)
        try:
            await message.reply(processed_text, parse_mode="HTML")
        except Exception:
            await message.reply(html.escape(processed_text), parse_mode="HTML")
    else:
        await message.reply("⚠️ <b>Лимит токенов Groq!</b> Сделай /reset.", parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
