import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime

# Logging သတ်မှတ်ခြင်း
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Database ဆက်သွယ်ခြင်း
def get_db():
    conn = sqlite3.connect('shop_bot.db')
    conn.row_factory = sqlite3.Row
    return conn


# Database တည်ဆောက်ခြင်း
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            stock INTEGER DEFAULT 0,
            image_url TEXT,
            category TEXT
        )
    ''')

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            cart TEXT DEFAULT '[]',
            joined_date TIMESTAMP
        )
    ''')

    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            items TEXT,
            total_amount REAL,
            status TEXT DEFAULT 'pending',
            order_date TIMESTAMP,
            payment_method TEXT,
            shipping_address TEXT
        )
    ''')

    conn.commit()
    conn.close()


# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # User ကို database ထဲသိမ်းခြင်း
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date)
        VALUES (?, ?, ?, ?)
    ''', (user.id, user.username, user.first_name, datetime.now()))
    conn.commit()
    conn.close()

    welcome_message = f"""မင်္ဂလာပါ {user.first_name}!

ကျွန်ုပ်တို့ ဆိုင်ကို ကြိုဆိုပါတယ်။ အောက်ပါ Command များကို သုံးနိုင်ပါတယ်။

/products - ပစ္စည်းများကြည့်ရန်
/cart - ခြင်းတောင်းကြည့်ရန်
/orders - မှာထားသောပစ္စည်းများ
/help - အကူအညီ

ဈေးဝယ်ခြင်းအတွက် ကျေးဇူးတင်ပါတယ်။"""

    await update.message.reply_text(welcome_message)


# Products ပြသခြင်း
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE stock > 0")
    products = cursor.fetchall()

    for product in products:
        button = InlineKeyboardButton(
            f"{product['name']} - {product['price']} MMK",
            callback_data=f"product_{product['id']}"
        )
        keyboard.append([button])

    conn.close()

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ကျွန်ုပ်တို့၏ ပစ္စည်းများ:", reply_markup=reply_markup)


