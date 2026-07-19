"""
💳 روش دریافت وجه از مشتری (بخش جدا از کیف‌پول کمیسیون پلتفرم!)

کیف‌پول کمیسیون (handlers/reseller/wallet.py و services/wallet_service.py)
یک اعتبار پیش‌شارژشده‌ی داخلی است که پلتفرم از آن کمیسیون کسر می‌کند.

این بخش کاملاً چیز دیگری است: حساب/کارت شخصی خود نماینده که مشتری مستقیماً
پول بسته را به آن واریز می‌کند.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from services.payment_methods_service import (
    add_card,
    list_cards,
    toggle_card,
    remove_card,
    set_zarinpal_merchant,
    get_zarinpal_merchant,
    format_card_number,
)
from utils.states import ResellerPaymentMethodStates
from utils.keyboards import payment_methods_submenu, card_row_buttons, back_to_reseller_menu_button

router = Router(name="reseller_payment_methods")


@router.callback_query(F.data == "rmenu:payment_methods")
async def payment_methods_menu(callback: CallbackQuery):
    await callback.message.edit_text("💳 روش دریافت وجه از مشتری", reply_markup=payment_methods_submenu())
    await callback.answer()


@router.callback_query(F.data == "pm:list_cards")
async def list_cards_cb(callback: CallbackQuery, reseller_id: int):
    cards = await list_cards(reseller_id)
    if not cards:
        await callback.message.answer("هنوز کارتی ثبت نکرده‌اید.", reply_markup=payment_methods_submenu())
        await callback.answer()
        return
    for c in cards:
        status = "✅ فعال" if c["is_active"] else "⛔️ غیرفعال"
        text = (
            f"#{c['id']} | {format_card_number(c['card_number'])} | {c['card_holder_name']}"
            + (f" | {c['bank_name']}" if c["bank_name"] else "")
            + f" | {status}"
        )
        await callback.message.answer(text, reply_markup=card_row_buttons(c["id"], c["is_active"]))
    await callback.answer()


@router.callback_query(F.data.startswith("pm:toggle_card:"))
async def toggle_card_cb(callback: CallbackQuery, reseller_id: int):
    card_id = int(callback.data.split(":")[2])
    new_status = await toggle_card(card_id, reseller_id)
    if new_status is None:
        await callback.message.edit_text("این کارت پیدا نشد (یا متعلق به شما نیست).")
        await callback.answer()
        return
    await callback.message.edit_text(f"کارت #{card_id} حالا {'✅ فعال' if new_status else '⛔️ غیرفعال'} است.")
    await callback.answer()


@router.callback_query(F.data.startswith("pm:remove_card:"))
async def remove_card_cb(callback: CallbackQuery, reseller_id: int):
    card_id = int(callback.data.split(":")[2])
    removed = await remove_card(card_id, reseller_id)
    await callback.message.edit_text(f"کارت #{card_id} حذف شد ✅" if removed else "این کارت پیدا نشد.")
    await callback.answer()


# ---------- افزودن کارت (سه مرحله) ----------
@router.callback_query(F.data == "pm:add_card")
async def start_add_card(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerPaymentMethodStates.entering_card_number)
    await callback.message.answer("شماره کارت ۱۶ رقمی را وارد کنید (بدون فاصله یا خط تیره):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerPaymentMethodStates.entering_card_number)
async def receive_card_number(message: Message, state: FSMContext):
    card_number = message.text.replace("-", "").replace(" ", "").strip()
    if not (card_number.isdigit() and len(card_number) == 16):
        await message.answer("شماره کارت باید دقیقاً ۱۶ رقم باشد. دوباره وارد کنید:")
        return
    await state.update_data(card_number=card_number)
    await state.set_state(ResellerPaymentMethodStates.entering_card_holder)
    await message.answer("نام صاحب کارت را وارد کنید:")


@router.message(ResellerPaymentMethodStates.entering_card_holder)
async def receive_card_holder(message: Message, state: FSMContext):
    await state.update_data(card_holder_name=message.text.strip())
    await state.set_state(ResellerPaymentMethodStates.entering_bank_name)
    await message.answer("نام بانک را وارد کنید (یا برای رد شدن، خط تیره - بفرستید):")


@router.message(ResellerPaymentMethodStates.entering_bank_name)
async def receive_bank_name_and_save(message: Message, state: FSMContext, reseller_id: int):
    bank_name = message.text.strip()
    if bank_name == "-":
        bank_name = None
    data = await state.get_data()
    card_id = await add_card(reseller_id, data["card_number"], data["card_holder_name"], bank_name)
    formatted = format_card_number(data["card_number"])
    await message.answer(
        f"کارت جدید ثبت شد ✅ (شناسه #{card_id})\n💳 {formatted}\n👤 به‌نام: {data['card_holder_name']}"
        + (f"\n🏦 {bank_name}" if bank_name else ""),
        reply_markup=payment_methods_submenu(),
    )
    await state.clear()


# ---------- زرین‌پال شخصی نماینده ----------
@router.callback_query(F.data == "pm:set_zarinpal")
async def show_zarinpal(callback: CallbackQuery, state: FSMContext, reseller_id: int):
    merchant_id = await get_zarinpal_merchant(reseller_id)
    current = f"\n\nمرچنت‌کد فعلی: {merchant_id}" if merchant_id else ""
    await state.set_state(ResellerPaymentMethodStates.entering_zarinpal_merchant)
    await callback.message.answer(f"مرچنت‌کد زرین‌پال خودتان را وارد کنید:{current}\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerPaymentMethodStates.entering_zarinpal_merchant)
async def receive_zarinpal_merchant(message: Message, state: FSMContext, reseller_id: int):
    await set_zarinpal_merchant(reseller_id, message.text.strip())
    await message.answer(
        "مرچنت‌کد زرین‌پال شما ثبت شد ✅ و از حالا موقع خرید به مشتری لینک پرداخت آنلاین نشان داده می‌شود.",
        reply_markup=payment_methods_submenu(),
    )
    await state.clear()
