import os
import json
import base64
import datetime
import anthropic
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ─── CONFIGURACIÓN ───────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── BASE DE DATOS EN MEMORIA ────────────────────────────────
user_data = {}

def get_user_data(user_id):
    uid = str(user_id)
    if uid not in user_data:
        user_data[uid] = {"transactions": [], "debts": []}
    return user_data[uid]

# ─── TECLADO RÁPIDO ──────────────────────────────────────────
KEYBOARD = ReplyKeyboardMarkup(
    [["📊 Reporte", "💸 Mis gastos"], ["💳 Deudas", "❓ Ayuda"]],
    resize_keyboard=True
)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *¡Hola! Soy tu bot de finanzas personales.*\n\n"
        "Puedes hablarme así:\n"
        "• _'gasté 50 en comida'_\n"
        "• _'ingresé 1000 de salario'_\n"
        "• _'debo 200 al banco hasta el 15 de marzo'_\n"
        "• 📸 Envíame una foto de tu boleta\n\n"
        "O usa los botones de abajo 👇",
        parse_mode="Markdown",
        reply_markup=KEYBOARD
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Comandos disponibles:*\n\n"
        "• 'gasté 30 en taxi'\n"
        "• 'cobré 500 de freelance'\n"
        "• 'debo 300 a Juan hasta el viernes'\n"
        "• 📸 Foto de boleta\n"
        "• 📊 Reporte del mes",
        parse_mode="Markdown",
        reply_markup=KEYBOARD
    )

async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(update.message.from_user.id)
    now = datetime.datetime.now()
    month_tx = [
        t for t in data["transactions"]
        if datetime.datetime.fromisoformat(t["date"]).month == now.month
        and datetime.datetime.fromisoformat(t["date"]).year == now.year
    ]

    income = sum(t["amount"] for t in month_tx if t["type"] == "income")
    expense = sum(t["amount"] for t in month_tx if t["type"] == "expense")
    balance = income - expense

    cats = {}
    for t in month_tx:
        if t["type"] == "expense":
            cats[t["category"]] = cats.get(t["category"], 0) + t["amount"]
    top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    cats_text = "\n".join([f"  {c}: ${v:.2f}" for c, v in top_cats]) or "  Sin datos"

    pending_debts = [d for d in data["debts"] if not d["paid"]]
    debt_total = sum(d["amount"] for d in pending_debts)
    emoji = "✅" if balance >= 0 else "⚠️"
    save_rate = round((balance / income) * 100) if income > 0 else 0

    await update.message.reply_text(
        f"📊 *Reporte de {now.strftime('%B %Y')}*\n\n"
        f"📈 Ingresos:  `${income:,.2f}`\n"
        f"📉 Gastos:    `${expense:,.2f}`\n"
        f"─────────────────\n"
        f"{emoji} Balance:  `${balance:,.2f}`\n"
        f"💰 Ahorro:   `{save_rate}%`\n\n"
        f"🏷️ *Top categorías:*\n{cats_text}\n\n"
        f"💳 Deudas pendientes: `${debt_total:,.2f}`",
        parse_mode="Markdown", reply_markup=KEYBOARD
    )

