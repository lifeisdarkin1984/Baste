"""
هندلرهای کیف‌پول کمیسیون نماینده — فاز ۱ فقط کارت‌به‌کارت (زرین‌پال/رمزارز فاز ۲).
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database.db import fetch_one
from services.wallet_service import request_topup
from utils.states import ResellerTopupStates

router = Router(name="reseller_wallet")


@router.message(F.text == "/wallet")
async def show_wallet(message: Message, reseller_id: int):
    reseller = await fetch_one(
        "SELECT wallet_credit_balance, credit_limit_negative FROM resellers WHERE id = %s",
        (reseller_id,),
    )
    await message.answer(
        f"💰 موجودی کیف‌پول کمیسیون: {reseller['wallet_credit_balance']:,.0f} تومان\n"
        f"سقف اعتبار منفی مجاز: {reseller['credit_limit_negative']:,.0f} تومان\n\n"
        f"⚠️ این کیف‌پول فقط برای کمیسیون پلتفرم است، نه گردش مالی فروش بسته."
    )


@router.message(F.text == "/topup")
async def start_topup(message: Message, state: FSMContext):
    await state.set_state(ResellerTopupStates.entering_amount)
    await message.answer("مبلغی که واریز کرده‌اید را وارد کنید (کارت‌به‌کارت):")


@router.message(ResellerTopupStates.entering_amount)
async def receive_topup_amount(message: Message, state: FSMContext, reseller_id: int):
    try:
        amount = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return

    await request_topup(reseller_id, amount, method="card", reference=None)
    await message.answer(
        "درخواست شارژ کیف‌پول شما ثبت شد ✅ و برای تأیید دستی برای مدیر کل ارسال شد."
    )
    await state.clear()