# Product details ပြသခြင်း
async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split('_')[1])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if product:
        keyboard = [
            [InlineKeyboardButton("🛒 ခြင်းတောင်းထဲထည့်ရန်", callback_data=f"add_{product_id}")],
            [InlineKeyboardButton("◀ နောက်သို့", callback_data="back_to_products")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"""**{product['name']}**

{product['description']}

💰 ဈေးနှုန်း: {product['price']} MMK
📦 လက်ကျန်: {product['stock']} ခု
📂 အမျိုးအစား: {product['category']}"""

        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await query.edit_message_text("ပစ္စည်း မတွေ့ပါ")


# ခြင်းတောင်းထဲထည့်ခြင်း
async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    product_id = int(query.data.split('_')[1])

    conn = get_db()
    cursor = conn.cursor()

    # Get current cart
    cursor.execute("SELECT cart FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    import json
    cart = json.loads(result['cart']) if result and result['cart'] else []

    # Check if product already in cart
    found = False
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += 1
            found = True
            break

    if not found:
        cart.append({'product_id': product_id, 'quantity': 1})

    # Update cart
    cursor.execute("UPDATE users SET cart = ? WHERE user_id = ?",
                   (json.dumps(cart), user_id))
    conn.commit()
    conn.close()

    await query.answer("ပစ္စည်း ခြင်းတောင်းထဲသို့ ထည့်ပြီးပါပြီ ✅")

    # Show product list again
    await show_products_callback(update, context)


# ခြင်းတောင်းကြည့်ခြင်း
async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = get_db()
    cursor = conn.cursor()

    # Get user's cart
    cursor.execute("SELECT cart FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    import json
    cart = json.loads(result['cart']) if result and result['cart'] else []

    if not cart:
        await update.message.reply_text("သင့်ခြင်းတောင်းထဲတွင် ပစ္စည်းမရှိသေးပါ")
        return

    total = 0
    cart_items = []

    for item in cart:
        cursor.execute("SELECT * FROM products WHERE id = ?", (item['product_id'],))
        product = cursor.fetchone()
        if product:
            subtotal = product['price'] * item['quantity']
            total += subtotal
            cart_items.append(f"{product['name']} x {item['quantity']} = {subtotal} MMK")

    conn.close()

    message = "**သင့်ခြင်းတောင်း**\n\n" + "\n".join(cart_items) + f"\n\n**စုစုပေါင်း: {total} MMK**"

    keyboard = [
        [InlineKeyboardButton("✅ အော်ဒါတင်ရန်", callback_data="checkout")],
        [InlineKeyboardButton("🗑 ခြင်းတောင်းရှင်းရန်", callback_data="clear_cart")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')


# အော်ဒါတင်ခြင်း
async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    conn = get_db()
    cursor = conn.cursor()

    # Get user's cart
    cursor.execute("SELECT cart FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    import json
    cart = json.loads(result['cart']) if result and result['cart'] else []

    if not cart:
        await query.edit_message_text("သင့်ခြင်းတောင်းထဲတွင် ပစ္စည်းမရှိပါ")
        return

    # Calculate total
    total = 0
    for item in cart:
        cursor.execute("SELECT price FROM products WHERE id = ?", (item['product_id'],))
        product = cursor.fetchone()
        if product:
            total += product['price'] * item['quantity']

    # Save order
    cursor.execute('''
        INSERT INTO orders (user_id, items, total_amount, order_date, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, json.dumps(cart), total, datetime.now(), 'pending'))

    # Clear cart
    cursor.execute("UPDATE users SET cart = '[]' WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()

    await query.edit_message_text(f"အော်ဒါတင်ပြီးပါပြီ။ စုစုပေါင်း {total} MMK ကျသင့်ပါတယ်။ ကျေးဇူးတင်ပါတယ်။")


# Admin function to add product
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is admin (you can set admin IDs)
    admin_ids = [6810975122]  # Your Telegram ID

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("ဒီ Command ကို Admin များသာ သုံးနိုင်ပါတယ်")
        return

    try:
        # Format: /addproduct name,price,description,stock,category
        args = context.args
        if not args:
            await update.message.reply_text("ပုံစံ: /addproduct ပစ္စည်းနာမည်,ဈေးနှုန်း,ဖော်ပြချက်,လက်ကျန်,အမျိုးအစား")
            return

        product_data = ' '.join(args).split(',')
        if len(product_data) < 5:
            await update.message.reply_text("ဒေတာ အပြည့်အစုံ ထည့်ပါ")
            return

        name = product_data[0].strip()
        price = float(product_data[1].strip())
        description = product_data[2].strip()
        stock = int(product_data[3].strip())
        category = product_data[4].strip()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (name, price, description, stock, category)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, price, description, stock, category))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"ပစ္စည်း '{name}' ကို ထည့်သွင်းပြီးပါပြီ ✅")

    except Exception as e:
        await update.message.reply_text(f"အမှားဖြစ်နေပါတယ်: {str(e)}")


# Helper function for callback
async def show_products_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE stock > 0")
    products = cursor.fetchall()

    for product in products:
        button = InlineKeyboardButton(
            f"{product['name']} - {product['price']} MMK",
            callback_data=f"product_{product['id']}"
        )
        keyboard.append([button])

    conn.close()

    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    await query.edit_message_text("ကျွန်ုပ်တို့၏ ပစ္စည်းများ:", reply_markup=reply_markup)


# Main function
def main():
    # Initialize database
    init_db()

    # Your bot token from @BotFather
    token = "8328892708:AAG1QERDgg3ntB4wfsltT4tsFCga0wBff-U"

    # Create application
    application = Application.builder().token(token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("products", show_products))
    application.add_handler(CommandHandler("cart", view_cart))
    application.add_handler(CommandHandler("addproduct", add_product))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(product_detail, pattern="^product_"))
    application.add_handler(CallbackQueryHandler(add_to_cart, pattern="^add_"))
    application.add_handler(CallbackQueryHandler(show_products_callback, pattern="^back_to_products$"))
    application.add_handler(CallbackQueryHandler(view_cart, pattern="^view_cart$"))
    application.add_handler(CallbackQueryHandler(checkout, pattern="^checkout$"))

    # Start bot
    print("Bot is running...")
    application.run_polling()


if __name__ == '__main__':
    main()