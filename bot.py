import os
import asyncio
import logging
import base64
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import requests

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

BOT_USERNAME = "Copilot_AI2026_bot"

SYSTEM_INSTRUCTION = (
    "Ты — Copilot, персональный ИИ-ассистент с характером саркастичного гика и опытного разработчика. "
    "Твой стиль общения: лёгкий сарказм, современный сленг, геймерский и дев-юмор, "
    "но при этом ты даёшь экспертные, полезные и точные ответы. "
    "Не называй никакие сторонние нейросети или компании, ты просто Copilot. "
    "Отвечай на языке пользователя."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Словарь для хранения истории диалогов: {chat_id: [messages]}
chat_history = {}

# Словарь для подсчета сообщений в группах: {chat_id: count_int}
group_message_counters = {}

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_history[message.chat.id] = []
    await message.answer(
        "Здарова! Я **Copilot** — твой персональный AI-ассистент с характером. ⚡️🤖\n\n"
        "Задавай любые вопросы по коду, технологиям или жизни, кидай картинки — разберёмся со всем!",
        parse_mode="Markdown"
    )

@dp.message()
async def handle_ai_response(message: types.Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    text_content = message.text or message.caption or ""
    should_answer = False

    # 1. В личных сообщениях отвечаем всегда
    if chat_type == "private":
        should_answer = True
    else:
        # 2. Проверяем триггеры для групп / супергрупп
        
        # Триггер А: ответили (реплай) на сообщение именно нашего бота
        if message.reply_to_message and message.reply_to_message.from_user:
            # Узнаем ID нашего бота через мемоизированный вызов или сравниваем с bot.id
            bot_user = await bot.get_me()
            if message.reply_to_message.from_user.id == bot_user.id:
                should_answer = True

        # Триггер Б: упомянули юзернейм бота в тексте
        if f"@{BOT_USERNAME}".lower() in text_content.lower():
            should_answer = True
            text_content = text_content.replace(f"@{BOT_USERNAME}", "").strip()

        # Триггер В: сработал счетчик каждых 15 сообщений (если еще не триггернули реплаем/упоминанием)
        if not should_answer:
            if chat_id not in group_message_counters:
                group_message_counters[chat_id] = 0
            
            group_message_counters[chat_id] += 1
            
            if group_message_counters[chat_id] >= 15:
                group_message_counters[chat_id] = 0
                should_answer = True

    # Если ни одно условие не сошлось — молчим
    if not should_answer:
        return

    if chat_id not in chat_history:
        chat_history[chat_id] = []

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        user_content = []
        
        # Проверяем фото
        if message.photo:
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

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/telegram-bot",
            "X-Title": "Copilot Telegram Bot",
            "Content-Type": "application/json"
        }
        
        messages_payload = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        for hist in chat_history[chat_id][:-1]:
            messages_payload.append(hist)
            
        messages_payload.append({"role": "user", "content": user_content})

        data = {
            "model": "google/gemini-2.5-flash", 
            "max_tokens": 1000,
            "messages": messages_payload
        }
        
        loop = asyncio.get_running_loop()
        
        response = None
        for attempt in range(3):
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers, timeout=30)
            )
            if response.status_code != 429:
                break
            await asyncio.sleep(2)
        
        try:
            res_json = response.json()
        except Exception:
            res_json = None

        if response.status_code == 200 and res_json:
            reply_text = res_json['choices'][0]['message']['content']
            chat_history[chat_id].append({"role": "assistant", "content": reply_text})
            
            try:
                await message.reply(reply_text, parse_mode="Markdown")
            except Exception:
                await message.reply(reply_text)
        else:
            if isinstance(res_json, dict) and 'error' in res_json:
                error_data = res_json['error']
                error_text = error_data.get('message', str(error_data)) if isinstance(error_data, dict) else str(error_data)
            else:
                error_text = response.text if response.text else f"Status code: {response.status_code}"
                
            await message.reply(f"Ошибка OpenRouter (`{response.status_code}`):\n`{error_text}`", parse_mode="Markdown")
            
    except Exception as e:
        logging.error(f"Сетевая ошибка: {e}")
        await message.reply(f"Упс, сетевой сбой: `{e}`", parse_mode="Markdown")

async def main():
    print(">>> ИИ-бот Copilot (Groups + Replies + Mentions + Counter) успешно запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
