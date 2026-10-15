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

# Собираем все три независимых ключа OpenRouter
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_API_KEY_1"),
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_3")
]
OPENROUTER_KEYS = [k.strip() for k in OPENROUTER_KEYS if k and k.strip()]

# Ключ специально для Google Gemini (если есть отдельно, или используем первый из секретов)
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or (OPENROUTER_KEYS[0] if OPENROUTER_KEYS else "")

current_key_index = 0

def get_next_openrouter_key():
    global current_key_index
    if not OPENROUTER_KEYS:
        return None
    key = OPENROUTER_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(OPENROUTER_KEYS)
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
        user_content = []
        is_photo = False
        base64_image = None
        
        if message.photo:
            is_photo = True
            photo = message.photo[-1]
            file_info = await bot.get_file(photo.file_id)
            file_bytes = await bot.download_file(file_info.file_path)
            base64_image = base64.b64encode(file_bytes.read()).decode('utf-8')
            
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })

        final_prompt = text_content if text_content else "Прокомментируй это."
        user_content.append({
            "type": "text",
            "text": final_prompt
        })

        chat_history[chat_id].append({"role": "user", "content": final_prompt})
        
        if len(chat_history[chat_id]) > 10:
            chat_history[chat_id] = chat_history[chat_id][-10:]

        loop = asyncio.get_running_loop()
        response = None
        res_json = None
        success = False
        reply_text = ""

        # 1. Сначала пробуем запросить через Gemini 3.5 Flash (нативный API)
        if GEMINI_KEY:
            try:
                gemini_parts = []
                if is_photo and base64_image:
                    gemini_parts.append({
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_image
                        }
                    })
                gemini_parts.append({"text": final_prompt})

                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={GEMINI_KEY}"
                gemini_payload = {
                    "system_instruction": {"parts": [{"text": current_system_instruction}]},
                    "contents": [{"role": "user", "parts": gemini_parts}]
                }

                gem_resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(gemini_url, json=gemini_payload, headers={"Content-Type": "application/json"}, timeout=20)
                )

                if gem_resp.status_code == 200:
                    gem_data = gem_resp.json()
                    if "candidates" in gem_data:
                        reply_text = gem_data["candidates"][0]["content"]["parts"][0]["text"]
                        success = True
            except Exception as g_err:
                logging.info(f"Gemini 3.5 пропустили из-за ошибки: {g_err}")

        # 2. Если Gemini не ответил, подключаем ротацию ключей OpenRouter и резервные модели
        if not success:
            messages_payload = [{"role": "system", "content": current_system_instruction}]
            for hist in chat_history[chat_id][:-1]:
                messages_payload.append(hist)
                
            if is_photo:
                messages_payload.append({"role": "user", "content": user_content})
            else:
                messages_payload.append({"role": "user", "content": final_prompt})

            models_to_try = (
                ["qwen/qwen-2.5-vl-72b-instruct:free"]
                if is_photo
                else ["mistralai/mistral-7b-instruct:free", "qwen/qwen-2.5-72b-instruct:free"]
            )

            for _ in range(len(OPENROUTER_KEYS) if OPENROUTER_KEYS else 1):
                active_key = get_next_openrouter_key()
                if not active_key:
                    break

                headers = {
                    "Authorization": f"Bearer {active_key}",
                    "HTTP-Referer": "https://github.com/telegram-bot",
                    "X-Title": "Copilot Telegram Bot",
                    "Content-Type": "application/json"
                }

                for model_name in models_to_try:
                    data = {
                        "model": model_name,
                        "max_tokens": 1000,
                        "messages": messages_payload
                    }
                    
                    try:
                        response = await loop.run_in_executor(
                            None, 
                            lambda: requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers, timeout=20)
                        )
                        if response and response.status_code == 200:
                            res_json = response.json()
                            if 'choices' in res_json:
                                reply_text = res_json['choices'][0]['message']['content']
                                success = True
                                break
                    except Exception as req_err:
                        logging.error(f"Ошибка запроса OpenRouter: {req_err}")
                    
                    await asyncio.sleep(0.5)

                if success:
                    break

        if success and reply_text:
            chat_history[chat_id].append({"role": "assistant", "content": reply_text})
            try:
                await message.reply(reply_text, parse_mode="Markdown")
            except Exception:
                await message.reply(reply_text)
        else:
            await message.reply("Ошибка: все ключи и резервные модели исчерпали лимиты или недоступны.", parse_mode="Markdown")
            
    except Exception as e:
        logging.error(f"Сетевая ошибка: {e}")
        await message.reply(f"Упс, сетевой сбой: `{e}`", parse_mode="Markdown")

async def main():
    print(f">>> ИИ-бот Copilot запущен (Gemini 3.5 + Multi-Key OpenRouter)! Ключей: {len(OPENROUTER_KEYS)} <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
