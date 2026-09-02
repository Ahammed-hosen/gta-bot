import sqlite3
import telebot
from telebot import types
import google.generativeai as genai

# টোকেন ও API কী কনফিগারেশন
BOT_TOKEN = "8854679629:AAFmojOsDLuNN9iA1qxcuqEUR5_mqHq7UOY"
GEMINI_API_KEY = "AQ.Ab8RN6JtDO5BUCno-JiEYD5e9lt2XMxINBXmpSMwaO8gshIWGg"

# AI কনফিগারেশন
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ডাটাবেজ তৈরি
def init_db():
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            car_name TEXT UNIQUE
        )
    """)
    conn.commit()
    conn.close()

def is_car_owned(car_name: str) -> bool:
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM cars WHERE LOWER(car_name) = LOWER(?)", (car_name.strip(),))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def add_car_to_db(user_id: int, car_name: str) -> bool:
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO cars (user_id, car_name) VALUES (?, ?)", (user_id, car_name.strip()))
        conn.commit()
        added = True
    except sqlite3.IntegrityError:
        added = False
    conn.close()
    return added

def get_all_cars():
    conn = sqlite3.connect("cars.db")
    cursor = conn.cursor()
    cursor.execute("SELECT car_name FROM cars ORDER BY id ASC")
    cars = [row[0] for row in cursor.fetchall()]
    conn.close()
    return cars

# AI দিয়ে গাড়ির আসল নাম যাচাই
def ai_process_car_name(user_input: str) -> str:
    prompt = (
        f"Identify if '{user_input}' refers to a GTA Online vehicle. "
        "If it is a vehicle, reply ONLY with the exact official in-game car name, nothing else. "
        "If it is not a GTA Online vehicle or just a random chat message, reply with 'NOT_A_CAR'."
    )
    try:
        response = ai_model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return user_input.strip()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "🚗 *GTA Online AI Garage Checker!*\n\n"
        "• যে কোনো গাড়ির নাম লিখুন (ভুল বানান হলেও AI বুঝে নেবে)।\n"
        "• সব গাড়ির তালিকা দেখতে: `/list`\n"
        "• একসাথে অনেক গাড়ি যোগ করতে: `/addall` এর নিচে লিস্ট দিন।"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['list'])
def list_cars(message):
    cars = get_all_cars()
    if not cars:
        bot.reply_to(message, "📭 গ্যারেজে এখনো কোনো গাড়ি নেই।")
        return

    full_text = f"📋 *আপনার গ্যারেজ (মোট: {len(cars)}টি):*\n\n"
    for idx, car in enumerate(cars, 1):
        full_text += f"{idx}. {car}\n"

    if len(full_text) > 4000:
        for i in range(0, len(full_text), 4000):
            bot.send_message(message.chat.id, full_text[i:i+4000])
    else:
        bot.reply_to(message, full_text)

@bot.message_handler(commands=['addall'])
def bulk_add(message):
    raw_text = message.text.replace("/addall", "").strip()
    lines = raw_text.split("\n")
    
    added_count = 0
    skipped_count = 0
    user_id = message.from_user.id

    for line in lines:
        name = line.strip()
        if name and name[0].isdigit() and ("." in name or ")" in name or "-" in name):
            for sep in [".", ")", "-"]:
                if sep in name:
                    name = name.split(sep, 1)[-1].strip()
                    break

        if name:
            if add_car_to_db(user_id, name):
                added_count += 1
            else:
                skipped_count += 1

    bot.reply_to(
        message,
        f"✅ *সম্পন্ন হয়েছে!*\n\n"
        f"• নতুন যোগ হয়েছে: `{added_count}` টি\n"
        f"• আগেই ছিল: `{skipped_count}` টি\n\n"
        f"লিস্ট দেখতে `/list` লিখুন।"
    )

@bot.message_handler(func=lambda msg: True)
def check_car_ai(message):
    user_text = message.text.strip()
    detected_car = ai_process_car_name(user_text)

    if detected_car == "NOT_A_CAR":
        try:
            chat_reply = ai_model.generate_content(
                f"User said: '{user_text}'. Reply briefly as a helpful GTA Online car expert in Bengali."
            ).text
            bot.reply_to(message, chat_reply)
        except Exception:
            bot.reply_to(message, "⚠️ এটি কোনো GTA Online গাড়ির নাম বলে মনে হচ্ছে না। সঠিক নাম লিখে পাঠান।")
        return

    if is_car_owned(detected_car):
        bot.reply_to(message, f"✅ *Already Owned!*\n`{detected_car}` আপনার গ্যারেজে রয়েছে।")
    else:
        markup = types.InlineKeyboardMarkup()
        btn_add = types.InlineKeyboardButton("➕ হ্যাঁ, গ্যারেজে যোগ করুন", callback_data=f"add_{detected_car}")
        btn_cancel = types.InlineKeyboardButton("❌ বাতিল", callback_data="cancel")
        markup.add(btn_add, btn_cancel)

        bot.reply_to(
            message,
            f"⚠️ *Not Owned!*\nগাড়ির নাম: *{detected_car}*\nএটি আপনার গ্যারেজে নেই। যোগ করতে চান?",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data.startswith("add_"):
        car_name = call.data.replace("add_", "")
        add_car_to_db(call.from_user.id, car_name)
        bot.edit_message_text(f"🎉 `{car_name}` সফলভাবে গ্যারেজে যোগ করা হয়েছে!", call.message.chat.id, call.message.message_id)
    elif call.data == "cancel":
        bot.edit_message_text("❌ বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

if __name__ == "__main__":
    init_db()
    bot.infinity_polling(timeout=10, long_polling_timeout=1)
  
