"""
بررسی درخواست‌های پرداخت قبض توسط نماینده/اپراتور (فاز ۳ اسپک).
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from database.db import fetch_all
from services.bill_payment_service import confirm_bill_payment, reject_bill_payment, mark_bill_paid
from core.permissions_middleware import OrderActionPermissionMiddleware
from utils.keyboards import bill_decision_buttons, bill_mark_paid_button, back_to_reseller_menu_button

router = Router(name="reseller_bill_payment")
router.callback_query.middleware(OrderActionPermissionMiddleware())


@router.callback_query(F.data == "rmenu:bills")
async def list_pending_bills_cb(callback: CallbackQuery, reseller_id: int):
    rows = await fetch_all(
        "SELECT * FROM bill_payments WHERE reseller_id = %s AND status = 'awaiting_receipt_review'",
        (reseller_id,),
    )
    if not rows:
        await callback.message.answer("درخواست پرداخت قبض در انتظاری وجود ندارد.", reply_markup=back_to_reseller_menu_button())
        await callback.answer()
        return
    for r in rows:
        await callback.message.answer(
            f"قبض {r['bill_code']} | شناسه: {r['bill_id_number']} | مبلغ: {r['amount']:,.0f}",
            reply_markup=bill_decision_buttons(r["id"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bill_confirm:"))
async def confirm_bill_cb(callback: CallbackQuery):
    bill_id = int(callback.data.split(":")[1])
    await confirm_bill_payment(bill_id)
    await callback.message.edit_text(f"قبض #{bill_id} تأیید شد.")
    await callback.message.answer("بعد از پرداخت واقعی قبض، دکمه‌ی زیر را بزنید:", reply_markup=bill_mark_paid_button(bill_id))
    await callback.answer()


@router.callback_query(F.data.startswith("bill_reject:"))
async def reject_bill_cb(callback: CallbackQuery):
    bill_id = int(callback.data.split(":")[1])
    await reject_bill_payment(bill_id)
    await callback.message.edit_text(f"قبض #{bill_id} رد شد.")
    await callback.answer()


@router.callback_query(F.data.startswith("bill_paid:"))
async def mark_paid_cb(callback: CallbackQuery):
    bill_id = int(callback.data.split(":")[1])
    await mark_bill_paid(bill_id)
    await callback.message.edit_text(f"قبض #{bill_id} به‌عنوان پرداخت‌شده ثبت شد ✅")
    await callback.answer()
