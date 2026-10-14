import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from openai import AsyncOpenAI

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Получаем токены из GitHub Secrets
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

# Настраиваем клиента xAI (Grok API полностью совместим с OpenAI SDK)
grok_client = AsyncOpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

# Промпт характера бота "Copilot"
SYSTEM_INSTRUCTION = (
    "Ты — Copilot, ИИ-ассистент с характером саркастичного гика, крипто-энтузиаста и опытного разработчика. "
    "Ты идеально шаришь в коде, технологиях, играх и мемах. "
    "Твой стиль: умный рофл, лёгкая ирония, использование сленга, но при этом ты ДАЁШЬ четкие, "
    "полезные и точные технические ответы. Не занудствуй и отвечай на языке пользователя."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Здарова! Я **Copilot** (теперь на базе **Grok**) — твой персональный AI-ассистент с характером. ⚡️🤖\n\n"
        "Задавай любые вопросы по коду, технологиям или жизни. Только без банальщины!",
        parse_mode="Markdown"
    )

@dp.message()
async def handle_ai_response(message: types.Message):
    # Показываем статус «печатает...»
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        # Запрос к Grok API
        response = await grok_client.chat.completions.create(
            model="grok-beta",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": message.text}
            ]
        )
        reply_text = response.choices[0].message.content
        await message.reply(reply_text)
        
    except Exception as e:
        logging.error(f"Ошибка Grok API: {e}")
        await message.reply("Упс, у Grok подгорели процессоры... Попробуй отправить запрос ещё раз.")

async def main():
    print(">>> ИИ-бот Copilot (Grok edition) успешно запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
  
