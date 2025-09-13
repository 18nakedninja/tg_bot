import os
import psycopg2
from psycopg2 import IntegrityError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

BOT_TOKEN = "8342478210:AAFd3jAdENjgZ52FHmcm3jtDhkP4rpfOJLg"
ADMIN_ID = 472044641  

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан! Проверь Railway.")

conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS products(
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS orders(
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    product TEXT,
    quantity TEXT
)""")
conn.commit()

print("✅ Подключение к БД успешно, таблицы проверены/созданы.")

# ================= ФУНКЦИИ =================
def get_products():
    cursor.execute("SELECT name FROM products ORDER BY id ASC")
    return [row[0] for row in cursor.fetchall()]

# ============== КЛИЕНТСКАЯ ЧАСТЬ =================
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
    await query.edit_message_text(f"Вы выбрали: {product}\n\nВведите количество:")

async def quantity_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "product" not in context.user_data:
        return
    product = context.user_data["product"]
    quantity = update.message.text
    user = update.message.from_user

    cursor.execute("INSERT INTO orders(user_id, username, product, quantity) VALUES (%s, %s, %s, %s)",
                   (str(user.id), user.username or "", product, quantity))
    conn.commit()

    await update.message.reply_text(f"✅ Ваш заказ на {quantity} × {product} принят!")
    await context.bot.send_message(chat_id=ADMIN_ID,
                                   text=f"📦 Новый заказ!\n👤 @{user.username or user.id}\n🛒 {product}\n🔢 Кол-во: {quantity}")
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
    """Обрабатывает ввод текста админом — добавляет товар, если активен режим add_product"""
    if context.user_data.get("admin_mode") == "add_product":
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("❌ Название товара не может быть пустым.")
            return
        try:
            cursor.execute("INSERT INTO products(name) VALUES (%s)", (name,))
            conn.commit()
            await update.message.reply_text(f"✅ Товар «{name}» добавлен!")
        except IntegrityError:
            conn.rollback()
            await update.message.reply_text("❌ Такой товар уже есть.")
        context.user_data.pop("admin_mode", None)


# ================== MAIN ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_menu))

    # Ловим callback-кнопки из админ-меню
    app.add_handler(CallbackQueryHandler(admin_menu_handler,
                                         pattern="^(list_products|add_product|remove_product|delete_.*)$"))

    # Ловим любые текстовые сообщения админа, чтобы добавить товар
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name))

    # 🔑 Отдельный обработчик удаления товара (НОВЫЙ)
    app.add_handler(CallbackQueryHandler(remove_product_handler, pattern="^delete_.*$"))

    print("🚀 Бот запущен! Ожидаем команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
