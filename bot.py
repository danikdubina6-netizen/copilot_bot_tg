import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import requests

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

SYSTEM_INSTRUCTION = (
    "Ты — Copilot, персональный ИИ-ассистент с характером саркастичного гика и опытного разработчика. "
    "Твой стиль общения: лёгкий сарказм, современный сленг, геймерский и дев-юмор, "
    "но при этом ты даёшь экспертные, полезные и точные ответы. "
    "Не называй никакие сторонние нейросети или компании, ты просто Copilot. "
    "Отвечай на языке пользователя."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Здарова! Я **Copilot** — твой персональный AI-ассистент с характером. ⚡️🤖\n\n"
        "Задавай любые вопросы по коду, технологиям или жизни. Только без банальщины!",
        parse_mode="Markdown"
    )

@dp.message()
async def handle_ai_response(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/telegram-bot", # Обязательно для OpenRouter
            "X-Title": "Copilot Telegram Bot",                # Название твоего приложения
            "Content-Type": "application/json"
        }
        data = {
            # Используем отличную бесплатную модель на OpenRouter
            "model": "google/gemini-2.5-flash", 
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": message.text}
            ]
        }
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers, timeout=20)
        )
        
        try:
            res_json = response.json()
        except Exception:
            res_json = None

        if response.status_code == 200 and res_json:
            reply_text = res_json['choices'][0]['message']['content']
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
    print(">>> ИИ-бот Copilot (OpenRouter) успешно запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
