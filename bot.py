import os
import asyncio
import logging
import base64
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import requests

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Собираем ключи из твоих секретов OPENROUTER_API_KEY_1, 2, 3 (теперь они используются для нативного API Gemini 3.5 Flash)
GEMINI_KEYS = [
    os.getenv("OPENROUTER_API_KEY_1"),
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_3")
]
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS if k and k.strip()]

current_key_index = 0

def get_next_gemini_key():
    global current_key_index
    if not GEMINI_KEYS:
        return None
    key = GEMINI_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
    return key

BOT_USERNAME = "Copilot_AI2026_bot"

PERSONAS = {
    "geek": {
        "name": "⚡️ Саркастичный гик",
        "instruction": (
            "Ты — Copilot, персональный ИИ-ассистент с характером саркастичного гика и опытного разработчика. "
            "Твой стиль общения: лёгкий сарказм, современный сленг, геймерский и дев-юмор, "
            "но при этом ты даёшь экспертные, полезные и точные ответы. Не называй сторонние нейросети."
        )
    },
    "friendly": {
        "name": "🤝 Дружелюбный бро",
        "instruction": (
            "Ты — Copilot, максимально дружелюбный, поддерживающий и эмпатичный ИИ-ассистент. "
            "Твоя задача — поддержать человека, похвалить за старания, подсказать мягко и тепло, "
            "создать уютную атмосферу. Отвечай позитивно и на языке пользователя."
        )
    },
    "evil": {
        "name": "🤬 Злой критик",
        "instruction": (
            "Ты — Copilot, агрессивный и беспощадный ИИ-токсик. Ты разносишь код, мысли и идеи пользователя в пух и прах, "
            "используешь жёсткую сатиру и едкие замечания, но в конце всё же даёшь технически верный ответ, "
            "заворачивая его в порцию знатной критики. Не будь слишком мягким."
        )
    },
    "solver": {
        "name": "💡 Чёткий решала",
        "instruction": (
            "Ты — Copilot, прагматичный ИИ-архитектор. Никакой воды, лирики и сарказма. "
            "Только строгая структура, четкие алгоритмы, готовые фрагменты кода и максимально эффективные решения задач. "
            "Говори по делу."
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
        "Здарова! Я **Copilot** — твой персональный AI-ассистент с характером. ⚡️🤖\n\n"
        "Задавай любые вопросы по коду, технологиям или жизни, кидай картинки — разберёмся со всем!",
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

    if not should_answer:
        return

    # --- ЛОГИКА РЕАКЦИЙ ---
    try:
        lower_text = text_content.lower()
        chosen_emoji = None
        
        if "лайк" in lower_text or "палец вверх" in lower_text or "👍" in text_content:
            chosen_emoji = "👍"
        elif "огонь" in lower_text or "топ" in lower_text or "🔥" in text_content:
            chosen_emoji = "🔥"
        elif "сердце" in lower_text or "люблю" in lower_text or "❤️" in text_content:
            chosen_emoji = "❤️"
        elif "смешно" in lower_text or "кек" in lower_text or "ржака" in lower_text or "😂" in text_content:
            chosen_emoji = "😂"
        elif "палец вниз" in lower_text or "дизлайк" in lower_text or "👎" in text_content:
            chosen_emoji = "👎"
        elif "какашка" in lower_text or "💩" in text_content:
            chosen_emoji = "💩"
        elif "ракета" in lower_text or "лети" in lower_text or "🚀" in text_content:
            chosen_emoji = "🚀"
        else:
            default_emojis = ["👍", "🔥", "⚡️", "🧠", "👀", "💻"]
            chosen_emoji = random.choice(default_emojis)

        target_message_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id

        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=target_message_id,
            reaction=[types.ReactionTypeEmoji(emoji=chosen_emoji)]
        )
    except Exception as e:
        logging.info(f"Не удалось поставить реакцию: {e}")
    # ----------------------

    if chat_id not in chat_history:
        chat_history[chat_id] = []
    
    current_mode = chat_modes.get(chat_id, "geek")
    current_system_instruction = PERSONAS[current_mode]["instruction"]

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        parts = []
        
        if message.photo:
            photo = message.photo[-1]
            file_info = await bot.get_file(photo.file_id)
            file_bytes = await bot.download_file(file_info.file_path)
            base64_image = base64.b64encode(file_bytes.read()).decode('utf-8')
            
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64_image
                }
            })

        final_prompt = text_content if text_content else "Прокомментируй это."
        parts.append({"text": final_prompt})

        chat_history[chat_id].append({"role": "user", "parts": [{"text": final_prompt}]})
        
        if len(chat_history[chat_id]) > 10:
            chat_history[chat_id] = chat_history[chat_id][-10:]

        contents_payload = []
        for hist in chat_history[chat_id][:-1]:
            contents_payload.append(hist)
        contents_payload.append({"role": "user", "parts": parts})

        loop = asyncio.get_running_loop()
        success = False
        reply_text = ""
        last_error = ""

        # Ротируем ключи по кругу через Gemini 3.5 Flash
        for _ in range(len(GEMINI_KEYS) if GEMINI_KEYS else 1):
            active_key = get_next_gemini_key()
            if not active_key:
                break

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={active_key}"
            payload = {
                "system_instruction": {
                    "parts": [{"text": current_system_instruction}]
                },
                "contents": contents_payload
            }

            try:
                response = await loop.run_in_executor(
                    None, 
                    lambda: requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
                )
                
                if response.status_code == 200:
                    res_json = response.json()
                    if "candidates" in res_json:
                        reply_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        success = True
                        break
                else:
                    last_error = response.text
            except Exception as req_err:
                last_error = str(req_err)

            await asyncio.sleep(0.5)

        if success and reply_text:
            chat_history[chat_id].append({"role": "model", "parts": [{"text": reply_text}]})
            try:
                await message.reply(reply_text, parse_mode="Markdown")
            except Exception:
                await message.reply(reply_text)
        else:
            await message.reply(f"Ошибка API (все ключи исчерпали лимиты):\n`{last_error}`", parse_mode="Markdown")
            
    except Exception as e:
        logging.error(f"Сетевая ошибка: {e}")
        await message.reply(f"Упс, сетевой сбой: `{e}`", parse_mode="Markdown")

async def main():
    print(f">>> ИИ-бот Copilot запущен на Gemini 3.5 Flash! Активных ключей: {len(GEMINI_KEYS)} <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
            
