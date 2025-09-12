import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# === ЛОГИ ===
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
BOT_TOKEN = "743563203:AAHwP9ZkApgJc8BPBZpLMuvaJT_vNs1ja-s"
ADMIN_ID = 472044641

HEADER_IMAGE = "header.jpg"
HEADER_VIDEO = "header.mp4"
HEADER_GIF = "header.gif"
CONTACT_LINK = "https://t.me/mobilike_com"

# === STATES ===
SELECT_PRODUCT, SELECT_QUANTITY, ADD_PRODUCT, REMOVE_PRODUCT = range(4)

# === БАЗА ДАННЫХ ===
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задана!")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products(
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS orders(
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    product TEXT,
    quantity TEXT
)
""")
conn.commit()

def get_products():
    cursor.execute("SELECT name FROM products ORDER BY id ASC")
    return [row[0] for row in cursor.fetchall()]

# === КЛИЕНТ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    media_sent = False
    for file, method in [(HEADER_VIDEO, update.message.reply_video),
                         (HEADER_GIF, update.message.reply_animation),
                         (HEADER_IMAGE, update.message.reply_photo)]:
        if os.path.exists(file):
            with open(file, "rb") as f:
                await method(f, caption="Выберите товар:")
                media_sent = True
                break
    if not media_sent:
        await update.message.reply_text("Выберите товар:")

    products = get_products()
    if not products:
        await update.message.reply_text("Список товаров пуст.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in products]
    keyboard.append([InlineKeyboardButton("📞 Связаться", url=CONTACT_LINK)])
    await update.message.reply_text("🛒 Список товаров:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_PRODUCT

async def product_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["product"] = query.data
    await query.edit_message_text(f"Вы выбрали: {query.data}\nВведите количество:")
    return SELECT_QUANTITY

async def quantity_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data["product"]
    quantity = update.message.text
    user = update.message.from_user

    cursor.execute(
        "INSERT INTO orders(user_id, username, product, quantity) VALUES (%s, %s, %s, %s)",
        (str(user.id), user.username or "", product, quantity)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Заказ на {quantity} × {product} принят!")
    await context.bot.send_message(chat_id=ADMIN_ID,
        text=f"📦 Новый заказ!\n👤 @{user.username or user.id}\n🛒 {product}\n🔢 Кол-во: {quantity}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# === АДМИН ===
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("🗑 Удалить товар", callback_data="remove_product")],
        [InlineKeyboardButton("📦 Последние заказы", callback_data="last_orders")],
        [InlineKeyboardButton("🧹 Очистить заказы", callback_data="clear_orders")]
    ]
    await update.message.reply_text("⚙️ Админ-меню:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
        data = query.data
        logger.info("Обработка admin-кнопки: %s", data)

        if data == "list_products":
            products = get_products()
            text = "📋 Товары:\n" + "\n".join(f"• {p}" for p in products) if products else "⚠️ Список пуст."
            await query.edit_message_text(text)

        elif data == "add_product":
            await query.edit_message_text("Введите название нового товара:")
            return ADD_PRODUCT

        elif data == "remove_product":
            products = get_products()
            if not products:
                await query.edit_message_text("⚠️ Список пуст.")
                return ConversationHandler.END
            keyboard = [[InlineKeyboardButton(f"🗑 {p}", callback_data=f"delete_{p}")] for p in products]
            await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
            return REMOVE_PRODUCT

        elif data == "last_orders":
            cursor.execute("SELECT user_id, username, product, quantity FROM orders ORDER BY id DESC LIMIT 5")
            orders = cursor.fetchall()
            if not orders:
                await query.edit_message_text("📦 Заказов нет.")
                return ConversationHandler.END
            text = "📦 Последние заказы:\n" + "".join(f"👤 @{u[1] or u[0]}: {u[3]} × {u[2]}\n" for u in orders)
            await query.edit_message_text(text)

        elif data == "clear_orders":
            cursor.execute("DELETE FROM orders")
            conn.commit()
            await query.edit_message_text("🧹 Все заказы удалены.")

    except Exception as e:
        logger.error("Ошибка в admin_handler: %s", str(e))
        await query.edit_message_text("❌ Ошибка при обработке кнопки.")
    return ConversationHandler.END

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    logger.info("Добавление товара: %s", name)
    if not name:
        await update.message.reply_text("❌ Название не может быть пустым.")
        return ADD_PRODUCT
    try:
        cursor.execute("INSERT INTO products(name) VALUES (%s)", (name,))
        conn.commit()
        await update.message.reply_text(f"✅ Товар «{name}» добавлен.")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await update.message.reply_text("❌ Такой товар уже существует.")
    return ConversationHandler.END

async def remove_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.replace("delete_", "")
    cursor.execute("DELETE FROM products WHERE name=%s", (name,))
    conn.commit()
    await query.edit_message_text(f"🗑 Товар «{name}» удалён.")
    return ConversationHandler.END

# === ЗАПУСК ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("admin", admin)],
        states={
            SELECT_PRODUCT: [
                CallbackQueryHandler(product_chosen),
                CallbackQueryHandler(admin_handler, pattern="^(list_products|add_product|remove_product|last_orders|clear_orders)$")
            ],
            SELECT_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_chosen),
                CallbackQueryHandler(admin_handler, pattern="^(list_products|add_product|remove_product|last_orders|clear_orders)$")
            ],
            ADD_PRODUCT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name),
                CallbackQueryHandler(admin_handler, pattern="^(list_products|add_product|remove_product|last_orders|clear_orders)$")
            ],
            REMOVE_PRODUCT: [
                CallbackQueryHandler(remove_product_handler, pattern="^delete_.*$"),
                CallbackQueryHandler(admin_handler, pattern="^(list_products|add_product|remove_product|last_orders|clear_orders)$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
