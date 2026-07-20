"""
پنل مدیریت کل — مدیریت نماینده‌ها (بخش ۷ اسپک) — فاز ۲: کاملاً دکمه‌ای.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from core.encryption import encrypt_token
from database.db import execute, fetch_all
from utils.states import SuperAdminResellerStates, SuperAdminResellerEditStates
from utils.keyboards import (
    admin_main_menu,
    admin_resellers_submenu,
    reseller_row_buttons,
    back_to_admin_menu_button,
)
from services.report_service import platform_wide_summary

router = Router(name="admin_reseller_management")


@router.message(F.text == "/start")
async def admin_start(message: Message):
    await message.answer(
        "👋 به پنل مدیریت کل خوش آمدید.\n\n"
        "از دکمه‌های زیر استفاده کنید. اگر وسط یک فرآیند گیر کردید، /cancel را بزنید.",
        reply_markup=admin_main_menu(),
    )


@router.callback_query(F.data == "amenu:home")
async def back_home(callback: CallbackQuery):
    await callback.message.edit_text(
        "👋 پنل مدیریت کل\n\nاز دکمه‌های زیر استفاده کنید.",
        reply_markup=admin_main_menu(),
    )
    await callback.answer()


@router.message(F.text == "/cancel")
async def cancel_any_state(message: Message, state: FSMContext):
    """راه فرار از هر حالت FSM گیرکرده — بدون این، هر پیام بعدی کاربر (حتی
    /start) توسط هندلر همان مرحله گرفته می‌شود."""
    current = await state.get_state()
    if current is None:
        await message.answer("در حال حاضر در هیچ فرآیندی نیستید.")
        return
    await state.clear()
    await message.answer("فرآیند لغو شد.", reply_markup=admin_main_menu())


# ---------- زیرمنوی نماینده‌ها ----------
@router.callback_query(F.data == "amenu:resellers")
async def resellers_menu(callback: CallbackQuery):
    await callback.message.edit_text("📋 مدیریت نماینده‌ها", reply_markup=admin_resellers_submenu())
    await callback.answer()


@router.callback_query(F.data == "amenu:resellers:add")
async def start_add_reseller_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SuperAdminResellerStates.entering_bot_token)
    await callback.message.answer(
        "توکن رباتی که نماینده از BotFather گرفته و به شما داده را ارسال کنید:\n"
        "(برای انصراف /cancel را بزنید)"
    )
    await callback.answer()


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

    from aiogram import Bot
    try:
        temp_bot = Bot(token=data["bot_token"])
        bot_info = await temp_bot.get_me()
        await temp_bot.session.close()
    except Exception:
        await message.answer("توکن ربات نامعتبر است. فرآیند افزودن نماینده لغو شد؛ دوباره از منو شروع کنید.")
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
        f"ربات ظرف حداکثر ۳۰ ثانیه به‌صورت خودکار روشن می‌شود.",
        reply_markup=admin_main_menu(),
    )
    await state.clear()


@router.callback_query(F.data == "amenu:resellers:list")
async def list_resellers_cb(callback: CallbackQuery):
    rows = await fetch_all(
        "SELECT id, bot_username, status, commission_percent, wallet_credit_balance FROM resellers"
    )
    if not rows:
        await callback.message.answer("هیچ نماینده‌ای ثبت نشده.", reply_markup=back_to_admin_menu_button())
        await callback.answer()
        return
    for r in rows:
        text = (
            f"#{r['id']} @{r['bot_username']}\n"
            f"وضعیت: {r['status']} | کمیسیون: {r['commission_percent']}٪ "
            f"| موجودی: {r['wallet_credit_balance']:,.0f}"
        )
        await callback.message.answer(text, reply_markup=reseller_row_buttons(r["id"], r["status"]))
    await callback.answer()


@router.callback_query(F.data.startswith("reseller_toggle:"))
async def toggle_reseller_status(callback: CallbackQuery):
    _, reseller_id, new_status = callback.data.split(":")
    await execute("UPDATE resellers SET status = %s WHERE id = %s", (new_status, int(reseller_id)))
    label = "فعال شد ✅" if new_status == "active" else "تعلیق شد ⏸"
    await callback.message.edit_text(f"نماینده #{reseller_id} {label}\nبات آن ظرف ۳۰ ثانیه به‌روزرسانی می‌شود.")
    await callback.answer()


# ---------- تغییر کمیسیون یک نماینده‌ی موجود ----------
@router.callback_query(F.data.startswith("reseller_edit_commission:"))
async def start_edit_commission(callback: CallbackQuery, state: FSMContext):
    reseller_id = int(callback.data.split(":")[1])
    rows = await fetch_all(
        "SELECT id, bot_username, commission_percent FROM resellers WHERE id = %s", (reseller_id,)
    )
    if not rows:
        await callback.answer("این نماینده پیدا نشد.", show_alert=True)
        return
    reseller = rows[0]
    await state.update_data(edit_reseller_id=reseller_id)
    await state.set_state(SuperAdminResellerEditStates.entering_new_commission_percent)
    await callback.message.answer(
        f"کمیسیون فعلی @{reseller['bot_username']}: {reseller['commission_percent']}٪\n"
        f"درصد کمیسیون جدید را وارد کنید (مثال: 3.5):\n(برای انصراف /cancel)"
    )
    await callback.answer()


@router.message(SuperAdminResellerEditStates.entering_new_commission_percent)
async def receive_new_commission_and_save(message: Message, state: FSMContext):
    try:
        percent = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("فقط عدد وارد کنید. مثال درست: 3.5")
        return
    if percent < 0 or percent > 100:
        await message.answer("درصد کمیسیون باید بین 0 تا 100 باشد.")
        return

    data = await state.get_data()
    reseller_id = data["edit_reseller_id"]
    await execute(
        "UPDATE resellers SET commission_percent = %s WHERE id = %s", (percent, reseller_id)
    )
    await message.answer(
        f"کمیسیون نماینده #{reseller_id} به {percent}٪ تغییر کرد ✅",
        reply_markup=admin_main_menu(),
    )
    await state.clear()


# ---------- گزارش پلتفرم (روی همین فایل چون هندلر کوتاهیه) ----------
@router.callback_query(F.data == "amenu:report")
async def platform_report_cb(callback: CallbackQuery):
    summary = await platform_wide_summary(days=30)
    await callback.message.answer(
        f"📊 گزارش کل پلتفرم (۳۰ روز اخیر)\n\n"
        f"تعداد سفارش فعال‌شده: {summary['order_count']}\n"
        f"فروش کل همه‌ی نماینده‌ها: {summary['total_sales']:,.0f} تومان\n"
        f"کارمزد جمع‌شده مدیریت: {summary['total_commission_collected']:,.0f} تومان\n"
        f"سود کل نماینده‌ها: {summary['total_reseller_profit']:,.0f} تومان",
        reply_markup=back_to_admin_menu_button(),
    )
    await callback.answer()
