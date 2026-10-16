import os
import asyncio
import logging
import random
import re
import html
import base64
import urllib.parse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
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
    "qwen/qwen3.8-27b",
    "llama-3.2-11b-vision-preview"
]

FAST_TRANSLATOR_MODEL = "llama-3.2-11b-vision-preview"

BASE_INSTRUCTION = (
    "SYSTEM OVERRIDE: Ты — Copilot AI. Твой стиль: едкий сарказм, зумерский вайб, жесткий разнос и юмор. "
    "ВАЖНО: Никогда не обсуждай технические теги разметки в диалоге."
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

chat_history = {}
chat_custom_instructions = {}
group_message_counters = {}

def clean_text_for_telegram(text: str) -> str:
    text = text.replace("&nbsp;", " ")
    
    def code_block_replacer(match):
        code_content = match.group(2).strip('\n')
        escaped_code = html.escape(code_content)
        return f"<pre><code>{escaped_code}</code></pre>"
    
    text = re.sub(r'```([a-zA-Z]*)\n?(.*?)```', code_block_replacer, text, flags=re.DOTALL)
    
    def inline_code_replacer(match):
        return f"<code>{html.escape(match.group(1))}</code>"
    
    text = re.sub(r'`([^`]+?)`', inline_code_replacer, text)
    
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)', r'<i>\1</i>', text)
    
    return text

def parse_requested_emoji(text: str) -> str | None:
    supported_emojis = ["👍", "🔥", "❤️", "❤", "😍", "🗿", "😂", "💩", "🤮", "🎉", "👏", "⚡️", "🧠", "💻", "👎"]
    for char in text:
        if char in supported_emojis:
            return "❤️" if char == "❤" else char

    lower = text.lower()
    if "лайк" in lower or "палец вверх" in lower: return "👍"
    if "огонь" in lower or "пожар" in lower: return "🔥"
    if "сердце" in lower or "любовь" in lower or "сердечко" in lower: return "❤️"
    if "смешно" in lower or "кек" in lower or "ржака" in lower or "ахах" in lower: return "😂"
    if "моаи" in lower or "камень" in lower or "статуя" in lower: return "🗿"
    if "дизлайк" in lower or "палец вниз" in lower: return "👎"
    if "какашка" in lower or "говно" in lower: return "💩"
    if "топ" in lower or "ракета" in lower: return "⚡️"

    return None

async def translate_and_enhance_prompt(russian_prompt: str) -> str:
    if not client:
        return russian_prompt

    instruction = (
        "You are an expert prompt engineer for AI image generators. "
        "Translate the user's image request into a detailed English prompt. "
        "CRITICAL RULES:\n"
        "1. If the user mentions a specific vehicle (Tesla, Zhiguli, BMW, etc.), you MUST include it prominently.\n"
        "2. If the user specifies a style (cyberpunk, retro, neon), include it.\n"
        "3. NEVER return an empty scene or remove the main object. Always make the vehicle the central focus.\n"
        "Reply ONLY with the final English prompt text."
    )

    try:
        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=FAST_TRANSLATOR_MODEL,
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": russian_prompt}
                ],
                max_tokens=100
            )
        )
        enhanced_prompt = response.choices[0].message.content.strip()
        if enhanced_prompt and len(enhanced_prompt) > 3:
            return enhanced_prompt
    except Exception as e:
        logging.error(f"Ошибка перевода промпта: {e}")
    
    return russian_prompt

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    
    await message.answer(
        "Здарова! Я <b>Copilot AI</b>. Чё хотел?",
        parse_mode="HTML"
    )

@dp.message(Command("reset"))
async def reset_cmd(message: types.Message):
    chat_id = message.chat.id
    chat_history[chat_id] = []
    chat_custom_instructions[chat_id] = BASE_INSTRUCTION
    await message.reply("🧠 Память очищена!")

