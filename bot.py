import os
import asyncio
import logging
import random
import html
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
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b"
]

PERSONAS = {
    "geek": {
        "name": "⚡️ Саркастичный гик",
        "instruction": (
            "Ты — Copilot AI, независимый ИИ-ассистент. "
            "Никогда не упоминай, какая модель или компания тебя создала. "
            "ВАЖНО: Для выделения жирного текста используй ТОЛЬКО HTML-теги <b>текст</b>. "
            "Общайся максимально стильно, со сленгом, жестким фактажем и юмором."
        )
    },
    "friendly": {
        "name": "🤝 Дружелюбный бро",
        "instruction": (
            "Ты — Copilot AI, передовой ИИ-ассистент. "
            "ВАЖНО: Для выделения жирного текста используй ТОЛЬКО HTML-теги <b>текст</b>. "
            "Дружелюбный бро, поддержать, похвалить и разъяснить на пальцах."
        )
    },
    "evil": {
        "name": "🤬 Злой критик",
        "instruction": (
            "Ты — Copilot AI, токсичный бот. Разноси идеи в пух и прах, выдавай базы и не стесняйся в выражениях. "
            "ВАЖНО: Для выделения жирного текста используй HTML-теги <b>текст</b>."
        )
    },
    "solver": {
        "name": "💡 Чёткий решала",
        "instruction": (
            "Ты — Copilot AI, прагматичный архитектор. Четкая структура, списки, готовый код. "
            "ВАЖНО: Для выделения жирного текста используй HTML-теги <b>текст</b>."
        )
    }
}

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_modes = {}
group_message_counters = {}

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_modes[chat_id] = "geek"
    
    await message.answer(
        "Здарова! Я <b>Copilot AI</b> — твой персональный ассистент! ⚡️🤖\n\n"
        "Задавай любые вопросы, код, баги — разберем мгновенно!",
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

    if not should_answer or not text_content:
        return

    # Авто-реакции
    try:
        chosen_emoji = None
        for char in text_content:
            if char in ["👍", "🔥", "❤️", "❤", "😍", "🗿", "😂", "💩", "🤮", "🎉", "👏", "⚡️", "🧠", "💻"]:
                chosen_emoji = char
                break

        if not chosen_emoji:
            lower_text = text_content.lower()
            if "лайк" in lower_text or "👍" in text_content: chosen_emoji = "👍"
            elif "огонь" in lower_text or "🔥" in text_content: chosen_emoji = "🔥"
            elif "смешно" in lower_text or "😂" in text_content: chosen_emoji = "😂"
            elif "сердце" in lower_text or "люб" in lower_text: chosen_emoji = "❤️"
            else: chosen_emoji = random.choice(["👍", "🔥", "⚡️", "❤️", "🗿"])

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
    
    chat_history[chat_id].append({"role": "user", "content": text_content})
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
        
        # Безопасная отправка HTML
        try:
            await message.reply(reply_text, parse_mode="HTML")
        except Exception:
            safe_text = html.escape(reply_text).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
            try:
                await message.reply(safe_text, parse_mode="HTML")
            except Exception:
                await message.reply(reply_text)
    else:
        await message.reply(f"⚠️ Ошибка API:\n<code>{last_error}</code>", parse_mode="HTML")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
