"""
بررسی درخواست‌های پرداخت قبض توسط نماینده/اپراتور (فاز ۳ اسپک).
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from database.db import fetch_all
from services.bill_payment_service import confirm_bill_payment, reject_bill_payment, mark_bill_paid
from core.permissions_middleware import OrderActionPermissionMiddleware

router = Router(name="reseller_bill_payment")
router.message.middleware(OrderActionPermissionMiddleware())


@router.message(Command("pending_bills"))
async def list_pending_bills(message: Message, reseller_id: int):
    rows = await fetch_all(
        "SELECT * FROM bill_payments WHERE reseller_id = %s AND status = 'awaiting_receipt_review'",
        (reseller_id,),
    )
    if not rows:
        await message.answer("درخواست پرداخت قبض در انتظاری وجود ندارد.")
        return
    for r in rows:
        await message.answer(
            f"قبض {r['bill_code']} | شناسه: {r['bill_id_number']} | مبلغ: {r['amount']:,.0f}\n"
            f"تأیید: /confirm_bill {r['id']}\nرد: /reject_bill {r['id']}"
        )


@router.message(F.text.startswith("/confirm_bill "))
async def confirm_bill(message: Message):
    bill_id = int(message.text.split()[1])
    await confirm_bill_payment(bill_id)
    await message.answer(f"قبض #{bill_id} تأیید شد. بعد از پرداخت واقعی: /mark_bill_paid {bill_id}")


@router.message(F.text.startswith("/reject_bill "))
async def reject_bill(message: Message):
    bill_id = int(message.text.split()[1])
    await reject_bill_payment(bill_id)
    await message.answer(f"قبض #{bill_id} رد شد.")


@router.message(F.text.startswith("/mark_bill_paid "))
async def mark_paid(message: Message):
    bill_id = int(message.text.split()[1])
    await mark_bill_paid(bill_id)
    await message.answer(f"قبض #{bill_id} به‌عنوان پرداخت‌شده ثبت شد ✅")