async def list_expenses(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(update.message.from_user.id)
    now = datetime.datetime.now()
    month_tx = [
        t for t in data["transactions"]
        if datetime.datetime.fromisoformat(t["date"]).month == now.month
    ][-10:]

    if not month_tx:
        await update.message.reply_text("📭 No hay transacciones este mes.", reply_markup=KEYBOARD)
        return

    lines = []
    for t in reversed(month_tx):
        sign = "➕" if t["type"] == "income" else "➖"
        d = datetime.datetime.fromisoformat(t["date"]).strftime("%d/%m")
        lines.append(f"{sign} {t['description']} — `${t['amount']:.2f}` _{d}_")

    await update.message.reply_text(
        "💸 *Últimas transacciones:*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=KEYBOARD
    )

async def list_debts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(update.message.from_user.id)
    pending = [d for d in data["debts"] if not d["paid"]]

    if not pending:
        await update.message.reply_text("✅ ¡No tienes deudas pendientes!", reply_markup=KEYBOARD)
        return

    lines = []
    for d in pending:
        due = datetime.datetime.fromisoformat(d["due_date"]).strftime("%d/%m/%Y")
        days_left = (datetime.datetime.fromisoformat(d["due_date"]) - datetime.datetime.now()).days
        alert = "🔴" if days_left <= 3 else ("🟡" if days_left <= 10 else "🟢")
        lines.append(f"{alert} *{d['name']}* — `${d['amount']:.2f}`\n   📅 Vence: {due} ({days_left}d)")

    total = sum(d["amount"] for d in pending)
    await update.message.reply_text(
        "💳 *Deudas pendientes:*\n\n" + "\n\n".join(lines) + f"\n\n💰 Total: `${total:.2f}`",
        parse_mode="Markdown", reply_markup=KEYBOARD
    )

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "📊 Reporte":
        await report(update, ctx); return
    if text == "💸 Mis gastos":
        await list_expenses(update, ctx); return
    if text == "💳 Deudas":
        await list_debts(update, ctx); return
    if text == "❓ Ayuda":
        await help_cmd(update, ctx); return

    await update.message.reply_text("⏳ Analizando...", reply_markup=KEYBOARD)

    today = datetime.date.today().isoformat()
    prompt = f"""Analiza este mensaje financiero. Hoy es {today}.
Mensaje: "{text}"
Responde SOLO JSON sin markdown:
Si es gasto/ingreso: {{"action":"transaction","type":"expense","amount":0.00,"description":"texto","category":"Comida","date":"YYYY-MM-DD"}}
Si es deuda: {{"action":"debt","name":"quien","amount":0.00,"due_date":"YYYY-MM-DD","notes":""}}
Si no es financiero: {{"action":"unknown"}}
Tipos validos: income o expense. Categorias: Comida, Transporte, Salud, Entretenimiento, Hogar, Ropa, Educacion, Salario, Freelance, Otros"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        parsed = json.loads(raw)
    except:
        await update.message.reply_text("🤔 No entendí. Ejemplo: 'gasté 50 en comida'", reply_markup=KEYBOARD)
        return

    data = get_user_data(update.message.from_user.id)

    if parsed.get("action") == "transaction":
        data["transactions"].append({
            "id": int(datetime.datetime.now().timestamp()),
            "type": parsed["type"],
            "amount": float(parsed["amount"]),
            "description": parsed["description"],
            "category": parsed["category"],
            "date": parsed["date"]
        })
        sign = "📈 Ingreso" if parsed["type"] == "income" else "📉 Gasto"
        await update.message.reply_text(
            f"✅ *¡Registrado!*\n\n{sign}: *{parsed['description']}*\n💵 `${float(parsed['amount']):.2f}`\n🏷️ {parsed['category']}\n📅 {parsed['date']}",
            parse_mode="Markdown", reply_markup=KEYBOARD
        )
    elif parsed.get("action") == "debt":
        data["debts"].append({
            "id": int(datetime.datetime.now().timestamp()),
            "name": parsed["name"],
            "amount": float(parsed["amount"]),
            "due_date": parsed["due_date"],
            "notes": parsed.get("notes",""),
            "paid": False
        })
        await update.message.reply_text(
            f"💳 *¡Deuda registrada!*\n\n👤 {parsed['name']}\n💵 `${float(parsed['amount']):.2f}`\n📅 Vence: {parsed['due_date']}",
            parse_mode="Markdown", reply_markup=KEYBOARD
        )
    else:
        await update.message.reply_text(
            "🤔 No parece financiero.\nEjemplos:\n• 'gasté 30 en taxi'\n• 'cobré 500 de salario'",
            reply_markup=KEYBOARD
        )

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Analizando factura...", reply_markup=KEYBOARD)
    try:
        photo = update.message.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        import httpx
        async with httpx.AsyncClient() as http:
            response = await http.get(file.file_path)
            image_data = base64.b64encode(response.content).decode()

        today = datetime.date.today().isoformat()
        ai_response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": f"Analiza esta factura. Hoy es {today}. Solo JSON: {{\"description\":\"negocio\",\"amount\":0.00,\"date\":\"YYYY-MM-DD\",\"category\":\"Comida\"}}"}
            ]}]
        )
        raw = ai_response.content[0].text.strip().replace("```json","").replace("```","").strip()
        parsed = json.loads(raw)

        data = get_user_data(update.message.from_user.id)
        data["transactions"].append({
            "id": int(datetime.datetime.now().timestamp()),
            "type": "expense",
            "amount": float(parsed["amount"]),
            "description": parsed["description"],
            "category": parsed["category"],
            "date": parsed["date"]
        })
        await update.message.reply_text(
            f"✅ *¡Factura registrada!*\n\n📉 *{parsed['description']}*\n💵 `${float(parsed['amount']):.2f}`\n🏷️ {parsed['category']}\n📅 {parsed['date']}",
            parse_mode="Markdown", reply_markup=KEYBOARD
        )
    except:
        await update.message.reply_text("❌ No pude leer la factura. Intenta con imagen más clara.", reply_markup=KEYBOARD)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot iniciado correctamente!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
