import logging
import os
import time
from datetime import datetime, timedelta
from ping3 import ping, exceptions
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, SERVERS

# Директория для логов
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Настройка логирования (динамическое обновление файла)
def get_logger():
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"server_monitor_{current_date}.log")
    logger = logging.getLogger("ServerMonitor")
    logger.setLevel(logging.INFO)

    # Удаляем старые хендлеры
    if logger.hasHandlers():
        logger.handlers.clear()

    # Новый хендлер для текущего дня
    handler = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

logger = get_logger()

# Интервал проверки (в секундах)
CHECK_INTERVAL = 60

# Хранение состояния серверов
server_status = {server['ip']: True for server in SERVERS}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я мониторю состояние серверов и уведомляю о проблемах.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    statuses = []
    for server in SERVERS:
        ip = server['ip']
        status = "✅ В сети" if server_status[ip] else "❌ Не в сети"
        statuses.append(f"{server['name']} ({ip}): {status}")
    await update.message.reply_text("\n".join(statuses))

async def get_failures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Используйте: /get_failures <YYYY-MM-DD> <YYYY-MM-DD>")
        return

    start_date, end_date = context.args
    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Используйте YYYY-MM-DD.")
        return

    results = []
    current_date = start_date
    while current_date <= end_date:
        log_file = os.path.join(LOG_DIR, f"server_monitor_{current_date.strftime('%Y-%m-%d')}.log")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if "WARNING" in line or "ERROR" in line:
                        results.append(line.strip())
        current_date += timedelta(days=1)

    if results:
        await update.message.reply_text("\n".join(results))
    else:
        await update.message.reply_text("Нет падений за указанный период.")

def monitor_servers(application):
    while True:
        global logger
        logger = get_logger()
        for server in SERVERS:
            ip = server['ip']
            name = server['name']
            try:
                response = ping(ip, timeout=2)
                if response is None:
                    if server_status[ip]:
                        logger.warning(f"{name} ({ip}) недоступен.")
                        server_status[ip] = False
                        application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"❌ {name} ({ip}) недоступен.")
                else:
                    response_ms = round(response * 1000, 2)  # Конвертируем в миллисекунды
                    if not server_status[ip]:
                        logger.info(f"{name} ({ip}) снова в сети. Задержка: {response_ms} ms")
                        server_status[ip] = True
                        application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"✅ {name} ({ip}) снова в сети. Задержка: {response_ms} ms")
                    else:
                        logger.info(f"{name} ({ip}) в сети. Задержка: {response_ms} ms")
            except exceptions.PingError as e:
                logger.error(f"Ошибка пинга {name} ({ip}): {e}")

        # Удаление старых логов
        delete_old_logs()
        time.sleep(CHECK_INTERVAL)

def delete_old_logs():
    cutoff_date = datetime.now() - timedelta(days=7)
    for log_file in os.listdir(LOG_DIR):
        log_path = os.path.join(LOG_DIR, log_file)
        if os.path.isfile(log_path):
            file_date_str = log_file.split("_")[2].split(".")[0]  # Извлечение даты из имени файла
            try:
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
                if file_date < cutoff_date:
                    os.remove(log_path)
                    logging.info(f"Удалён старый лог-файл: {log_file}")
            except ValueError:
                continue

if __name__ == "__main__":
    # Создание приложения Telegram Bot
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Добавление команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("get_failures", get_failures))

    # Запуск мониторинга в фоновом режиме
    import threading
    monitor_thread = threading.Thread(target=monitor_servers, args=(application,), daemon=True)
    monitor_thread.start()

    # Запуск бота
    application.run_polling()
