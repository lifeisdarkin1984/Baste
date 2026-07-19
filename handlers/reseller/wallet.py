"""
هندلرهای کیف‌پول کمیسیون نماینده (نزد پلتفرم) — کارت‌به‌کارت + زرین‌پال + رمزارز.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import fetch_one
from services.wallet_service import request_topup
from services.zarinpal_service import create_payment_request, PLATFORM_ZARINPAL_MERCHANT_ID
from services.crypto_service import list_crypto_options, request_crypto_topup
from utils.states import ResellerTopupStates, ResellerCryptoTopupStates
from utils.keyboards import wallet_submenu, back_to_reseller_menu_button

router = Router(name="reseller_wallet")


@router.callback_query(F.data == "rmenu:wallet")
async def wallet_menu(callback: CallbackQuery, reseller_id: int):
    reseller = await fetch_one(
        "SELECT wallet_credit_balance, credit_limit_negative FROM resellers WHERE id = %s",
        (reseller_id,),
    )
    await callback.message.edit_text(
        f"💰 موجودی کیف‌پول کمیسیون: {reseller['wallet_credit_balance']:,.0f} تومان\n"
        f"سقف اعتبار منفی مجاز: {reseller['credit_limit_negative']:,.0f} تومان\n\n"
        f"⚠️ این کیف‌پول فقط برای کمیسیون پلتفرم است، نه گردش مالی فروش بسته.",
        reply_markup=wallet_submenu(),
    )
    await callback.answer()


# ---------- کارت‌به‌کارت ----------
@router.callback_query(F.data == "wallet:topup_card")
async def start_topup_card(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerTopupStates.entering_amount)
    await callback.message.answer("مبلغی که واریز کرده‌اید را وارد کنید (کارت‌به‌کارت):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerTopupStates.entering_amount)
async def receive_topup_amount(message: Message, state: FSMContext, reseller_id: int):
    try:
        amount = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return

    await request_topup(reseller_id, amount, method="card", reference=None)
    await message.answer(
        "درخواست شارژ کیف‌پول شما ثبت شد ✅ و برای تأیید دستی برای مدیر کل ارسال شد.",
        reply_markup=back_to_reseller_menu_button(),
    )
    await state.clear()


# ---------- زرین‌پال ----------
@router.callback_query(F.data == "wallet:topup_zarinpal")
async def start_topup_zarinpal(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerTopupStates.entering_zarinpal_amount)
    await callback.message.answer("مبلغ شارژ (تومان) را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerTopupStates.entering_zarinpal_amount)
async def receive_zarinpal_amount(message: Message, state: FSMContext, reseller_id: int):
    try:
        amount = int(message.text.replace(",", "").strip())
    except ValueError:
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return
    try:
        link, authority = await create_payment_request(
            PLATFORM_ZARINPAL_MERCHANT_ID,
            amount,
            f"شارژ کیف‌پول نماینده {reseller_id}",
            callback_url="https://example.com/zarinpal/callback",
        )
    except Exception as e:
        await message.answer(f"خطا در اتصال به زرین‌پال: {e}", reply_markup=back_to_reseller_menu_button())
        await state.clear()
        return
    await message.answer(
        f"برای پرداخت {amount:,.0f} تومان روی لینک زیر بزنید:\n{link}",
        reply_markup=back_to_reseller_menu_button(),
    )
    await state.clear()


# ---------- رمزارز ----------
@router.callback_query(F.data == "wallet:topup_crypto")
async def show_crypto_options(callback: CallbackQuery, state: FSMContext):
    options = await list_crypto_options()
    if not options:
        await callback.message.answer(
            "در حال حاضر روش شارژ رمزارزی توسط مدیر کل تنظیم نشده.",
            reply_markup=back_to_reseller_menu_button(),
        )
        await callback.answer()
        return
    lines = [
        f"{o['coin_name']} ({o['network']}) -> آدرس: {o['address']} | نرخ: {o['price']:,.0f} تومان"
        for o in options
    ]
    await callback.message.answer("\n".join(lines))
    await state.set_state(ResellerCryptoTopupStates.entering_coin)
    await callback.message.answer("نام کوینی که واریز کرده‌اید را وارد کنید (مثال: USDT):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCryptoTopupStates.entering_coin)
async def receive_crypto_coin(message: Message, state: FSMContext):
    await state.update_data(coin_name=message.text.strip())
    await state.set_state(ResellerCryptoTopupStates.entering_tx_hash)
    await message.answer("هش تراکنش را وارد کنید:")


@router.message(ResellerCryptoTopupStates.entering_tx_hash)
async def receive_crypto_tx_hash(message: Message, state: FSMContext):
    await state.update_data(tx_hash=message.text.strip())
    await state.set_state(ResellerCryptoTopupStates.entering_amount)
    await message.answer("مبلغ تخمینی (تومان) را وارد کنید:")


@router.message(ResellerCryptoTopupStates.entering_amount)
async def receive_crypto_amount_and_save(message: Message, state: FSMContext, reseller_id: int):
    try:
        amount = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("مبلغ باید عدد باشد.")
        return
    data = await state.get_data()
    await request_crypto_topup(reseller_id, data["coin_name"], data["tx_hash"], amount)
    await message.answer(
        "درخواست شارژ رمزارزی ثبت شد و برای تأیید مدیر کل ارسال شد.",
        reply_markup=back_to_reseller_menu_button(),
    )
    await state.clear()
