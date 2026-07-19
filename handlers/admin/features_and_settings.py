"""
پنل مدیریت کل — فاز ۲ اسپک (بخش ۷): فعال/رد درخواست فیچر، تنظیمات رمزارز،
لیست سیاه مشترک، اطلاعیه همگانی، فعال/غیرفعال‌سازی سراسری پرداخت قبوض،
گزارش سود واقعی کل سیستم — این نسخه: کاملاً دکمه‌ای (فاز ۲ پروژه‌ی دکمه‌ای‌سازی).
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.db import fetch_all
from services.feature_flag_service import (
    list_pending_features,
    decide_feature,
    set_bills_payment_enabled,
    is_bills_payment_enabled,
)
from services.crypto_service import upsert_crypto_setting
from services.blacklist_service import list_blacklist, add_to_blacklist
from utils.states import SuperAdminCryptoStates, SuperAdminBlacklistStates, SuperAdminBroadcastStates
from utils.keyboards import (
    admin_features_submenu,
    feature_decision_buttons,
    blacklist_add_button,
    bills_toggle_buttons,
    back_to_admin_menu_button,
)

router = Router(name="admin_features_and_settings")


@router.callback_query(F.data == "amenu:features")
async def features_menu(callback: CallbackQuery):
    await callback.message.edit_text("⚙️ فیچرها و تنظیمات", reply_markup=admin_features_submenu())
    await callback.answer()


# ---------- فیچر شارژ/VPN ----------
@router.callback_query(F.data == "amenu:features:pending")
async def pending_features_cb(callback: CallbackQuery):
    rows = await list_pending_features()
    if not rows:
        await callback.message.answer("درخواست فیچر در انتظاری وجود ندارد.", reply_markup=back_to_admin_menu_button())
        await callback.answer()
        return
    for r in rows:
        await callback.message.answer(
            f"#{r['id']} | نماینده {r['reseller_id']} | فیچر: {r['feature']}",
            reply_markup=feature_decision_buttons(r["id"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("feature_approve:"))
async def approve_feature_cb(callback: CallbackQuery):
    flag_id = int(callback.data.split(":")[1])
    await decide_feature(flag_id, approve=True)
    await callback.message.edit_text(f"فیچر #{flag_id} تأیید شد ✅")
    await callback.answer()


@router.callback_query(F.data.startswith("feature_reject:"))
async def reject_feature_cb(callback: CallbackQuery):
    flag_id = int(callback.data.split(":")[1])
    await decide_feature(flag_id, approve=False)
    await callback.message.edit_text(f"فیچر #{flag_id} رد شد.")
    await callback.answer()


# ---------- تنظیمات رمزارز (به‌جای یک دستور تک‌خطی، ۴ مرحله‌ی دکمه‌محور) ----------
@router.callback_query(F.data == "amenu:features:crypto")
async def start_set_crypto(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SuperAdminCryptoStates.entering_coin)
    await callback.message.answer("نام کوین را وارد کنید (مثال: USDT):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(SuperAdminCryptoStates.entering_coin)
async def receive_coin(message: Message, state: FSMContext):
    await state.update_data(coin=message.text.strip())
    await state.set_state(SuperAdminCryptoStates.entering_address)
    await message.answer("آدرس کیف‌پول را وارد کنید:")


@router.message(SuperAdminCryptoStates.entering_address)
async def receive_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(SuperAdminCryptoStates.entering_network)
    await message.answer("نام شبکه را وارد کنید (مثال: TRC20):")


@router.message(SuperAdminCryptoStates.entering_network)
async def receive_network(message: Message, state: FSMContext):
    await state.update_data(network=message.text.strip())
    await state.set_state(SuperAdminCryptoStates.entering_price)
    await message.answer("نرخ تبدیل (تومان به ازای یک واحد کوین) را وارد کنید:")


@router.message(SuperAdminCryptoStates.entering_price)
async def receive_price_and_save(message: Message, state: FSMContext):
    try:
        price = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("نرخ باید عدد باشد.")
        return
    data = await state.get_data()
    await upsert_crypto_setting(data["coin"], data["address"], data["network"], price)
    await message.answer(f"تنظیمات {data['coin']} ذخیره شد ✅", reply_markup=back_to_admin_menu_button())
    await state.clear()


# ---------- لیست سیاه مشترک ----------
@router.callback_query(F.data == "amenu:features:blacklist")
async def show_blacklist_cb(callback: CallbackQuery):
    rows = await list_blacklist()
    if not rows:
        text = "لیست سیاه خالی است."
    else:
        text = "\n".join(f"{r['telegram_user_id']} | {'سراسری' if r['is_global'] else 'محلی'} | {r['reason']}" for r in rows)
    await callback.message.answer(text, reply_markup=blacklist_add_button())
    await callback.answer()


@router.callback_query(F.data == "blacklist_add_start")
async def start_blacklist_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SuperAdminBlacklistStates.entering_telegram_id)
    await callback.message.answer("آیدی عددی تلگرام کاربر مورد نظر را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(SuperAdminBlacklistStates.entering_telegram_id)
async def receive_blacklist_id(message: Message, state: FSMContext):
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("آیدی عددی معتبر نیست، دوباره وارد کنید:")
        return
    await state.update_data(telegram_id=int(message.text.strip()))
    await state.set_state(SuperAdminBlacklistStates.entering_reason)
    await message.answer("دلیل بلاک شدن را وارد کنید (یا برای رد شدن، خط تیره - بفرستید):")


@router.message(SuperAdminBlacklistStates.entering_reason)
async def receive_blacklist_reason_and_save(message: Message, state: FSMContext):
    data = await state.get_data()
    reason = message.text.strip()
    if reason == "-":
        reason = "بدون دلیل ثبت‌شده"
    await add_to_blacklist(data["telegram_id"], reason, reseller_id=None, is_global=True)
    await message.answer(f"کاربر {data['telegram_id']} به لیست سیاه مشترک اضافه شد ✅", reply_markup=back_to_admin_menu_button())
    await state.clear()


# ---------- اطلاعیه همگانی ----------
@router.callback_query(F.data == "amenu:features:broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SuperAdminBroadcastStates.entering_text)
    await callback.message.answer("متن اطلاعیه‌ای که برای همه‌ی نماینده‌های فعال ارسال شود را بفرستید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(SuperAdminBroadcastStates.entering_text)
async def receive_broadcast_text_and_send(message: Message, state: FSMContext, bot: Bot):
    text = message.text
    resellers = await fetch_all("SELECT telegram_numeric_id FROM resellers WHERE status = 'active'")
    sent = 0
    for r in resellers:
        try:
            await bot.send_message(r["telegram_numeric_id"], f"📢 اطلاعیه از مدیریت:\n\n{text}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"اطلاعیه برای {sent} نماینده ارسال شد.", reply_markup=back_to_admin_menu_button())
    await state.clear()


# ---------- پرداخت قبوض (سراسری) ----------
@router.callback_query(F.data == "amenu:features:bills")
async def bills_status_cb(callback: CallbackQuery):
    enabled = await is_bills_payment_enabled()
    status_text = "فعال ✅" if enabled else "غیرفعال 🔴"
    await callback.message.answer(f"وضعیت فعلی پرداخت قبوض: {status_text}", reply_markup=bills_toggle_buttons(enabled))
    await callback.answer()


@router.callback_query(F.data.startswith("bills_set:"))
async def bills_set_cb(callback: CallbackQuery):
    value = callback.data.split(":")[1] == "on"
    await set_bills_payment_enabled(value)
    label = "فعال شد ✅" if value else "غیرفعال شد 🔴"
    await callback.message.edit_text(f"قابلیت پرداخت قبوض برای کل پلتفرم {label}")
    await callback.answer()
