# bot.py
import os
import logging
import asyncpg
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# ==========================
# 🔧 НАСТРОЙКИ
# ==========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8342478210:AAFd3jAdENjgZ52FHmcm3jtDhkP4rpfOJLg")
ADMIN_ID = int(os.getenv("ADMIN_ID", "472044641"))  # твой Telegram ID
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:bVUsvGYRNbUYqKNdntqqngMZUWZWpYSh@switchback.proxy.rlwy.net:51471/railway")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================
# 📊 БАЗА ДАННЫХ
# ==========================
async def init_db():
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price NUMERIC(10,2)
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            product_id INT REFERENCES products(id),
            username TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.close()

async def get_products():
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("SELECT id, name, description, price FROM products")
    await conn.close()
    return [dict(r) for r in rows]

async def add_product(name, description, price):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute(
        "INSERT INTO products (name, description, price) VALUES ($1, $2, $3)",
        name, description, price
    )
    await conn.close()

async def add_order(product_id, username, phone):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute(
        "INSERT INTO orders (product_id, username, phone) VALUES ($1, $2, $3)",
        product_id, username, phone
    )
    await conn.close()

async def list_orders():
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("""
        SELECT o.id, p.name, o.username, o.phone, o.created_at
        FROM orders o
        JOIN products p ON o.product_id = p.id
        ORDER BY o.created_at DESC
    """)
    await conn.close()
    return [dict(r) for r in rows]

# ==========================
# 🤖 ЛОГИКА БОТА
# ==========================
SELECT_PRODUCT, GET_PHONE, ADD_PRODUCT_NAME, ADD_PRODUCT_DESC, ADD_PRODUCT_PRICE = range(5)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = await get_products()
    if not products:
        await update.message.reply_text("Пока нет доступных товаров.")
        return ConversationHandler.END

    buttons = [[p["name"]] for p in products]
    context.user_data["products"] = {p["name"]: p for p in products}

    await update.message.reply_text(
        "Выберите товар:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    )
    return SELECT_PRODUCT

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_name = update.message.text
    products = context.user_data.get("products", {})
    if product_name not in products:
        await update.message.reply_text("Выберите товар из списка.")
        return SELECT_PRODUCT

    context.user_data["selected_product"] = products[product_name]
    await update.message.reply_text("Введите ваш номер телефона:")
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    product = context.user_data["selected_product"]

    await add_order(product["id"], update.effective_user.username, phone)

    await update.message.reply_text(
        f"✅ Предзаказ оформлен на {product['name']}!\nМы свяжемся с вами."
    )
    return ConversationHandler.END

# ==========================
# 👑 АДМИН-КОМАНДЫ
# ==========================
async def admin_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ У вас нет доступа.")
    await update.message.reply_text("Введите название нового товара:")
    return ADD_PRODUCT_NAME

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"] = {"name": update.message.text}
    await update.message.reply_text("Введите описание товара:")
    return ADD_PRODUCT_DESC

async def add_product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"]["description"] = update.message.text
    await update.message.reply_text("Введите цену товара:")
    return ADD_PRODUCT_PRICE

async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Введите корректное число для цены.")
        return ADD_PRODUCT_PRICE

    p = context.user_data["new_product"]
    await add_product(p["name"], p["description"], price)
    await update.message.reply_text(f"✅ Товар '{p['name']}' добавлен.")
    return ConversationHandler.END

async def admin_list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ У вас нет доступа.")
    orders = await list_orders()
    if not orders:
        return await update.message.reply_text("📭 Заказов пока нет.")
    text = "\n\n".join(
        f"#{o['id']} {o['name']}\n👤 {o['username']} 📞 {o['phone']}\n🕒 {o['created_at']}"
        for o in orders
    )
    await update.message.reply_text(text)

# ==========================
# 🚀 ЗАПУСК
# ==========================
async def main():
    await init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Основной диалог для заказов
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_product)],
            GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
        },
        fallbacks=[]
    )

    # Диалог для добавления товара (только админ)
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("add_product", admin_add_product)],
        states={
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            ADD_PRODUCT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_desc)],
            ADD_PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
        },
        fallbacks=[]
    )

    app.add_handler(conv)
    app.add_handler(admin_conv)
    app.add_handler(CommandHandler("list_orders", admin_list_orders))

    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    # ✅ Вместо asyncio.run() — используем get_event_loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

