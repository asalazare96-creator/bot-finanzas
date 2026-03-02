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
DATA_FILE = "data.json"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── BASE DE DATOS (archivo JSON simple) ─────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"transactions": [], "debts": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ─── TECLADO RÁPIDO ──────────────────────────────────────────
KEYBOARD = ReplyKeyboardMarkup(
    [["📊 Reporte", "💸 Mis gastos"], ["💳 Deudas", "❓ Ayuda"]],
    resize_keyboard=True
)

# ─── COMANDOS ────────────────────────────────────────────────
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
        "💬 *Texto libre:*\n"
        "• 'gasté 30 en taxi'\n"
        "• 'cobré 500 de trabajo freelance'\n"
        "• 'debo 300 a Juan hasta el viernes'\n\n"
        "📸 *Foto:* Sube tu boleta y la analizo\n\n"
        "📊 *Botones:*\n"
        "• Reporte — resumen del mes\n"
        "• Mis gastos — lista de transacciones\n"
        "• Deudas — lo que debes",
        parse_mode="Markdown",
        reply_markup=KEYBOARD
    )

# ─── REPORTE DEL MES ─────────────────────────────────────────
async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    now = datetime.datetime.now()
    month_tx = [
        t for t in data["transactions"]
        if datetime.datetime.fromisoformat(t["date"]).month == now.month
        and datetime.datetime.fromisoformat(t["date"]).year == now.year
    ]

    income = sum(t["amount"] for t in month_tx if t["type"] == "income")
    expense = sum(t["amount"] for t in month_tx if t["type"] == "expense")
    balance = income - expense

    # Categorías
    cats = {}
    for t in month_tx:
        if t["type"] == "expense":
            cats[t["category"]] = cats.get(t["category"], 0) + t["amount"]
    top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    cats_text = "\n".join([f"  {c}: ${v:.2f}" for c, v in top_cats]) or "  Sin datos"

    # Deudas pendientes
    pending_debts = [d for d in data["debts"] if not d["paid"]]
    debt_total = sum(d["amount"] for d in pending_debts)

    emoji = "✅" if balance >= 0 else "⚠️"
    save_rate = round((balance / income) * 100) if income > 0 else 0

    msg = (
        f"📊 *Reporte de {now.strftime('%B %Y').capitalize()}*\n\n"
        f"📈 Ingresos:  `${income:,.2f}`\n"
        f"📉 Gastos:    `${expense:,.2f}`\n"
        f"─────────────────\n"
        f"{emoji} Balance:  `${balance:,.2f}`\n"
        f"💰 Ahorro:   `{save_rate}%`\n\n"
        f"🏷️ *Top categorías de gasto:*\n{cats_text}\n\n"
        f"💳 Deudas pendientes: `${debt_total:,.2f}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=KEYBOARD)

# ─── LISTA DE TRANSACCIONES ──────────────────────────────────
async def list_expenses(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    now = datetime.datetime.now()
    month_tx = [
        t for t in data["transactions"]
        if datetime.datetime.fromisoformat(t["date"]).month == now.month
    ][-10:]  # últimas 10

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

# ─── LISTA DE DEUDAS ─────────────────────────────────────────
async def list_debts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
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
        f"💳 *Deudas pendientes:*\n\n" + "\n\n".join(lines) + f"\n\n💰 Total: `${total:.2f}`",
        parse_mode="Markdown", reply_markup=KEYBOARD
    )

# ─── PROCESAR TEXTO CON IA ───────────────────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Botones del teclado
    if text == "📊 Reporte":
        await report(update, ctx); return
    if text == "💸 Mis gastos":
        await list_expenses(update, ctx); return
    if text == "💳 Deudas":
        await list_debts(update, ctx); return
    if text == "❓ Ayuda":
        await help_cmd(update, ctx); return

    # Procesar con IA
    await update.message.reply_text("⏳ Analizando...", reply_markup=KEYBOARD)

    today = datetime.date.today().isoformat()
    prompt = f"""Analiza este mensaje financiero y extrae los datos. Hoy es {today}.

Mensaje: "{text}"

Responde SOLO en JSON sin markdown. Puede ser uno de estos casos:

1. Si es un GASTO o INGRESO:
{{"action": "transaction", "type": "income|expense", "amount": 0.00, "description": "texto", "category": "una de: Comida, Transporte, Salud, Entretenimiento, Hogar, Ropa, Educación, Salario, Freelance, Otros", "date": "YYYY-MM-DD"}}

2. Si es una DEUDA:
{{"action": "debt", "name": "a quien", "amount": 0.00, "due_date": "YYYY-MM-DD", "notes": "notas opcionales"}}

3. Si no es financiero:
{{"action": "unknown"}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        raw = response.content[0].text.strip().replace("```json","").replace("```","")
        parsed = json.loads(raw)
    except:
        await update.message.reply_text("🤔 No entendí. Intenta: 'gasté 50 en comida' o 'cobré 200 de trabajo'", reply_markup=KEYBOARD)
        return

    data = load_data()

    if parsed["action"] == "transaction":
        data["transactions"].append({
            "id": int(datetime.datetime.now().timestamp()),
            "type": parsed["type"],
            "amount": float(parsed["amount"]),
            "description": parsed["description"],
            "category": parsed["category"],
            "date": parsed["date"]
        })
        save_data(data)
        sign = "📈 Ingreso" if parsed["type"] == "income" else "📉 Gasto"
        await update.message.reply_text(
            f"✅ *Registrado!*\n\n{sign}: *{parsed['description']}*\n💵 `${parsed['amount']:.2f}`\n🏷️ {parsed['category']}\n📅 {parsed['date']}",
            parse_mode="Markdown", reply_markup=KEYBOARD
        )

    elif parsed["action"] == "debt":
        data["debts"].append({
            "id": int(datetime.datetime.now().timestamp()),
            "name": parsed["name"],
            "amount": float(parsed["amount"]),
            "due_date": parsed["due_date"],
            "notes": parsed.get("notes",""),
            "paid": False
        })
        save_data(data)
        await update.message.reply_text(
            f"💳 *Deuda registrada!*\n\n👤 {parsed['name']}\n💵 `${parsed['amount']:.2f}`\n📅 Vence: {parsed['due_date']}",
            parse_mode="Markdown", reply_markup=KEYBOARD
        )

    else:
        await update.message.reply_text(
            "🤔 No parece un mensaje financiero.\nEjemplos:\n• 'gasté 30 en taxi'\n• 'cobré 500 de salario'\n• 'debo 200 al banco'",
            reply_markup=KEYBOARD
        )

# ─── PROCESAR IMAGEN (FACTURA) ───────────────────────────────
async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Analizando tu factura con IA...", reply_markup=KEYBOARD)

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)

    import httpx
    async with httpx.AsyncClient() as http:
        response = await http.get(file.file_path)
        image_data = base64.b64encode(response.content).decode()

    today = datetime.date.today().isoformat()
    ai_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": f"Analiza esta factura/boleta. Hoy es {today}. Responde SOLO en JSON sin markdown: {{\"description\": \"negocio/descripción\", \"amount\": 0.00, \"date\": \"YYYY-MM-DD\", \"category\": \"Comida|Transporte|Salud|Entretenimiento|Hogar|Ropa|Educación|Otros\"}}"}
            ]
        }]
    )

    try:
        raw = ai_response.content[0].text.strip().replace("```json","").replace("```","")
        parsed = json.loads(raw)

        data = load_data()
        data["transactions"].append({
            "id": int(datetime.datetime.now().timestamp()),
            "type": "expense",
            "amount": float(parsed["amount"]),
            "description": parsed["description"],
            "category": parsed["category"],
            "date": parsed["date"]
        })
        save_data(data)

        await update.message.reply_text(
            f"✅ *Factura registrada!*\n\n📉 Gasto: *{parsed['description']}*\n💵 `${parsed['amount']:.2f}`\n🏷️ {parsed['category']}\n📅 {parsed['date']}",
            parse_mode="Markdown", reply_markup=KEYBOARD
        )
    except:
        await update.message.reply_text("❌ No pude leer la factura. Intenta con una imagen más clara.", reply_markup=KEYBOARD)

# ─── MAIN ────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
