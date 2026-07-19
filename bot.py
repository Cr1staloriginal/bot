import os
import re
import asyncio
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем асинхронный API ВК
from univk import API

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = "8838275413:AAED4QN9xjmLOZn_u48uFt_tUXBvU_r4fkw"
# ===============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

is_running = False  # предотвращает одновременные запуски

# ---------- Извлечение ID из ссылки ----------
def extract_owner_id(text):
    """Извлекает числовой ID из ссылки ВК или просто числа"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    # ищем vk.com/id123 или vkontakte.ru/id123
    match = re.search(r'(?:vk\.com/|vkontakte\.ru/)(?:id)?(\d+)', text)
    if match:
        return int(match.group(1))
    return None

# ---------- Скачивание и отправка ----------
async def send_all_music(update: Update, context: ContextTypes.DEFAULT_TYPE, owner_id: int):
    global is_running
    user_id = update.effective_user.id

    if is_running:
        await context.bot.send_message(chat_id=user_id, text="⏳ Уже идёт отправка, подождите.")
        return

    is_running = True
    try:
        await context.bot.send_message(chat_id=user_id, text=f"🔍 Получаю список треков для владельца {owner_id}...")

        # Создаём экземпляр API ВК (без авторизации!)
        vk_api = API()

        # Получаем список аудиозаписей пользователя
        audios = await vk_api.get(owner_id)  # возвращает список словарей

        if not audios:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ У этого пользователя нет аудиозаписей (или они скрыты)."
            )
            is_running = False
            return

        total = len(audios)
        await context.bot.send_message(chat_id=user_id, text=f"✅ Найдено {total} треков. Начинаю отправку...")

        sent = 0
        for idx, audio in enumerate(audios, 1):
            artist = audio.get('artist', 'Unknown')
            title = audio.get('title', 'Unknown')
            url = audio.get('url')
            duration = audio.get('duration', 0)

            if not url:
                continue  # пропускаем треки без ссылки

            # Безопасное имя файла (заменяем спецсимволы)
            safe_artist = artist.replace('/', '_').replace(':', '_').replace('"', '')
            safe_title = title.replace('/', '_').replace(':', '_').replace('"', '')
            file_name = f"{safe_artist} - {safe_title}.mp3"
            file_path = os.path.join(os.getcwd(), file_name)

            # Скачиваем
            try:
                response = requests.get(url, stream=True, timeout=30)
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    # Отправляем в Telegram
                    with open(file_path, 'rb') as f:
                        await context.bot.send_audio(
                            chat_id=user_id,
                            audio=f,
                            title=title,
                            performer=artist,
                            duration=duration
                        )
                    os.remove(file_path)
                    sent += 1
                    await asyncio.sleep(0.7)  # чтобы не превысить лимиты Telegram
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⚠️ Не удалось скачать: {artist} - {title}"
                    )
            except Exception as e:
                logger.error(f"Ошибка при скачивании/отправке {file_name}: {e}")
                if os.path.exists(file_path):
                    os.remove(file_path)

            # Прогресс каждые 50 треков
            if idx % 50 == 0:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📦 Прогресс: {sent} из {total}"
                )

        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 Готово! Отправлено {sent} треков."
        )

    except Exception as e:
        logger.exception("Ошибка в send_all_music")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Ошибка: {str(e)[:200]}"
        )
    finally:
        is_running = False

# ---------- Обработчики команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я выгружаю музыку из профиля ВК.\n"
        "Отправь команду:\n"
        "/get_music <ссылка_на_профиль> или <id>\n"
        "Пример: /get_music https://vk.com/id123456\n"
        "Или просто /get_music 123456"
    )

async def get_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажите ссылку или ID, например:\n"
            "/get_music https://vk.com/id123456"
        )
        return

    arg = args[0]
    owner_id = extract_owner_id(arg)
    if owner_id is None:
        await update.message.reply_text(
            "❌ Не удалось распознать ID из ссылки. Укажите корректную ссылку или числовой ID."
        )
        return

    # Запускаем фоновую задачу
    asyncio.create_task(send_all_music(update, context, owner_id))
    await update.message.reply_text(
        f"🚀 Запущено извлечение музыки для ID {owner_id}. Следите за сообщениями от бота."
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get_music", get_music))
    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
