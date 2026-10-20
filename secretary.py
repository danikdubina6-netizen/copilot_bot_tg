import os
import telebot
from openai import OpenAI

# Получаем ключи из секретов GitHub
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

# Клиент Groq для генерации ответов через ИИ
ai_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

SYSTEM_PROMPT = """
Ты — вежливый и умный ИИ-секретарь. Отвечай кратко, вежливо и по делу на сообщения пользователей.
"""

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_text = message.text or "[Медиа или файл]"
    
    try:
        response = ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=300
        )
        ai_reply = response.choices[0].message.content
        bot.reply_to(message, f"🤖 [ИИ-Секретарь]: {ai_reply}")
    except Exception as e:
        print(f"Ошибка ИИ: {e}")

if __name__ == "__main__":
    print("Бот-секретарь запущен...")
    bot.infinity_polling()
    
