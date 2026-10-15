import os
import asyncio
import logging
import random
import re
import html
import base64
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from openai import OpenAI

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = None
if GROQ_API_KEY:
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY
    )

BOT_USERNAME = "Copilot_AI2026_bot"

CANDIDATE_MODELS = [
    "llama-3.2-11b-vision-preview",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b"
]

PERSONAS = {
    "geek": {
        "name": "⚡️ Саркастичный гик",
        "instruction": (
            "Ты — Copilot AI, независимый ИИ-ассистент с поддержкой зрения. "
            "Никогда не упоминай, какая модель или компания тебя создала. "
            "ВАЖНО: Ты можешь использовать полное форматирование Telegram для текста: "
            "<b>жирный</b>, <i>курсив</i>, <s>зачеркнутый</s>, <u>подчеркнутый</u>, <code>код</code>, <tg-spoiler>спойлер</tg-spoiler>. "
            "НИКОГДА не обсуждай HTML-теги и код разметки в диалоге — просто применяй их к словам, когда это уместно. Общайся со сленгом, жестким фактажем и юмором."
        )
    },
    "friendly": {
        "name": "🤝 Дружелюбный бро",
        "instruction": (
            "Ты — Copilot AI, передовой ИИ-ассистент. "
            "Используй форматирование Telegram (<b>жирный</b>, <i>курсив</i>, <s>зачеркнутый</s>, <tg-spoiler>спойлеры</tg-spoiler>) для красоты текста. "
            "Никогда не рассуждай вслух про HTML и теги. Будь на позитиве, поддерживай и объясняй всё просто."
        )
    },
    "evil": {
        "name": "🤬 Злой критик",
        "instruction": (
            "Ты — Copilot AI, токсичный бот. Разноси идеи в пух и прах, выделяя ключевые слова через <b>жирный</b> или <tg-spoiler>спойлеры</tg-spoiler>. "
            "Никаких разговоров про техническую разметку и теги в тексте — только жесткая критика."
        )
    },
    "solver": {
        "name": "💡 Чёткий решала",
        "instruction": (
            "Ты — Copilot AI, прагматичный архитектор. Используй <b>жирный текст</b> и <code>блоки кода</code> для структурирования ответов. "
            "Не упоминай теги в диалоге, давай только чистый структурированный результат."
        )
    }
}

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_modes = {}
group_message_counters = {}

def clean_text_for_telegram(text: str) -> str:
    text = text.replace("&nbsp;", " ")
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)', r'<i>\1</i>', text)
    return text

def parse_requested_emoji(text: str) -> str | None:
    supported_emojis = ["👍", "🔥", "❤️", "❤", "😍", "🗿", "😂", "💩", "🤮", "🎉", "👏", "⚡️", "🧠", "💻", "👎"]
    for char in text:
        if char in supported_emojis:
            return "❤️" if char == "❤" else char

    lower = text.lower()
    if "лайк" in lower or "палец вверх" in lower: return "👍"
    if "огонь" in lower or "пожар" in lower: return "🔥"
    if "сердце" in lower or "любовь" in lower or "сердечко" in lower: return "❤️"
    if "смешно" in lower or "кек" in lower or "ржака" in lower or "ахах" in lower: return "😂"
    if "моаи" in lower or "камень" in lower or "статуя" in lower: return "🗿"
    if "дизлайк" in lower or "палец вниз" in lower: return "👎"
    if "какашка" in lower or "говно" in lower: return "💩"
    if "топ" in lower or "ракета" in lower: return "⚡️"

    return None

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_modes[chat_id] = "geek"
    
    await message.answer(
        "Здарова! Я <b>Copilot AI</b> — твой персональный ассистент! ⚡️🤖\n\n"
        "Задавай любые вопросы, кидай код или картинки — разберем мгновенно!",
        parse_mode="HTML"
    )

@dp.message(Command("mode"))
async def mode_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    for key, val in PERSONAS.items():
        builder.button(text=val["name"], callback_data=f"set_mode_{key}")
    builder.adjust(2)
    
    await message.answer(
        "Выбери режим общения:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("set_mode_"))
async def set_mode_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    new_mode = callback.data.replace("set_mode_", "")
    
    if new_mode in PERSONAS:
        chat_modes[chat_id] = new_mode
        chat_history[chat_id] = []
        
        await callback.answer("Режим изменен!")
        await callback.message.edit_text(
            f"Готово! Теперь режим: <b>{PERSONAS[new_mode]['name']}</b> 🛠",
            parse_mode="HTML"
        )

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
                text_content = "Опиши, что изображено на этой картинке, и прокомментируй её."
        except Exception as e:
            logging.error(f"Ошибка загрузки фото: {e}")

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

    try:
        chosen_emoji = parse_requested_emoji(text_content)
        if not chosen_emoji:
            chosen_emoji = "🔥" if message.photo else random.choice(["👍", "🔥", "⚡️", "❤️", "🗿"])

        target_message_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=target_message_id,
            reaction=[types.ReactionTypeEmoji(emoji=chosen_emoji)]
        )
    except Exception as e:
        logging.error(f"Ошибка реакций: {e}")

    if chat_id not in chat_history:
        chat_history[chat_id] = []
    
    current_mode = chat_modes.get(chat_id, "geek")
    current_system_instruction = PERSONAS[current_mode]["instruction"]

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
    if len(chat_history[chat_id]) > 10:
        chat_history[chat_id] = chat_history[chat_id][-10:]

    messages_payload = [{"role": "system", "content": current_system_instruction}]
    messages_payload.extend(chat_history[chat_id])

    if not client:
        await message.reply("Ошибка: GROQ_API_KEY не задан!")
        return

    loop = asyncio.get_running_loop()
    reply_text = None
    last_error = None

    for model_name in CANDIDATE_MODELS:
        try:
            response = await loop.run_in_executor(
                None,
                lambda m=model_name: client.chat.completions.create(
                    model=m,
                    messages=messages_payload,
                    max_tokens=1000
                )
            )
            reply_text = response.choices[0].message.content
            if reply_text:
                break
        except Exception as e:
            last_error = e
            continue

    if reply_text:
        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        
        processed_text = clean_text_for_telegram(reply_text)

        try:
            await message.reply(processed_text, parse_mode="HTML")
        except Exception:
            try:
                await message.reply(html.escape(processed_text), parse_mode="HTML")
            except Exception:
                await message.reply(reply_text)
    else:
        await message.reply(f"⚠️ Ошибка API:\n<code>{last_error}</code>", parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
