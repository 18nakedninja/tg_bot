import os
import psycopg2
from psycopg2 import IntegrityError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ================= НАСТРОЙКИ =================
# Вставь сюда токен твоего бота
BOT_TOKEN = "8342478210:AAFd3jAdENjgZ52FHmcm3jtDhkP4rpfOJLg"

# Вставь сюда ID телеграма администратора (число)
ADMIN_ID = 472044641  

# Файлы для обложки / стартового медиа
HEADER_IMAGE = "header.jpg"
HEADER_VIDEO = "header.mp4"
HEADER_GIF = "header.gif"
CONTACT_LINK = "https://t.me/mobilike_com"

# ================= СОСТОЯНИЯ =================
SELECT_PRODUCT, SELECT_QUANTITY, ADD_PRODUCT, REMOVE_PRODUCT, EDIT_PRODUCT_NAME = range(5)

# ================= ПОДКЛЮЧЕНИЕ К БАЗЕ =================
DATABASE_URL = os.environ.get("DATABASE_URL")  # Railway или локальный URL

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан! Проверь переменные окружения на Railway.")

# Подключение к PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cursor = conn.cursor()

# Создание таблиц, если их нет
cursor.execute("""
CREATE TABLE IF NOT EXISTS products(
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
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
print("✅ Подключение к БД успешно, таблицы проверены/созданы.")

# ================= ФУНКЦИИ =================
def get_products():
    cursor.execute("SELECT name FROM products ORDER BY id ASC")
    return [row[0] for row in cursor.fetchall()]

# ============== КЛИЕНТСКАЯ ЧАСТЬ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Отправляем медиа при старте
    if os.path.exists(HEADER_VIDEO):
        with open(HEADER_VIDEO, "rb") as v:
            await update.message.reply_video(v, caption="Выберите товар:")
    elif os.path.exists(HEADER_GIF):
        with open(HEADER_GIF, "rb") as g:
            await update.message.reply_animation(g, caption="Выберите товар:")
    elif os.path.exists(HEADER_IMAGE):
        with open(HEADER_IMAGE, "rb") as img:
            await update.message.reply_photo(img, caption="Выберите товар:")
    else:
        await update.message.reply_text("Выберите товар:")

    products = get_products()
    if not products:
        await update.message.reply_text("Список товаров пуст. Администратор должен его заполнить.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in products]
    keyboard.append([InlineKeyboardButton("📞 Связаться", url=CONTACT_LINK)])
    await update.message.reply_text("🛒 Список товаров:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_PRODUCT

async def product_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["product"] = query.data
    await query.edit_message_text(f"Вы выбрали: {query.data}\n\nВведите количество:")
    return SELECT_QUANTITY

async def quantity_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data.get("product")
    quantity = update.message.text
    user = update.message.from_user

    cursor.execute(
        "INSERT INTO orders(user_id, username, product, quantity) VALUES (%s, %s, %s, %s)",
        (str(user.id), user.username or "", product, quantity)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Ваш заказ на {quantity} × {product} принят!")
    admin_message = f"📦 Новый заказ!\n👤 @{user.username or user.id}\n🛒 {product}\n🔢 Кол-во: {quantity}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# ================== АДМИН ==================
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только админ
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
        await query.edit_message_text("✏️ Введите название нового товара:")
        return ADD_PRODUCT

    elif data == "remove_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(f"🗑 {p}", callback_data=f"delete_{p}")] for p in products]
        await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REMOVE_PRODUCT

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("❌ Название товара не может быть пустым.")
        return ADD_PRODUCT
    try:
        cursor.execute("INSERT INTO products(name) VALUES (%s)", (name,))
        conn.commit()
        await update.message.reply_text(f"✅ Товар «{name}» добавлен!")
    except IntegrityError:
        conn.rollback()
        await update.message.reply_text("❌ Такой товар уже есть.")
    return ConversationHandler.END

async def remove_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.replace("delete_", "")
    cursor.execute("DELETE FROM products WHERE name=%s", (name,))
    conn.commit()
    await query.edit_message_text(f"🗑 Товар «{name}» удалён.")
    return ConversationHandler.END

# ================== MAIN ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("admin", admin_menu)
        ],
        states={
            SELECT_PRODUCT: [CallbackQueryHandler(product_chosen)],
            SELECT_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_chosen)],
            ADD_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            REMOVE_PRODUCT: [CallbackQueryHandler(remove_product_handler, pattern="^delete_.*$")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_menu_handler,
                                         pattern="^(list_products|add_product|remove_product)$"))

    print("🚀 Бот запущен! Ожидаем команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
