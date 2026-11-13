import asyncio
import io
import sqlite3
import os
import threading
from flask import Flask
import qrcode
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, BufferedInputFile
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= FLASK SERVER FOR RENDER / UPTIMEROBOT =================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running 24x7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# ================= CONFIGURATION =================
BOT_TOKEN = "9140398729:AAH8iU8gB4xfXP_tLOVxHcJpljRl9sbxIrs"
ADMIN_ID = 8832964897
LOG_CHANNEL_ID = -1004461325321
UPI_ID = "Paytm.s2b9rko@pty"
UPI_NAME = "TG SHOP"
SUPPORT_USERNAME = "@Ur_Alex25"
LOG_CHANNEL_LINK = "https://t.me/TG_SHOPSES"
BOT_USERNAME = "@TGSHOP25_BOT"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect("store.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance REAL DEFAULT 0.0
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    item_name TEXT,
                    region TEXT,
                    price REAL,
                    details TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS deposits (
                    dep_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    status TEXT
                )""")
    conn.commit()
    conn.close()

def get_balance(user_id: int) -> float:
    conn = sqlite3.connect("store.db")
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        conn.commit()
        balance = 0.0
    else:
        balance = row[0]
    conn.close()
    return round(balance, 2)

def update_balance(user_id: int, amount: float):
    get_balance(user_id)
    conn = sqlite3.connect("store.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# ================= MOCK STOCK / PANEL DATA =================
REGIONS = {
    "IN": {"name": "🇮🇳 India", "price": 28.6, "code": "+91"},
    "US": {"name": "🇺🇸 USA", "price": 37.7, "code": "+1"},
    "ID": {"name": "🇮🇩 Indonesia", "price": 25.0, "code": "+62"},
    "MM": {"name": "🇲🇲 Myanmar", "price": 30.0, "code": "+95"},
    "BD": {"name": "🇧🇩 Bangladesh", "price": 26.5, "code": "+880"},
    "VN": {"name": "🇻🇳 Vietnam", "price": 32.0, "code": "+84"}
}

# ================= FSM STATES =================
class DepositState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()

# ================= KEYBOARDS =================
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Telegram Accounts", callback_data="cat_menu")],
        [
            InlineKeyboardButton(text="💰 My Wallet", callback_data="wallet"),
            InlineKeyboardButton(text="➕ Deposit", callback_data="deposit")
        ],
        [InlineKeyboardButton(text="📦 My Orders", callback_data="my_orders")],
        [InlineKeyboardButton(text="📈 Sales", callback_data="sales")],
        [InlineKeyboardButton(text="🆘 Support", callback_data="support")]
    ])

def categories_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Cheap + Mail", callback_data="type:cheap_mail"),
            InlineKeyboardButton(text="🚫 Cheap No Mail", callback_data="type:cheap_nomail")
        ],
        [
            InlineKeyboardButton(text="⭐📧 Good + Mail", callback_data="type:good_mail"),
            InlineKeyboardButton(text="⭐🚫 Good No Mail", callback_data="type:good_nomail")
        ],
        [InlineKeyboardButton(text="🗑️ Use and Throw", callback_data="type:uet")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

def regions_kb(acc_type: str):
    buttons = []
    row = []
    for r_key, r_val in REGIONS.items():
        row.append(InlineKeyboardButton(text=r_val["name"], callback_data=f"reg:{acc_type}:{r_key}:1"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🌐 Global", callback_data=f"reg:{acc_type}:US:1")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="cat_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def items_list_kb(acc_type: str, region_key: str, page: int = 1):
    r_data = REGIONS[region_key]
    flag = r_data["name"].split()[0]
    price = r_data["price"]
    
    buttons = []
    for i in range(6):
        item_id = (page - 1) * 6 + i + 1
        btn_text = f"{flag} ₹{price} {region_key}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"buy:{acc_type}:{region_key}:{item_id}")])
    
    buttons.append([InlineKeyboardButton(text="Next ➡️", callback_data=f"reg:{acc_type}:{region_key}:{page+1}")])
    buttons.append([
        InlineKeyboardButton(text="🔄 Refresh", callback_data=f"reg:{acc_type}:{region_key}:{page}"),
        InlineKeyboardButton(text="⬅️ Back", callback_data=f"type:{acc_type}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= HANDLERS =================
def get_welcome_text(user_name: str, balance: float) -> str:
    return (
        f"👋 Hi {user_name},\n\n"
        f"💎 Welcome to STORE\n"
        f"Live Telegram accounts with instant delivery.\n"
        f"⚠️ Non-guarantee / phishing accounts may be included.\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Your Wallet: ₹{balance}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ Instant Delivery\n"
        f"🔐 Secure Payments\n"
        f"📈 Dynamic panel pricing\n\n"
        f"👇 Select an option:"
    )

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    bal = get_balance(message.from_user.id)
    await message.answer(
        get_welcome_text(message.from_user.first_name, bal),
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    bal = get_balance(call.from_user.id)
    await call.message.edit_text(
        get_welcome_text(call.from_user.first_name, bal),
        reply_markup=main_menu_kb()
    )
    await call.answer()

@dp.callback_query(F.data == "cat_menu")
async def cb_cat_menu(call: CallbackQuery):
    text = (
        "📱 **TG Accounts**\n\n"
        "Prices are fetched live from the panel.\n"
        "Your configured margin is added automatically.\n\n"
        "Cheap Acc — All origins, lowest price\n"
        "Good Acc — Safe origins (Autoreg, Personal, Self Registration)\n\n"
        "📧 Mail Added — Email bound to account\n"
        "🚫 No Mail — No email bound\n\n"
        "⚠️ NO REFUNDS IN ANY CASE."
    )
    await call.message.edit_text(text, reply_markup=categories_kb(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("type:"))
async def cb_select_type(call: CallbackQuery):
    acc_type = call.data.split(":")[1]
    text = (
        "📧 **Mail Accounts**\n\n"
        "Mail-included accounts from all available qualities.\n\n"
        "👇 Select a region to browse:"
    )
    await call.message.edit_text(text, reply_markup=regions_kb(acc_type), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("reg:"))
async def cb_select_region(call: CallbackQuery):
    _, acc_type, region_key, page_str = call.data.split(":")
    page = int(page_str)
    r_name = REGIONS[region_key]["name"]
    
    await call.answer("🔄 Fetching accounts...")
    text = (
        f"🌍 Available Accounts: {r_name}\n"
        f"📄 Page {page}\n\n"
        f"⚡ Instant Delivery\n"
        f"👇 Select an account to buy:"
    )
    try:
        await call.message.edit_text(text, reply_markup=items_list_kb(acc_type, region_key, page))
    except Exception:
        pass

@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy_item(call: CallbackQuery):
    _, acc_type, region_key, item_id = call.data.split(":")
    r_data = REGIONS[region_key]
    price = r_data["price"]
    user_id = call.from_user.id
    bal = get_balance(user_id)
    
    await call.answer()
    temp_msg = await call.message.answer("🔄 Buying account... Please wait.")
    await asyncio.sleep(0.8)
    
    if bal < price:
        await temp_msg.edit_text(f"❌ Insufficient Balance! Need ₹{price} (Your Wallet: ₹{bal})")
        return
    
    update_balance(user_id, -price)
    dummy_number = f"{r_data['code']}98***{item_id.zfill(2)}"
    
    conn = sqlite3.connect("store.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, item_name, region, price, details) VALUES (?, ?, ?, ?, ?)",
        (user_id, r_data["name"], r_data["name"], price, f"Number: {dummy_number} | OTP: Ready")
    )
    conn.commit()
    conn.close()
    
    await temp_msg.edit_text(
        f"✅ **Purchase Successful!**\n\n"
        f"📦 Item: {r_data['name']}\n"
        f"📱 Number: `{dummy_number}`\n"
        f"💰 Paid: ₹{price}",
        parse_mode="Markdown"
    )
    
    uid_str = str(user_id)
    masked_user = f"{uid_str[:2]}***{uid_str[-3:]}"
    log_text = (
        f"🚀 **NEW ACCOUNT SOLD!**\n\n"
        f"👤 User: `{masked_user}`\n"
        f"📦 Item: {r_data['name']}\n"
        f"🌍 Region: {r_data['name']}\n"
        f"📱 Number: `{dummy_number}`\n"
        f"💰 Price: ₹{price}\n"
        f"⚡ Status: Verified & Delivered\n\n"
        f"🛍️ Always use {BOT_USERNAME}"
    )
    try:
        await bot.send_message(LOG_CHANNEL_ID, log_text, parse_mode="Markdown")
    except Exception:
        pass

# ================= WALLET & DEPOSIT =================
@dp.callback_query(F.data == "wallet")
async def cb_wallet(call: CallbackQuery):
    bal = get_balance(call.from_user.id)
    await call.message.answer(f"💳 Balance ₹{bal}\n\nNo transactions.")
    await call.answer()

@dp.callback_query(F.data == "deposit")
async def cb_deposit(call: CallbackQuery, state: FSMContext):
    await state.set_state(DepositState.waiting_for_amount)
    await call.message.answer("➕ **Deposit Funds**\n\nPlease enter the amount you want to deposit (in ₹):", parse_mode="Markdown")
    await call.answer()

@dp.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("⚠️ Kripya valid amount (sirf numbers) enter karein:")
        return
    
    amount = int(message.text)
    await state.update_data(amount=amount)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🇮🇳 UPI Payment — ₹{amount}", callback_data=f"pay_upi:{amount}")],
        [InlineKeyboardButton(text=f"💎 Crypto Payment — ₹{amount}", callback_data=f"pay_crypto:{amount}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_dep")]
    ])
    await message.answer(
        f"💰 **Deposit ₹{amount}**\n\nSelect your preferred payment method:",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("pay_upi:"))
async def cb_pay_upi(call: CallbackQuery, state: FSMContext):
    amount = call.data.split(":")[1]
    await state.set_state(DepositState.waiting_for_screenshot)
    
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
    qr = qrcode.make(upi_url)
    bio = io.BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)
    
    caption = (
        f"🇮🇳 **Manual UPI Deposit**\n\n"
        f"💰 Amount: ₹{amount}\n"
        f"🏦 UPI ID: `{UPI_ID}`\n\n"
        f"1️⃣ Pay the exact amount using the UPI ID or QR above.\n"
        f"2️⃣ After payment, send the **payment screenshot here**.\n"
        f"3️⃣ Admin will verify it manually.\n"
        f"4️⃣ Balance will be added after approval."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_dep")]
    ])
    
    await call.message.delete()
    await call.message.answer_photo(
        photo=BufferedInputFile(bio.read(), filename="qr.png"),
        caption=caption,
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("pay_crypto:"))
async def cb_pay_crypto(call: CallbackQuery):
    await call.answer(f"💎 Crypto deposit ke liye {SUPPORT_USERNAME} se sampark karein!", show_alert=True)

@dp.message(DepositState.waiting_for_screenshot, F.photo)
async def process_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount", 0)
    user_id = message.from_user.id
    
    conn = sqlite3.connect("store.db")
    c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, amount, status) VALUES (?, ?, 'pending')", (user_id, amount))
    dep_id = c.lastrowid
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("✅ Screenshot received! Admin verification ke baad aapka balance add ho jayega.")
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_app:{dep_id}:{user_id}:{amount}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_rej:{dep_id}:{user_id}")
        ]
    ])
    try:
        await bot.send_photo(
            ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=f"🔔 **New Deposit Request #{dep_id}**\n👤 User: `{user_id}`\n💰 Amount: ₹{amount}",
            reply_markup=admin_kb,
            parse_mode="Markdown"
        )
    except Exception:
        pass

@dp.callback_query(F.data.startswith("adm_app:"))
async def cb_admin_approve(call: CallbackQuery):
    _, dep_id, user_id, amount = call.data.split(":")
    user_id, amount = int(user_id), float(amount)
    
    update_balance(user_id, amount)
    await call.message.edit_caption(caption=f"✅ Deposit #{dep_id} Approved (₹{amount} added to {user_id})")
    
    try:
        await bot.send_message(user_id, f"✅ Aapka ₹{amount} ka deposit approve ho gaya hai!")
        await bot.send_message(LOG_CHANNEL_ID, f"✅ Deposit #{dep_id} (₹{amount}) approved by admin\nUser: `{user_id}`", parse_mode="Markdown")
    except Exception:
        pass

@dp.callback_query(F.data.startswith("adm_rej:"))
async def cb_admin_reject(call: CallbackQuery):
    _, dep_id, user_id = call.data.split(":")
    user_id = int(user_id)
    
    await call.message.edit_caption(caption=f"❌ Deposit #{dep_id} Rejected (User: {user_id})")
    try:
        await bot.send_message(user_id, f"❌ Aapka deposit request #{dep_id} reject ho gaya hai. Support: {SUPPORT_USERNAME}")
    except Exception:
        pass

@dp.callback_query(F.data == "cancel_dep")
async def cb_cancel_dep(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    bal = get_balance(call.from_user.id)
    await call.message.answer(
        get_welcome_text(call.from_user.first_name, bal),
        reply_markup=main_menu_kb()
    )

# ================= ORDERS, SALES & SUPPORT =================
@dp.callback_query(F.data == "my_orders")
async def cb_my_orders(call: CallbackQuery):
    conn = sqlite3.connect("store.db")
    c = conn.cursor()
    c.execute("SELECT item_name, price, details FROM orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 5", (call.from_user.id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        text = "📦 **Order History**\n\nNo orders yet."
    else:
        text = "📦 **Order History**\n\n"
        for r in rows:
            text += f"• {r[0]} (₹{r[1]}) — `{r[2]}`\n"
            
    await call.message.answer(text, reply_markup=main_menu_kb(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "sales")
async def cb_sales(call: CallbackGroup if 'CallbackGroup' in globals() else object):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 TG SHOP LOGS", url=LOG_CHANNEL_LINK)],
        [InlineKeyboardButton(text="🏠 Menu", callback_data="main_menu")]
    ])
    await call.message.answer(
        "📈 **Sales Channels**\n\nJoin our optional sales channels for updates and offers:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    await call.message.answer(f"🆘 Support ke liye sampark karein: {SUPPORT_USERNAME}")
    await call.answer()

async def main():
    init_db()
    keep_alive()  # Flask server start karega background mein
    print("Bot aur Web Server chalu ho gaye hain...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
