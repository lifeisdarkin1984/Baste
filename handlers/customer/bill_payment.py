"""
پرداخت قبوض برای مشتری (فاز ۳ اسپک) — فیچر سراسری، فقط اگر مدیر کل فعال کرده باشد.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.order_service import get_or_create_customer
from services.bill_payment_service import create_bill_payment_request, attach_receipt

router = Router(name="customer_bill_payment")


class BillPaymentStates(StatesGroup):
    waiting_receipt = State()


@router.message(F.text.startswith("/pay_bill "))
async def start_bill_payment(message: Message, state: FSMContext, reseller_id: int):
    """فرمت: /pay_bill <شناسه قبض> <مبلغ>"""
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("فرمت درست: /pay_bill 12345678 150000")
        return
    _, bill_id_number, amount_str = parts
    try:
        amount = Decimal(amount_str)
    except InvalidOperation:
        await message.answer("مبلغ باید عدد باشد.")
        return

    customer = await get_or_create_customer(reseller_id, message.from_user.id)
    try:
        bill = await create_bill_payment_request(reseller_id, customer["id"], bill_id_number, amount)
    except PermissionError as e:
        await message.answer(f"⛔️ {e}")
        return

    await state.update_data(bill_payment_id=bill["id"])
    await state.set_state(BillPaymentStates.waiting_receipt)
    await message.answer(
        f"درخواست پرداخت قبض ثبت شد ✅\nشناسه: {bill['bill_code']}\n"
        f"لطفاً مبلغ را پرداخت کرده و تصویر رسید را ارسال کنید."
    )


@router.message(BillPaymentStates.waiting_receipt, F.photo)
async def receive_bill_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    await attach_receipt(data["bill_payment_id"], message.photo[-1].file_id)
    await message.answer("رسید دریافت شد ✅ در انتظار بررسی نماینده است.")
    await state.clear()
