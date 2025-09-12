import os
import psycopg2
from psycopg2 import IntegrityError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# === НАСТРОЙКИ ===
BOT_TOKEN = "8342478210:AAFd3jAdENjgZ52FHmcm3jtDhkP4rpfOJLg"
ADMIN_ID = 472044641

HEADER_IMAGE = "header.jpg"
HEADER_VIDEO = "header.mp4"
HEADER_GIF = "header.gif"
CONTACT_LINK = "https://t.me/mobilike_com"

# === STATES ===
SELECT_PRODUCT, SELECT_QUANTITY, ADD_PRODUCT, REMOVE_PRODUCT, CONFIRM_CLEAR, WAIT_MEDIA, EDIT_PRODUCT = range(7)

# === АДМИН-МЕНЮ ===
async def show_admin_menu(update_or_query, context):
    keyboard = [
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("🗑 Удалить товар", callback_data="remove_product")],
        [InlineKeyboardButton("✏️ Редактировать товар", callback_data="edit_product")],
        [InlineKeyboardButton("📦 Последние заказы", callback_data="last_orders")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🧹 Очистить заказы", callback_data="clear_orders")],
        [InlineKeyboardButton("🖼 Загрузить обложку", callback_data="upload_media")]
    ]

    text = "⚙️ <b>Админ-панель</b>\n\nВыберите действие:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "edit_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(f"✏️ {p}", callback_data=f"edit_{p}")] for p in products]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
        await query.edit_message_text("Выберите товар для редактирования:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_PRODUCT

    # остальные обработчики остаются без изменений

async def edit_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    old_name = query.data.replace("edit_", "")
    context.user_data["edit_product"] = old_name
    await query.edit_message_text(f"✏️ Введите новое имя для товара «{old_name}»:")
    return EDIT_PRODUCT

async def edit_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    old_name = context.user_data.get("edit_product")
    if not old_name:
        await update.message.reply_text("⚠️ Ошибка: не выбран товар.")
        return ConversationHandler.END

    if not new_name:
        await update.message.reply_text("❌ Название не может быть пустым.")
        return EDIT_PRODUCT

    cursor.execute("UPDATE products SET name=%s WHERE name=%s", (new_name, old_name))
    conn.commit()

    await update.message.reply_text(f"✅ Товар «{old_name}» переименован в «{new_name}».")
    await show_admin_menu(update, context)
    return ConversationHandler.END

# === ПОДКЛЮЧЕНИЕ К POSTGRESQL ===
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задана! Проверь переменные окружения на Railway.")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# создаём таблицы, если их нет
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

# === КЛИЕНТСКАЯ ЧАСТЬ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    product = context.user_data["product"]
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

# === АДМИН-МЕНЮ ===
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    products = get_products()
    keyboard = [
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("🗑 Удалить товар", callback_data="remove_product")],
        [InlineKeyboardButton("📦 Последние заказы", callback_data="last_orders")],
        [InlineKeyboardButton("🧹 Очистить заказы", callback_data="clear_orders")],
        [InlineKeyboardButton("🖼 Загрузить обложку", callback_data="upload_media")]
    ]
    await update.message.reply_text("⚙️ Админ-меню:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "list_products":
        products = get_products()
        text = "📋 Список товаров:\n" + "\n".join(f"• {p}" for p in products) if products else "⚠️ Список пуст."
        await query.edit_message_text(text)

    elif data == "add_product":
        await query.edit_message_text("Введите название нового товара:")
        return ADD_PRODUCT

    elif data == "remove_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(f"🗑 {p}", callback_data=f"delete_{p}")] for p in products]
        await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REMOVE_PRODUCT

    elif data == "last_orders":
        cursor.execute("SELECT user_id, username, product, quantity FROM orders ORDER BY id DESC LIMIT 5")
        orders = cursor.fetchall()
        if not orders:
            await query.edit_message_text("📦 Заказов пока нет.")
            return ConversationHandler.END
        text = "📦 Последние заказы:\n\n" + "".join(f"👤 @{u[1] or u[0]}: {u[3]} × {u[2]}\n" for u in orders)
        await query.edit_message_text(text)

    elif data == "clear_orders":
        keyboard = [
            [InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear_yes")],
            [InlineKeyboardButton("❌ Отмена", callback_data="confirm_clear_no")]
        ]
        await query.edit_message_text("⚠️ Ты уверен, что хочешь удалить все заказы?", reply_markup=InlineKeyboardMarkup(keyboard))
        return CONFIRM_CLEAR

    elif data == "upload_media":
        await query.edit_message_text("📸 Пришли фото, видео или gif, которое будет обложкой при /start.")
        return WAIT_MEDIA

# === ДОБАВЛЕНИЕ / УДАЛЕНИЕ ТОВАРОВ ===
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

# === ЗАПУСК ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start),
                  CommandHandler("admin", admin_menu)],
    states={
        SELECT_PRODUCT: [CallbackQueryHandler(product_chosen)],
        SELECT_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_chosen)],
        ADD_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
        REMOVE_PRODUCT: [CallbackQueryHandler(remove_product_handler, pattern="^delete_.*$")],
        EDIT_PRODUCT: [
            CallbackQueryHandler(edit_product_handler, pattern="^edit_.*$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_name)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_menu_handler,
                                         pattern="^(list_products|add_product|remove_product|last_orders|clear_orders|upload_media)$"))
    app.run_polling()

if __name__ == "__main__":
    main()
