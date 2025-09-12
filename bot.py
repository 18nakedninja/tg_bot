import os
import psycopg2
from psycopg2 import IntegrityError
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# === НАСТРОЙКИ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8342478210:AAFd3jAdENjgZ52FHmcm3jtDhkP4rpfOJLg"
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан! Установи его в переменных окружения.")

ADMIN_ID = 472044641
CONTACT_LINK = "https://t.me/mobilike_com"

# === STATES ===
SELECT_PRODUCT = 0
SELECT_QUANTITY = 1
ADD_PRODUCT = 2
REMOVE_PRODUCT = 3
SELECT_PRODUCT_TO_EDIT = 4
EDIT_PRODUCT_NAME = 5

# === DATABASE HELPERS ===
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не задана!")

def execute_query(query, params=None, fetch=False):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_products():
    rows = execute_query("SELECT name FROM products ORDER BY id ASC", fetch=True)
    return [r[0] for r in rows]

# === CREATE TABLES ===
execute_query("""
CREATE TABLE IF NOT EXISTS products(
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE
)
""")
execute_query("""
CREATE TABLE IF NOT EXISTS orders(
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    product TEXT,
    quantity TEXT
)
""")

# === CLIENT SIDE ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    try:
        execute_query(
            "INSERT INTO orders(user_id, username, product, quantity) VALUES (%s, %s, %s, %s)",
            (str(user.id), user.username or "", product, quantity)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка БД: {e}")
        return ConversationHandler.END

    await update.message.reply_text(f"✅ Ваш заказ на {quantity} × {product} принят!")
    await context.bot.send_message(chat_id=ADMIN_ID,
                                   text=f"📦 Новый заказ!\n👤 @{user.username or user.id}\n🛒 {product}\n🔢 Кол-во: {quantity}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# === ADMIN PANEL ===
async def show_admin_menu(update_or_query, context):
    keyboard = [
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("🗑 Удалить товар", callback_data="remove_product")],
        [InlineKeyboardButton("✏️ Редактировать товар", callback_data="edit_product")],
        [InlineKeyboardButton("📦 Последние заказы", callback_data="last_orders")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ]
    text = "⚙️ <b>Админ-панель</b>\n\nВыберите действие:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return ConversationHandler.END
    await show_admin_menu(update, context)
    return ConversationHandler.END

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "list_products":
        products = get_products()
        text = "📋 Список товаров:\n" + "\n".join(f"• {p}" for p in products) if products else "⚠️ Список пуст."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "add_product":
        await query.edit_message_text("✏️ Введите название нового товара:")
        return ADD_PRODUCT

    elif data == "remove_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(f"🗑 {p}", callback_data=f"delete_{p}")] for p in products]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
        await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REMOVE_PRODUCT

    elif data == "edit_product":
        products = get_products()
        if not products:
            await query.edit_message_text("⚠️ Список товаров пуст.")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(f"✏️ {p}", callback_data=f"edit_{p}")] for p in products]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
        await query.edit_message_text("Выберите товар для редактирования:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_PRODUCT_TO_EDIT

    elif data == "last_orders":
        orders = execute_query("SELECT user_id, username, product, quantity FROM orders ORDER BY id DESC LIMIT 5", fetch=True)
        text = "📦 Последние заказы:\n\n" + "".join(f"👤 @{u[1] or u[0]}: {u[3]} × {u[2]}\n" for u in orders) if orders else "📦 Заказов пока нет."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "stats":
        total_orders = execute_query("SELECT COUNT(*) FROM orders", fetch=True)[0][0]
        total_products = execute_query("SELECT COUNT(*) FROM products", fetch=True)[0][0]
        text = f"📊 Статистика:\n📦 Заказов: {total_orders}\n📋 Товаров: {total_products}"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_back":
        await show_admin_menu(query, context)

# === ADD / REMOVE / EDIT PRODUCT ===
async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        name = update.message.text.strip()
        print(f"[DEBUG] add_product_name вызван, получили: {name}")  # лог в консоль

        if not name:
            await update.message.reply_text("❌ Название товара не может быть пустым.")
            return ADD_PRODUCT

        try:
            execute_query("INSERT INTO products(name) VALUES (%s)", (name,))
        except IntegrityError:
            await update.message.reply_text("❌ Такой товар уже есть.")
            return ADD_PRODUCT
        except Exception as db_error:
            print(f"[ERROR] Ошибка при добавлении товара: {db_error}")
            await update.message.reply_text(f"❌ Ошибка БД: {db_error}")
            return ADD_PRODUCT

        await update.message.reply_text(f"✅ Товар «{name}» добавлен!")
        await show_admin_menu(update, context)
        return ConversationHandler.END

    except Exception as e:
        print(f"[CRITICAL] add_product_name упал: {e}")
        await update.message.reply_text(f"❌ Критическая ошибка: {e}")
        return ConversationHandler.END

async def remove_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.replace("delete_", "")
    execute_query("DELETE FROM products WHERE name=%s", (name,))
    await query.edit_message_text(f"🗑 Товар «{name}» удалён.")
    await show_admin_menu(update, context)
    return ConversationHandler.END

async def select_product_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_product"] = query.data.replace("edit_", "")
    await query.edit_message_text(f"✏️ Введите новое имя для товара «{context.user_data['edit_product']}»:")
    return EDIT_PRODUCT_NAME

async def edit_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    old_name = context.user_data.get("edit_product")
    if not old_name or not new_name:
        await update.message.reply_text("❌ Ошибка: неверное имя.")
        return EDIT_PRODUCT_NAME
    try:
        execute_query("UPDATE products SET name=%s WHERE name=%s", (new_name, old_name))
    except IntegrityError:
        await update.message.reply_text("❌ Товар с таким названием уже существует.")
        return EDIT_PRODUCT_NAME
    await update.message.reply_text(f"✅ Товар «{old_name}» переименован в «{new_name}».")
    await show_admin_menu(update, context)
    return ConversationHandler.END

# === MAIN ===
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
        CONFIRM_CLEAR: [CallbackQueryHandler(confirm_clear_handler)],
        WAIT_MEDIA: [MessageHandler(filters.ALL, upload_media_handler)]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,   # <-- ДОБАВИЛ, чтобы можно было снова войти в add_product
    per_message=True      # <-- САМОЕ ГЛАВНОЕ! иначе MessageHandler не отработает
)

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_menu_handler,
                                         pattern="^(list_products|add_product|remove_product|edit_product|last_orders|stats|admin_back)$"))
    app.run_polling()

if __name__ == "__main__":
    main()
