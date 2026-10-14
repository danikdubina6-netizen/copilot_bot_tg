import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from groq import AsyncGroq

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Инициализируем Groq
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

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
        # Отправляем запрос в Groq к быстрой модели Llama-3.3-70b
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": message.text}
            ]
        )
        reply_text = response.choices[0].message.content
        await message.reply(reply_text)
        
    except Exception as e:
        logging.error(f"Ошибка Groq API: {e}")
        await message.reply(f"Упс, произошёл сбой: `{e}`", parse_mode="Markdown")

async def main():
    print(">>> ИИ-бот Copilot успешно запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
