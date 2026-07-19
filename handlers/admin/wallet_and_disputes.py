"""
پنل مدیریت کل — تراکنش‌ها و بررسی درخواست‌های استرداد (بخش ۷ اسپک) — فاز ۲.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from database.db import fetch_all
from services.wallet_service import confirm_topup
from services.dispute_service import approve_dispute, reject_dispute
from utils.keyboards import (
    admin_wallet_submenu,
    topup_confirm_button,
    dispute_decision_buttons,
    back_to_admin_menu_button,
)

router = Router(name="admin_wallet_and_disputes")


@router.callback_query(F.data == "amenu:wallet")
async def wallet_menu(callback: CallbackQuery):
    await callback.message.edit_text("💰 کیف‌پول و استرداد", reply_markup=admin_wallet_submenu())
    await callback.answer()


@router.callback_query(F.data == "amenu:wallet:topups")
async def list_pending_topups_cb(callback: CallbackQuery):
    rows = await fetch_all(
        "SELECT id, reseller_id, amount, method, created_at FROM wallet_transactions "
        "WHERE type = 'topup' AND status = 'pending'"
    )
    if not rows:
        await callback.message.answer("درخواست شارژ در انتظاری وجود ندارد.", reply_markup=back_to_admin_menu_button())
        await callback.answer()
        return
    for r in rows:
        await callback.message.answer(
            f"#{r['id']} | نماینده {r['reseller_id']} | مبلغ {r['amount']:,.0f} | روش {r['method']}",
            reply_markup=topup_confirm_button(r["id"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_confirm:"))
async def confirm_topup_cb(callback: CallbackQuery):
    transaction_id = int(callback.data.split(":")[1])
    await confirm_topup(transaction_id)
    await callback.message.edit_text(f"تراکنش #{transaction_id} تأیید و موجودی نماینده افزایش یافت ✅")
    await callback.answer()


@router.callback_query(F.data == "amenu:wallet:disputes")
async def list_pending_disputes_cb(callback: CallbackQuery):
    rows = await fetch_all(
        "SELECT id, order_id, reseller_id, reason FROM disputes WHERE review_status = 'pending'"
    )
    if not rows:
        await callback.message.answer("درخواست استرداد در انتظاری وجود ندارد.", reply_markup=back_to_admin_menu_button())
        await callback.answer()
        return
    for r in rows:
        await callback.message.answer(
            f"#{r['id']} | سفارش {r['order_id']} | نماینده {r['reseller_id']}\nدلیل: {r['reason']}",
            reply_markup=dispute_decision_buttons(r["id"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("dispute_approve:"))
async def approve_dispute_cb(callback: CallbackQuery):
    dispute_id = int(callback.data.split(":")[1])
    await approve_dispute(dispute_id)
    await callback.message.edit_text(f"درخواست استرداد #{dispute_id} تأیید شد و کمیسیون برگشت داده شد ✅")
    await callback.answer()


@router.callback_query(F.data.startswith("dispute_reject:"))
async def reject_dispute_cb(callback: CallbackQuery):
    dispute_id = int(callback.data.split(":")[1])
    await reject_dispute(dispute_id)
    await callback.message.edit_text(f"درخواست استرداد #{dispute_id} رد شد.")
    await callback.answer()
