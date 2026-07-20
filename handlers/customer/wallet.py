"""
کیف‌پول مشتری — نمایش موجودی و افزایش موجودی (کارت‌به‌کارت / زرین‌پال شخصی
نماینده)، همه با کیبورد پایین صفحه. تأیید افزایش موجودی دستی و توسط خود
نماینده/اپراتور انجام می‌شود (services/customer_wallet_service.py).
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database.db import fetch_one
from services.order_service import get_or_create_customer
from services.payment_methods_service import list_cards, get_zarinpal_merchant, format_card_number
from services.customer_wallet_service import get_wallet_balance, create_topup_request, attach_topup_receipt
from utils.states import CustomerWalletStates
from utils.keyboards import (
    customer_main_reply_keyboard,
    customer_wallet_menu_keyboard,
    customer_topup_method_keyboard,
    wallet_topup_review_buttons,
    CUSTOMER_WALLET_BUTTON_TEXT,
    CUSTOMER_TOPUP_BUTTON_TEXT,
    CUSTOMER_TOPUP_CARD_BUTTON_TEXT,
    CUSTOMER_TOPUP_ZARINPAL_BUTTON_TEXT,
    CUSTOMER_BACK_BUTTON_TEXT,
    CUSTOMER_BACK_TO_MENU_BUTTON_TEXT,
)

router = Router(name="customer_wallet")


async def _back_to_main_menu(message: Message, reseller_id: int, state: FSMContext):
    await state.clear()
    reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
    has_support = bool(reseller and reseller["support_contact"])
    await message.answer("منوی اصلی:", reply_markup=customer_main_reply_keyboard(has_support_contact=has_support))


@router.message(F.text == CUSTOMER_WALLET_BUTTON_TEXT)
async def show_wallet(message: Message, reseller_id: int, state: FSMContext):
    await state.clear()
    customer = await get_or_create_customer(reseller_id, message.from_user.id)
    balance = await get_wallet_balance(customer["id"])
    await message.answer(
        f"💰 موجودی کیف‌پول شما: {balance:,.0f} تومان\n\n"
        f"با شارژ کیف‌پول، خرید بسته‌های بعدی بدون نیاز به ارسال رسید و منتظر ماندن، آنی انجام می‌شود.",
        reply_markup=customer_wallet_menu_keyboard(),
    )


@router.message(F.text == CUSTOMER_TOPUP_BUTTON_TEXT)
async def start_topup(message: Message, reseller_id: int, state: FSMContext):
    active_cards = await list_cards(reseller_id, only_active=True)
    zarinpal_merchant = await get_zarinpal_merchant(reseller_id)

    if not active_cards and not zarinpal_merchant:
        await message.answer(
            "نماینده هنوز روش دریافت وجهی ثبت نکرده؛ برای شارژ کیف‌پول با پشتیبانی هماهنگ کنید.",
            reply_markup=customer_wallet_menu_keyboard(),
        )
        return

    await state.set_state(CustomerWalletStates.choosing_method)
    await message.answer(
        "روش واریز را انتخاب کنید:",
        reply_markup=customer_topup_method_keyboard(bool(active_cards), bool(zarinpal_merchant)),
    )


@router.message(CustomerWalletStates.choosing_method)
async def choose_topup_method(message: Message, reseller_id: int, state: FSMContext):
    if message.text == CUSTOMER_BACK_BUTTON_TEXT:
        await state.clear()
        await show_wallet(message, reseller_id, state)
        return

    if message.text not in (CUSTOMER_TOPUP_CARD_BUTTON_TEXT, CUSTOMER_TOPUP_ZARINPAL_BUTTON_TEXT):
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    method = "card" if message.text == CUSTOMER_TOPUP_CARD_BUTTON_TEXT else "zarinpal"
    await state.update_data(topup_method=method)
    await state.set_state(CustomerWalletStates.entering_amount)
    await message.answer("مبلغی که می‌خواهید به کیف‌پول اضافه کنید را وارد کنید (تومان، فقط عدد):")


@router.message(CustomerWalletStates.entering_amount)
async def receive_topup_amount(message: Message, reseller_id: int, state: FSMContext):
    try:
        amount = Decimal(message.text.replace(",", "").strip())
        if amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("لطفاً فقط یک عدد مثبت وارد کنید.")
        return

    data = await state.get_data()
    method = data["topup_method"]

    if method == "card":
        active_cards = await list_cards(reseller_id, only_active=True)
        payment_lines = []
        for c in active_cards:
            line = f"💳 {format_card_number(c['card_number'])} | به‌نام: {c['card_holder_name']}"
            if c["bank_name"]:
                line += f" | {c['bank_name']}"
            payment_lines.append(line)
        payment_info = "\n".join(payment_lines) if payment_lines else "کارتی ثبت نشده."
    else:
        payment_info = "🔗 پرداخت آنلاین از طریق زرین‌پال شخصی نماینده."

    customer = await get_or_create_customer(reseller_id, message.from_user.id)
    topup_id = await create_topup_request(reseller_id, customer["id"], amount, method)

    await state.update_data(topup_id=topup_id, amount=str(amount))
    await state.set_state(CustomerWalletStates.uploading_receipt)
    await message.answer(
        f"مبلغ {amount:,.0f} تومان را به روش زیر واریز کنید و سپس تصویر رسید را همینجا ارسال کنید:\n\n{payment_info}"
    )


@router.message(CustomerWalletStates.uploading_receipt, F.photo)
async def receive_topup_receipt(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    topup_id = data.get("topup_id")
    receipt_file_id = message.photo[-1].file_id
    await attach_topup_receipt(topup_id, receipt_file_id)

    reseller = await fetch_one(
        "SELECT telegram_numeric_id, support_contact FROM resellers WHERE id = %s", (reseller_id,)
    )
    await state.clear()
    has_support = bool(reseller and reseller["support_contact"])
    await message.answer(
        "رسید دریافت شد ✅ درخواست افزایش موجودی برای تأیید نماینده ارسال شد.",
        reply_markup=customer_main_reply_keyboard(has_support_contact=has_support),
    )

    if reseller and reseller["telegram_numeric_id"]:
        try:
            await message.bot.send_photo(
                reseller["telegram_numeric_id"],
                photo=receipt_file_id,
                caption=f"💳 درخواست افزایش موجودی کیف‌پول مشتری (شماره {topup_id}) به مبلغ "
                        f"{Decimal(data.get('amount', '0')):,.0f} تومان — رسید پیوست است.",
                reply_markup=wallet_topup_review_buttons(topup_id),
            )
        except Exception:
            pass
