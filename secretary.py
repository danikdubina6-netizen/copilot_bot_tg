import os
import asyncio
import logging
import html
from pyrogram import Client, filters
from pyrogram.types import Message
from openai import OpenAI

logging.basicConfig(level=logging.INFO)

# Получаем данные из переменных окружения
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

groq_client = None
if GROQ_API_KEY:
    groq_client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY
    )

# Инициализация Pyrogram юзербота (сессия сохранится в файл my_secretary.session)
app = Client(
    "my_secretary",
    api_id=API_ID,
    api_hash=API_HASH
)

# Память для диалогов секретаря
secretary_history = {}

SECRETARY_INSTRUCTION = (
    "Ты — умный ИИ-секретарь Матвея. Хозяина сейчас нет в сети (AFK). "
    "Твоя задача — вежливо, сдержанно и емко отвечать собеседнику в личных сообщениях от лица секретаря. "
    "Передавай суть, отвечай на вопросы по делу, не пиши слишком длинно, чтобы текст помещался на экран смартфона. "
    "Язык: исключительно русский."
)

@app.on_message(filters.private & ~filters.me & ~filters.bot)
async def handle_afk_dm(client: Client, message: Message):
    chat_id = message.chat.id
    user_text = message.text or message.caption
    
    if not user_text or not groq_client:
        return

    try:
        # Проверяем статус владельца аккаунта (тебя) через get_me() или общие чаты, 
        # но проще проверить статус текущего юзера: если ты онлайн, бот молчит.
        me = await client.get_me()
        # В Pyrogram статус 'online' означает, что владелец в сети
        if me.status and str(me.status).lower() == "userstatus.online":
            return  # Хозяин в сети — секретарь молчит
    except Exception as e:
        logging.warning(f"Не удалось проверить статус: {e}")

    # Если тебя нет в сети — секретарь берет трубку
    logging.info(f"🤖 Секретарь отвечает в ЛС для {chat_id}: {user_text}")

    if chat_id not in secretary_history:
        secretary_history[chat_id] = []

    secretary_history[chat_id].append({"role": "user", "content": user_text})
    if len(secretary_history[chat_id]) > 6:
        secretary_history[chat_id] = secretary_history[chat_id][-6:]

    messages_payload = [{"role": "system", "content": SECRETARY_INSTRUCTION}] + secretary_history[chat_id]

    try:
        response = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="qwen/qwen3.8-27b",
            messages=messages_payload,
            max_tokens=400
        )
        
        reply_text = response.choices[0].message.content if response.choices else "Хозяин отошел, передам ему сообщение позже."
    except Exception as e:
        logging.error(f"Ошибка ИИ-секретаря: {e}")
        reply_text = "В данный момент я занят другими делами, отвечу позже."

    secretary_history[chat_id].append({"role": "assistant", "content": reply_text})
    
    # Отправляем ответ в ЛС от твоего имени (как секретарь)
    await message.reply(f"🤖 <i>[Авто-секретарь]:</i> {html.escape(reply_text)}", parse_mode="HTML")

if __name__ == "__main__":
    print(">>> ИИ-Секретарь запущен и ждет сообщения в ЛС! <<<")
    app.run()
      