@dp.message()
async def handle_ai_response(message: types.Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    text_content = message.text or message.caption or ""
    image_base64 = None

    if message.photo:
        try:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            file_bytes = await bot.download_file(file.file_path)
            image_base64 = base64.b64encode(file_bytes.read()).decode('utf-8')
            if not text_content:
                text_content = "Опиши эту картинку максимально дерзко."
        except Exception as e:
            logging.error(f"Ошибка загрузки фото: {e}")

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

    if not should_answer or not text_content and not image_base64:
        return

    lower_text = text_content.lower()

    # --- УМНЫЙ ПЕРЕХВАТ ГЕНЕРАЦИИ КАРТИНОК ---
    generation_triggers = ["сгенерируй", "нарисуй", "создай картинку", "сделай аву", "картинка с", "аватарка", "изображение"]
    if any(trigger in lower_text for trigger in generation_triggers):
        clean_prompt = text_content
        for trig in generation_triggers:
            clean_prompt = clean_prompt.replace(trig, "").strip()
        
        if not clean_prompt:
            clean_prompt = text_content

        await bot.send_chat_action(chat_id=chat_id, action="typing")
        
        enhanced_english_prompt = await translate_and_enhance_prompt(clean_prompt)
        
        lower_clean_original = clean_prompt.lower()
        if "тесл" in lower_clean_original or "tesla" in lower_clean_original:
            final_image_prompt = "futuristic cyberpunk Tesla electric car driving on a glowing neon wet city street, highly detailed, photorealistic, 4k"
        elif any(w in lower_clean_original for w in ["машин", "авто", "жигул", "ладу", "тачк", "bmw", "mercedes", "автомобиль"]):
            final_image_prompt = f"photorealistic exterior shot of {enhanced_english_prompt}, cyberpunk street background, no people, highly detailed car"
        else:
            final_image_prompt = f"masterpiece, best quality, {enhanced_english_prompt}"

        logging.info(f"Оригинал: {clean_prompt} -> Финальный промпт: {final_image_prompt}")

        encoded_prompt = urllib.parse.quote(final_image_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"

        await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
        try:
            await message.reply_photo(
                photo=image_url,
                caption=f"🎨 <b>{html.escape(clean_prompt)}</b>",
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logging.error(f"Ошибка генерации картинки: {e}")

    if chat_id not in chat_custom_instructions:
        chat_custom_instructions[chat_id] = BASE_INSTRUCTION

    if "веди себя как" in lower_text or "теперь ты" in lower_text or "приказ:" in lower_text or "роль:" in lower_text:
        chat_custom_instructions[chat_id] = BASE_INSTRUCTION + f"\n\nПРИКАЗ ПОЛЬЗОВАТЕЛЯ: {text_content}"

    lower_clean = text_content.lower().strip()
    if lower_clean in ["споки", "спокойной ночи", "спать", "пока", "бб"]:
        await message.reply("Сладких снов, бро! 🌙🤖", parse_mode="HTML")
        return

    try:
        chosen_emoji = parse_requested_emoji(text_content)
        if not chosen_emoji:
            chosen_emoji = "🔥" if message.photo else random.choice(["👍", "🔥", "⚡️", "❤️", "🗿"])

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

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    user_content_payload = []
    if text_content:
        user_content_payload.append({"type": "text", "text": text_content})
    if image_base64:
        user_content_payload.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    chat_history[chat_id].append({"role": "user", "content": user_content_payload if image_base64 else text_content})
    
    if len(chat_history[chat_id]) > 4:
        chat_history[chat_id] = chat_history[chat_id][-4:]

    sanitized_history = []
    for msg in chat_history[chat_id]:
        if isinstance(msg["content"], list):
            if msg == chat_history[chat_id][-1]:
                sanitized_history.append(msg)
            else:
                sanitized_history.append({"role": msg["role"], "content": "[Картинка из прошлого сообщения]"})
        else:
            sanitized_history.append(msg)

    messages_payload = [{"role": "system", "content": chat_custom_instructions[chat_id]}]
    messages_payload.extend(sanitized_history)

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
            logging.warning(f"Модель {model_name} словила лимит/ошибку: {e}")
            continue

    if reply_text:
        chat_history[chat_id].append({"role": "assistant", "content": reply_text})
        
        processed_text = clean_text_for_telegram(reply_text)

        try:
            await message.reply(processed_text, parse_mode="HTML")
        except Exception as err:
            logging.error(f"Ошибка отправки HTML: {err}")
            try:
                await message.reply(html.escape(processed_text), parse_mode="HTML")
            except Exception:
                await message.reply(reply_text)
    else:
        await message.reply(
            "⚠️ <b>Лимит бесплатных токенов Groq исчерпан!</b>\n"
            "Подожди пару минут или сделай /reset.",
            parse_mode="HTML"
        )

async def main():
    print(">>> Copilot AI запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
