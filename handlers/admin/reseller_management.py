"""
پنل مدیریت کل — مدیریت نماینده‌ها (بخش ۷ اسپک).
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state

from core.encryption import encrypt_token
from database.db import execute, fetch_all
from utils.states import SuperAdminResellerStates

router = Router(name="admin_reseller_management")


@router.message(F.text == "/start")
async def admin_start(message: Message):
    await message.answer(
        "👋 به پنل مدیریت کل خوش آمدید.\n\n"
        "📋 مدیریت نماینده‌ها:\n"
        "/add_reseller — افزودن نماینده جدید\n"
        "/list_resellers — لیست نماینده‌ها\n"
        "/suspend [id] — تعلیق نماینده\n"
        "/activate_reseller [id] — فعال‌سازی نماینده\n\n"
        "💰 کیف‌پول و استرداد:\n"
        "/pending_topups — شارژهای در انتظار تأیید\n"
        "/confirm_topup [id] — تأیید شارژ\n"
        "/pending_disputes — درخواست‌های استرداد در انتظار\n"
        "/approve_dispute [id] — تأیید استرداد\n"
        "/reject_dispute [id] — رد استرداد\n\n"
        "⚙️ فیچرها و تنظیمات:\n"
        "/pending_features — درخواست‌های فیچر شارژ/VPN\n"
        "/approve_feature [id] / /reject_feature [id]\n"
        "/set_crypto COIN ADDR NET PRICE\n"
        "/blacklist — لیست سیاه\n"
        "/blacklist_add [id] دلیل\n"
        "/broadcast متن — اطلاعیه همگانی\n"
        "/bills_on / /bills_off\n\n"
        "📊 گزارش:\n"
        "/platform_report — گزارش سود واقعی کل پلتفرم\n\n"
        "🗄 بک‌آپ:\n"
        "/backup / /restore\n\n"
        "اگر وسط یک فرآیند گیر کردید، /cancel را بزنید."
    )


@router.message(F.text == "/cancel")
async def cancel_any_state(message: Message, state: FSMContext):
    """راه فرار از هر حالت FSM گیرکرده (بخش ۷) — بدون این، اگر کاربر وسط
    /add_reseller چیز نامعتبری بفرستد یا نخواهد ادامه دهد، هر پیام بعدی‌اش
    (حتی /start) توسط هندلر همان مرحله گرفته می‌شود."""
    current = await state.get_state()
    if current is None:
        await message.answer("در حال حاضر در هیچ فرآیندی نیستید.")
        return
    await state.clear()
    await message.answer("فرآیند لغو شد. می‌توانید دوباره شروع کنید.")


@router.message(F.text == "/add_reseller")
async def start_add_reseller(message: Message, state: FSMContext):
    await state.set_state(SuperAdminResellerStates.entering_bot_token)
    await message.answer(
        "توکن رباتی که نماینده از BotFather گرفته و به شما داده را ارسال کنید:\n"
        "(برای انصراف /cancel را بزنید)"
    )


@router.message(SuperAdminResellerStates.entering_bot_token)
async def receive_bot_token(message: Message, state: FSMContext):
    await state.update_data(bot_token=message.text.strip())
    await state.set_state(SuperAdminResellerStates.entering_telegram_id)
    await message.answer("آیدی عددی تلگرام نماینده (صاحب ربات) را وارد کنید:")


@router.message(SuperAdminResellerStates.entering_telegram_id)
async def receive_telegram_id(message: Message, state: FSMContext):
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("آیدی عددی معتبر نیست، دوباره وارد کنید:\n(برای انصراف /cancel)")
        return
    await state.update_data(telegram_numeric_id=int(message.text.strip()))
    await state.set_state(SuperAdminResellerStates.entering_commission_percent)
    await message.answer("درصد کمیسیون این نماینده را وارد کنید (مثال: 2):")


@router.message(SuperAdminResellerStates.entering_commission_percent)
async def receive_commission(message: Message, state: FSMContext):
    try:
        percent = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("فقط عدد وارد کنید.")
        return
    await state.update_data(commission_percent=str(percent))
    await state.set_state(SuperAdminResellerStates.entering_credit_limit)
    await message.answer("سقف اعتبار منفی مجاز برای این نماینده را وارد کنید (مثال: 50000، یا 0 برای عدم مجوز منفی):")


@router.message(SuperAdminResellerStates.entering_credit_limit)
async def receive_credit_limit(message: Message, state: FSMContext):
    try:
        limit = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("فقط عدد وارد کنید.")
        return
    await state.update_data(credit_limit_negative=str(limit))
    await state.set_state(SuperAdminResellerStates.entering_order_prefix)
    await message.answer("پیشوند شناسه سفارش برای این نماینده را وارد کنید (مثال: AR):")


@router.message(SuperAdminResellerStates.entering_order_prefix)
async def receive_order_prefix_and_save(message: Message, state: FSMContext):
    data = await state.get_data()
    prefix = message.text.strip().upper()

    # اعتبارسنجی توکن با گرفتن username از طریق aiogram (خارج از این متد، در سرویس جداگانه)
    from aiogram import Bot
    try:
        temp_bot = Bot(token=data["bot_token"])
        bot_info = await temp_bot.get_me()
        await temp_bot.session.close()
    except Exception:
        await message.answer("توکن ربات نامعتبر است. فرآیند افزودن نماینده لغو شد؛ دوباره با /add_reseller شروع کنید.")
        await state.clear()
        return

    await execute(
        "INSERT INTO resellers (bot_token_encrypted, bot_username, telegram_numeric_id, "
        "commission_percent, credit_limit_negative, order_prefix, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'active')",
        (
            encrypt_token(data["bot_token"]),
            bot_info.username,
            data["telegram_numeric_id"],
            data["commission_percent"],
            data["credit_limit_negative"],
            prefix,
        ),
    )
    await message.answer(
        f"نماینده جدید با ربات @{bot_info.username} ثبت شد ✅\n"
        f"ربات ظرف حداکثر ۳۰ ثانیه به‌صورت خودکار توسط Bot Manager روشن می‌شود."
    )
    await state.clear()


@router.message(F.text == "/list_resellers")
async def list_resellers(message: Message):
    rows = await fetch_all("SELECT id, bot_username, status, commission_percent, wallet_credit_balance FROM resellers")
    if not rows:
        await message.answer("هیچ نماینده‌ای ثبت نشده.")
        return
    lines = [
        f"#{r['id']} @{r['bot_username']} | وضعیت: {r['status']} | کمیسیون: {r['commission_percent']}٪ "
        f"| موجودی: {r['wallet_credit_balance']:,.0f}"
        for r in rows
    ]
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/suspend "))
async def suspend_reseller(message: Message):
    reseller_id = int(message.text.split()[1])
    await execute("UPDATE resellers SET status = 'suspended' WHERE id = %s", (reseller_id,))
    await message.answer(f"نماینده #{reseller_id} تعلیق شد. بات آن ظرف ۳۰ ثانیه متوقف می‌شود.")


@router.message(F.text.startswith("/activate_reseller "))
async def activate_reseller(message: Message):
    reseller_id = int(message.text.split()[1])
    await execute("UPDATE resellers SET status = 'active' WHERE id = %s", (reseller_id,))
    await message.answer(f"نماینده #{reseller_id} فعال شد. بات آن ظرف ۳۰ ثانیه روشن می‌شود.")
