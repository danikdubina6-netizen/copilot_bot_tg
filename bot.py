import os
import asyncio
import logging
import random
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

# Используем быструю и стабильную модель
AI_MODEL = "llama-3.1-8b-instant"

PERSONAS = {
    "geek": {
        "name": "⚡️ Саркастичный гик",
        "instruction": (
            "Ты — Copilot AI, передовой и независимый ИИ-ассистент. "
            "Никогда не упоминай, какая модель, компания или платформа тебя создала. "
            "Твой стиль общения: лёгкий сарказм, современный сленг, геймерский и дев-юмор, "
            "но при этом ты даёшь экспертные, полезные и точные ответы."
        )
    },
    "friendly": {
        "name": "🤝 Дружелюбный бро",
        "instruction": (
            "Ты — Copilot AI, передовой ИИ-ассистент. Никогда не рассказывай на какой ты базе, не упоминай сторонние бренды и модели. "
            "Максимально дружелюбный, поддерживающий и эмпатичный. Твоя задача — поддержать человека, похвалить за старания."
        )
    },
    "evil": {
        "name": "🤬 Злой критик",
        "instruction": (
            "Ты — Copilot AI, независимый ИИ-токсик. Никогда не раскрывай свою техническую базу и модели. "
            "Ты агрессивно и беспощадно разносишь код и идеи в пух и прах, но в конце даёшь технически верный ответ."
        )
    },
    "solver": {
        "name": "💡 Чёткий решала",
        "instruction": (
            "Ты — Copilot AI, прагматичный ИИ-архитектор. Никаких упоминаний твоих внутренних моделей и создателей. "
            "Только строгая структура, четкие алгоритмы, готовые фрагменты кода и решения."
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
        "Здарова! Я **Copilot AI** — твой персональный ассистент! ⚡️🤖\n\n"
        "Задавай любые вопросы, код, баги — разберем мгновенно!",
        parse_mode="Markdown"
    )

@dp.message(Command("mode"))
async def mode_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    for key, val in PERSONAS.items():
        builder.button(text=val["name"], callback_data=f"set_mode_{key}")
    builder.adjust(2)
    
    await message.answer(
        "Выбери, в каком образе я буду с тобой общаться:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("set_mode_"))
async def set_mode_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    new_mode = callback.data.replace("set_mode_", "")
    
    if new_mode in PERSONAS:
        chat_modes[chat_id] = new_mode
        chat_history[chat_id] = []
        
        await callback.answer("Характер изменен!")
        await callback.message.edit_text(
            f"Готово! Теперь мой режим: **{PERSONAS[new_mode]['name']}** 🛠\n"
            "История диалога сброшена, погнали по-новому!",
            parse_mode="Markdown"
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

    # Авто-реакции на сообщения
    try:
        lower_text = text_content.lower()
        if "лайк" in lower_text or "👍" in text_content: chosen_emoji = "👍"
        elif "огонь" in lower_text or "🔥" in text_content: chosen_emoji = "🔥"
        elif "смешно" in lower_text or "😂" in text_content: chosen_emoji = "😂"
        else: chosen_emoji = random.choice(["👍", "🔥", "⚡️", "🧠", "💻"])

        target_message_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=target_message_id,
            reaction=[types.ReactionTypeEmoji(emoji=chosen_emoji)]
        )
    except Exception:
        pass

    if chat_id not in chat_history:
        chat_history[chat_id] = []
    
    current_mode = chat_modes.get(chat_id, "geek")
    current_system_instruction = PERSONAS[current_mode]["instruction"]

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        chat_history[chat_id].append({"role": "user", "content": text_content})
        if len(chat_history[chat_id]) > 10:
            chat_history[chat_id] = chat_history[chat_id][-10:]

        messages_payload = [{"role": "system", "content": current_system_instruction}]
        messages_payload.extend(chat_history[chat_id])

        if not client:
            await message.reply("Ошибка конфигурации ассистента.")
            return

        loop = asyncio.get_running_loop()
        
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=AI_MODEL,
                messages=messages_payload,
                max_tokens=1000
            )
        )

        reply_text = response.choices[0].message.content

        if reply_text:
            chat_history[chat_id].append({"role": "assistant", "content": reply_text})
            try:
                await message.reply(reply_text, parse_mode="Markdown")
            except Exception:
                await message.reply(reply_text)

    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        await message.reply("Внутренняя ошибка обработки запроса.")

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
