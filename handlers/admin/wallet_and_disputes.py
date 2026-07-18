"""
پنل مدیریت کل — تراکنش‌ها و بررسی درخواست‌های استرداد (بخش ۷ اسپک).
"""
from aiogram import Router, F
from aiogram.types import Message

from database.db import fetch_all
from services.wallet_service import confirm_topup
from services.dispute_service import approve_dispute, reject_dispute

router = Router(name="admin_wallet_and_disputes")


@router.message(F.text == "/pending_topups")
async def list_pending_topups(message: Message):
    rows = await fetch_all(
        "SELECT id, reseller_id, amount, method, created_at FROM wallet_transactions "
        "WHERE type = 'topup' AND status = 'pending'"
    )
    if not rows:
        await message.answer("درخواست شارژ در انتظاری وجود ندارد.")
        return
    for r in rows:
        await message.answer(
            f"#{r['id']} | نماینده {r['reseller_id']} | مبلغ {r['amount']:,.0f} | روش {r['method']}\n"
            f"برای تأیید: /confirm_topup {r['id']}"
        )


@router.message(F.text.startswith("/confirm_topup "))
async def confirm_topup_handler(message: Message):
    transaction_id = int(message.text.split()[1])
    await confirm_topup(transaction_id)
    await message.answer(f"تراکنش #{transaction_id} تأیید و موجودی نماینده افزایش یافت ✅")


@router.message(F.text == "/pending_disputes")
async def list_pending_disputes(message: Message):
    rows = await fetch_all(
        "SELECT id, order_id, reseller_id, reason FROM disputes WHERE review_status = 'pending'"
    )
    if not rows:
        await message.answer("درخواست استرداد در انتظاری وجود ندارد.")
        return
    for r in rows:
        await message.answer(
            f"#{r['id']} | سفارش {r['order_id']} | نماینده {r['reseller_id']}\nدلیل: {r['reason']}\n"
            f"تأیید: /approve_dispute {r['id']}\nرد: /reject_dispute {r['id']}"
        )


@router.message(F.text.startswith("/approve_dispute "))
async def approve_dispute_handler(message: Message):
    dispute_id = int(message.text.split()[1])
    await approve_dispute(dispute_id)
    await message.answer(f"درخواست استرداد #{dispute_id} تأیید شد و کمیسیون برگشت داده شد ✅")


@router.message(F.text.startswith("/reject_dispute "))
async def reject_dispute_handler(message: Message):
    dispute_id = int(message.text.split()[1])
    await reject_dispute(dispute_id)
    await message.answer(f"درخواست استرداد #{dispute_id} رد شد.")
