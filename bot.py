import os
import psycopg2
from psycopg2 import IntegrityError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

BOT_TOKEN = "ТВОЙ_ТОКЕН"
ADMIN_ID = 472044641  

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан! Проверь Railway.")

# ================= ФУНКЦИИ РАБОТЫ С БД =================
def execute_query(query, params=None, fetch=False):
    """Универсальная функция для выполнения запросов."""
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    result = cursor.fetchall() if fetch else None
    conn.commit()
    cursor.close()
    conn.close()
    return result

def init_db():
    execute_query("""
    CREATE TABLE IF NOT EXISTS products(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    )""")
    execute_query("""
    CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY,
        user_id TEXT,
        username TEXT,
        product TEXT,
        phone TEXT
    )""")

def get_products():
    rows = execute_query("SELECT name FROM products ORDER BY id ASC", fetch=True)
    return [row[0] for row in rows]

# ================= КЛИЕНТСКАЯ ЧАСТЬ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_products()
    if not products:
        await update.message.reply_text("Список товаров пуст. Администратор должен его заполнить.")
        return

    keyboard = [[InlineKeyboardButton(p, callback_data=f"product_{p}")] for p in products]
    keyboard.append([InlineKeyboardButton("📞 Связаться", url="https://t.me/mobilike_com")])
    await update.message.reply_text("🛒 Список товаров:", reply_markup=InlineKeyboardMarkup(keyboard))

async def product_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product = query.data.replace("product_", "")
    context.user_data["product"] = product
    await query.edit_message_text(f"Вы выбрали: {product}\n\nВведите свой номер телефона для оформления заказа:")

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "product" not in context.user_data:
        return  # игнорируем если товар не выбран

    product = context.user_data["product"]
    phone = update.message.text.strip()
    user = update.message.from_user

    execute_query(
        "INSERT INTO orders(user_id, username, product, phone) VALUES (%s, %s, %s, %s)",
        (str(user.id), user.username or "", product, phone)
    )

    await update.message.reply_text(f"✅ Ваш заказ на {product} принят! Мы свяжемся с вами по номеру {phone}.")
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📦 Новый заказ!\n👤 @{user.username or user.id}\n🛒 {product}\n📞 Телефон: {phone}"
    )
    context.user_data.clear()

# ================== АДМИН ==================
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    keyboard = [
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("🗑 Удалить товар", callback_data="remove_product")],
    ]
    await update.message.reply_text("⚙️ Админ-меню:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "list_products":
        products = get_products()
        text = "📋 Список товаров:\n" + "\n".join(f"• {p}" for p in products) if products else "⚠️ Список пуст."
        await query.edit_message_text(text)

    elif data == "add_product":
        context.user_data["admin_mode"] = "add_product"
        await query.edit_message_text("✏️ Введите название нового товара:")

    elif data == "remove_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return
        keyboard = [[InlineKeyboardButton(f"🗑 {p}", callback_data=f"delete_{p}")] for p in products]
        await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("admin_mode") == "add_product":
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("❌ Название товара не может быть пустым.")
            return
        try:
            execute_query("INSERT INTO products(name) VALUES (%s)", (name,))
            await update.message.reply_text(f"✅ Товар «{name}» добавлен!")
        except IntegrityError:
            await update.message.reply_text("❌ Такой товар уже есть.")
        context.user_data.pop("admin_mode", None)

async def remove_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_name = query.data.replace("delete_", "")
    execute_query("DELETE FROM products WHERE name = %s", (product_name,))
    await query.edit_message_text(f"✅ Товар «{product_name}» удалён.")

# ================== MAIN ==================
def main():
    init_db()
    print("✅ Подключение к БД успешно, таблицы проверены/созданы.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Клиентские хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(product_chosen, pattern="^product_"))

    async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get("admin_mode") == "add_product":
            await add_product_name(update, context)
        elif "product" in context.user_data:
            await phone_received(update, context)
        else:
            await update.message.reply_text("⚠️ Непонятная команда. Используйте /start или /admin")

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CallbackQueryHandler(admin_menu_handler, pattern="^(list_products|add_product|remove_product)$"))
    app.add_handler(CallbackQueryHandler(remove_product_handler, pattern="^delete_.*$"))

    print("🚀 Бот запущен! Ожидаем команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
