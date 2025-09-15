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

# ================= ФУНКЦИИ РАБОТЫ С БД =================
def execute_query(query, params=None, fetch=False):
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
        name TEXT UNIQUE NOT NULL,
        photo_id TEXT
    )""")
    execute_query("""
    CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY,
        user_id TEXT,
        username TEXT,
        product TEXT,
        phone TEXT
    )""")
    execute_query("""
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT,
        type TEXT
    )""")

def get_products():
    rows = execute_query("SELECT name, photo_id FROM products ORDER BY id ASC", fetch=True)
    return rows

# ================= КЛИЕНТСКАЯ ЧАСТЬ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Заглавное медиа (если установлено)
    header = execute_query("SELECT value, type FROM settings WHERE key='header_media'", fetch=True)
    if header:
        media_id, media_type = header[0]
        if media_type == "photo":
            await update.message.reply_photo(photo=media_id, caption="Добро пожаловать 🛍")
        elif media_type == "video":
            await update.message.reply_video(video=media_id, caption="Добро пожаловать 🛍")
        elif media_type == "animation":
            await update.message.reply_animation(animation=media_id, caption="Добро пожаловать 🛍")

    products = get_products()
    if not products:
        await update.message.reply_text("Список товаров пуст. Администратор должен его заполнить.")
        return

    for name, photo_id in products:
        keyboard = [[InlineKeyboardButton(f"🛒 Купить {name}", callback_data=f"product_{name}")]]
        if photo_id:
            await update.message.reply_photo(photo=photo_id, caption=f"📦 {name}", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(f"📦 {name}", reply_markup=InlineKeyboardMarkup(keyboard))

async def product_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product = query.data.replace("product_", "")
    context.user_data["product"] = product
    await query.edit_message_text(f"Вы выбрали: {product}\n\nВведите свой номер телефона для оформления заказа:")

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "product" not in context.user_data:
        return

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
        [InlineKeyboardButton("🖼 Установить заглавное медиа", callback_data="set_header_media")],
    ]
    await update.message.reply_text("⚙️ Админ-меню:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "list_products":
        products = get_products()
        text = "📋 Список товаров:\n" + "\n".join(f"• {p[0]}" for p in products) if products else "⚠️ Список пуст."
        await query.edit_message_text(text)

    elif data == "add_product":
        context.user_data["admin_mode"] = "add_product"
        await query.edit_message_text("✏️ Введите название нового товара:")

    elif data == "remove_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return
        keyboard = [[InlineKeyboardButton(f"🗑 {p[0]}", callback_data=f"delete_{p[0]}")] for p in products]
        await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "set_header_media":
        context.user_data["admin_mode"] = "set_header"
        await query.edit_message_text("📷 Отправьте фото / 🎥 видео / 🖼 гиф для заглавной части магазина.")

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

async def set_header_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("admin_mode") == "set_header":
        media_id, media_type = None, None

        if update.message.photo:
            media_id = update.message.photo[-1].file_id
            media_type = "photo"
        elif update.message.video:
            media_id = update.message.video.file_id
            media_type = "video"
        elif update.message.animation:
            media_id = update.message.animation.file_id
            media_type = "animation"
        else:
            await update.message.reply_text("❌ Поддерживаются только фото, видео и GIF.")
            return

        execute_query(
            "INSERT INTO settings (key, value, type) VALUES ('header_media', %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, type = EXCLUDED.type",
            (media_id, media_type)
        )

        await update.message.reply_text("✅ Заглавное медиа обновлено!")
        context.user_data.pop("admin_mode", None)

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
        elif context.user_data.get("admin_mode") == "set_header":
            await set_header_media(update, context)
        elif "product" in context.user_data:
            await phone_received(update, context)
        else:
            await update.message.reply_text("⚠️ Непонятная команда. Используйте /start или /admin")

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, text_router))

    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CallbackQueryHandler(admin_menu_handler, pattern="^(list_products|add_product|remove_product|set_header_media)$"))
    app.add_handler(CallbackQueryHandler(remove_product_handler, pattern="^delete_.*$"))

    print("🚀 Бот запущен! Ожидаем команды...")
    app.run_polling()

if __name__ == "__main__":
    main()
