import json
import os
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# === НАСТРОЙКИ ===
BOT_TOKEN = "743563203:AAHwP9ZkApgJc8BPBZpLMuvaJT_vNs1ja-s"  # <-- токен прямо в коде
ADMIN_ID = 472044641  # <-- замени на свой Telegram user ID
PRODUCTS_FILE = "products.json"
ORDERS_FILE = "orders.txt"
HEADER_IMAGE = "header.jpg"
HEADER_VIDEO = "header.mp4"
HEADER_GIF = "header.gif"
CONTACT_LINK = "https://t.me/mobilike_com"  # <-- сюда ссылку на твой Telegram

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

PRODUCTS = load_products()

# Состояния диалога
SELECT_PRODUCT, SELECT_QUANTITY, ADD_PRODUCT, REMOVE_PRODUCT, CONFIRM_CLEAR, WAIT_MEDIA = range(6)

# === КЛИЕНТСКАЯ ЧАСТЬ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Отправляем обложку, если есть
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

    if not PRODUCTS:
        await update.message.reply_text("Список товаров пуст. Администратор должен его заполнить.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in PRODUCTS]
    keyboard.append([InlineKeyboardButton("📞 Связаться", url=CONTACT_LINK)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛒 Список товаров:", reply_markup=reply_markup)
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

    with open(ORDERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user.username or user.id} заказал {quantity} × {product}\n")

    await update.message.reply_text(f"✅ Ваш заказ на {quantity} × {product} принят!")

    admin_message = f"📦 Новый заказ!\n👤 @{user.username or user.id}\n🛒 {product}\n🔢 Кол-во: {quantity}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# === АДМИН-МЕНЮ ===
# Пустой список товаров при старте
products = []

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное админ-меню"""
    query = update.callback_query
    if query:
        await query.answer()

    keyboard = [
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("❌ Удалить товар", callback_data="remove_product")],
        [InlineKeyboardButton("🧹 Очистить заказы", callback_data="clear_orders")],
        [InlineKeyboardButton("🖼 Загрузить картинку", callback_data="upload_media")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text("🔧 Админ-меню", reply_markup=reply_markup)
    else:
        await update.message.reply_text("🔧 Админ-меню", reply_markup=reply_markup)


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок в админ-меню"""
    query = update.callback_query
    await query.answer()

    if query.data == "list_products":
        if not products:
            await query.edit_message_text("📭 Список товаров пуст.")
        else:
            text = "📋 Текущие товары:\n" + "\n".join([f"• {p}" for p in products])
            await query.edit_message_text(text)

    elif query.data == "add_product":
        await query.edit_message_text("✏️ Введите название нового товара:")
        return ADD_PRODUCT

    elif query.data == "remove_product":
        if not products:
            await query.edit_message_text("📭 Нет товаров для удаления.")
            return
        keyboard = [
            [InlineKeyboardButton(f"❌ {p}", callback_data=f"remove:{p}")] for p in products
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите товар для удаления:", reply_markup=reply_markup)

    elif query.data == "clear_orders":
        keyboard = [
            [InlineKeyboardButton("✅ Да", callback_data="confirm_clear_yes"),
             InlineKeyboardButton("❌ Нет", callback_data="confirm_clear_no")]
        ]
        await query.edit_message_text("Вы уверены, что хотите удалить все заказы?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "upload_media":
        await query.edit_message_text("📤 Пришлите новую картинку.")
        return WAIT_MEDIA


async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление нового товара"""
    product_name = update.message.text.strip()
    if product_name:
        products.append(product_name)
        await update.message.reply_text(f"✅ Товар «{product_name}» добавлен!")
    else:
        await update.message.reply_text("⚠️ Пустое название, попробуйте снова.")
    return ConversationHandler.END


async def remove_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление выбранного товара"""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("remove:"):
        await query.edit_message_text("⚠️ Ошибка: неправильный формат.")
        return

    product_to_remove = query.data.split("remove:")[1]

    if product_to_remove in products:
        products.remove(product_to_remove)
        await query.edit_message_text(f"✅ Товар «{product_to_remove}» удалён!")
    else:
        await query.edit_message_text("⚠️ Товар не найден.")

async def upload_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.video:
        file = await update.message.video.get_file()
        await file.download_to_drive(HEADER_VIDEO)
        if os.path.exists(HEADER_IMAGE): os.remove(HEADER_IMAGE)
        if os.path.exists(HEADER_GIF): os.remove(HEADER_GIF)
        await update.message.reply_text("✅ Видео обложка сохранена!")
    elif update.message.animation:
        file = await update.message.animation.get_file()
        await file.download_to_drive(HEADER_GIF)
        if os.path.exists(HEADER_IMAGE): os.remove(HEADER_IMAGE)
        if os.path.exists(HEADER_VIDEO): os.remove(HEADER_VIDEO)
        await update.message.reply_text("✅ GIF обложка сохранена!")
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        await file.download_to_drive(HEADER_IMAGE)
        if os.path.exists(HEADER_VIDEO): os.remove(HEADER_VIDEO)
        if os.path.exists(HEADER_GIF): os.remove(HEADER_GIF)
        await update.message.reply_text("✅ Картинка обложка сохранена!")
    else:
        await update.message.reply_text("❌ Это не фото, видео или gif. Пришли другой файл.")
        return WAIT_MEDIA
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    async def post_init(application):
        # Эта функция вызывается автоматически после старта приложения
        await application.bot.set_my_commands([
            ("start", "Сделать заказ"),
            ("cancel", "Отменить действие"),
            ("admin", "Админ-меню"),
        ])

    app.post_init = post_init

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_PRODUCT: [CallbackQueryHandler(product_chosen)],
            SELECT_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_chosen)],
            ADD_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            REMOVE_PRODUCT: [CallbackQueryHandler(remove_product_handler)],
            CONFIRM_CLEAR: [CallbackQueryHandler(clear_orders_confirm)],
            WAIT_MEDIA: [MessageHandler(filters.ALL, upload_media_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CallbackQueryHandler(admin_menu_handler,
                                         pattern="^(list_products|add_product|remove_product|last_orders|clear_orders|upload_media)$"))

    # 🚀 Нормальный запуск без сложных asyncio.run()
    app.run_polling()

if __name__ == "__main__":
    main()
