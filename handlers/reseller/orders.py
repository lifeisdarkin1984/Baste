"""
هندلرهای مدیریت سفارش برای پنل نماینده/اپراتور (بخش ۴ و ۷ اسپک).
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import fetch_one, fetch_all
from services.order_service import confirm_order, reject_order, activate_order
from services.dispute_service import create_dispute
from services.customer_wallet_service import (
    confirm_topup,
    reject_topup,
    WalletTopupInsufficientCreditError,
)
from services.notifications import (
    notify_reseller_wallet_topup_insufficient_credit,
    notify_super_admin_wallet_topup_insufficient_credit,
)
from utils.states import ResellerDisputeStates
from utils.keyboards import activate_order_button, dispute_button, order_review_buttons, orders_refresh_button
from core.permissions_middleware import OrderActionPermissionMiddleware

router = Router(name="reseller_orders")

# فقط صاحب نماینده یا اپراتور فعال او مجاز به تأیید/رد/فعال‌سازی/استرداد هستند
# (بخش ۷ اسپک - اپراتور بدون دسترسی مالی/تنظیمات، ولی مجاز به این اکشن‌ها).
router.callback_query.middleware(OrderActionPermissionMiddleware())


@router.callback_query(F.data == "rmenu:orders")
async def list_pending_orders_cb(callback: CallbackQuery, reseller_id: int):
    rows = await fetch_all(
        "SELECT id, order_code, package_price, commission_amount, phone_number FROM orders "
        "WHERE reseller_id = %s AND status = 'awaiting_receipt_review'",
        (reseller_id,),
    )
    if not rows:
        await callback.message.answer("سفارش در انتظار بررسی‌ای وجود ندارد.", reply_markup=orders_refresh_button())
        await callback.answer()
        return
    for r in rows:
        await callback.message.answer(
            f"سفارش {r['order_code']} | قیمت بسته: {r['package_price']:,.0f} | "
            f"کمیسیون: {r['commission_amount']:,.0f}\n"
            f"شماره خط: {r['phone_number'] or 'ثبت نشده'}",
            reply_markup=order_review_buttons(r["id"]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("approve_receipt:"))
async def approve_receipt(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    await confirm_order(order_id)
    order = await fetch_one("SELECT phone_number FROM orders WHERE id = %s", (order_id,))
    phone_line = f"\nشماره خط: {order['phone_number']}" if order and order["phone_number"] else ""
    await callback.message.answer(
        f"رسید تأیید شد ✅.{phone_line}\nلطفاً بعد از فعال‌سازی دستی بسته، دکمه‌ی زیر را بزنید.",
        reply_markup=activate_order_button(order_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reject_receipt:"))
async def reject_receipt(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    await reject_order(order_id)
    await callback.message.answer(
        "رسید رد شد ❌. اگر فکر می‌کنید این رسید فیک بوده و کمیسیون باید برگردد، "
        "درخواست استرداد ثبت کنید:",
        reply_markup=dispute_button(order_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("activate_order:"))
async def activate(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    order = await activate_order(order_id)

    reseller = await fetch_one(
        "SELECT end_order_message FROM resellers WHERE id = %s", (order["reseller_id"],)
    )
    end_message = reseller["end_order_message"] or "بسته‌ی شما با موفقیت فعال شد. با تشکر از خرید شما 🙏"

    customer = await fetch_one(
        "SELECT telegram_user_id FROM customers WHERE id = %s", (order["customer_id"],)
    )

    # پیام پایان سفارش مستقیماً برای خود مشتری ارسال می‌شود. callback.bot همان
    # Bot instance مربوط به ربات این نماینده است چون هر ربات نماینده
    # Dispatcher/Bot اختصاصی خودش را دارد (core/bot_manager.py).
    if customer:
        try:
            await callback.bot.send_message(customer["telegram_user_id"], end_message)
        except Exception:
            pass  # مثلاً مشتری ربات را بلاک کرده؛ فعال‌سازی سفارش متوقف نمی‌شود

    await callback.message.answer(f"سفارش {order['order_code']} فعال شد و پیام پایان برای مشتری ارسال شد ✅")
    await callback.answer()


@router.callback_query(F.data.startswith("wallet_topup_confirm:"))
async def confirm_wallet_topup(callback: CallbackQuery):
    topup_id = int(callback.data.split(":")[1])
    try:
        await confirm_topup(topup_id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    except WalletTopupInsufficientCreditError as e:
        await notify_reseller_wallet_topup_insufficient_credit(callback.bot, e.reseller_id, e.topup_id)
        await notify_super_admin_wallet_topup_insufficient_credit(e.reseller_id, e.topup_id)
        await callback.message.answer(
            "کیف‌پول مشتری شارژ شد ✅ ولی کسر کمیسیون شما به‌خاطر کمبود اعتبار ناموفق بود؛ لطفاً کیف‌پول کمیسیون خود را شارژ کنید."
        )
        await callback.answer()
        return
    await callback.message.answer("افزایش موجودی کیف‌پول مشتری تأیید و اعمال شد ✅")
    await callback.answer()


@router.callback_query(F.data.startswith("wallet_topup_reject:"))
async def reject_wallet_topup(callback: CallbackQuery):
    topup_id = int(callback.data.split(":")[1])
    await reject_topup(topup_id)
    await callback.message.answer("درخواست افزایش موجودی رد شد ❌")
    await callback.answer()


@router.callback_query(F.data.startswith("open_dispute:"))
async def open_dispute(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    await state.update_data(dispute_order_id=order_id)
    await state.set_state(ResellerDisputeStates.entering_reason)
    await callback.message.answer("لطفاً دلیل درخواست استرداد را بنویسید (مثلاً: رسید جعلی بود):")
    await callback.answer()


@router.message(ResellerDisputeStates.entering_reason)
async def submit_dispute_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data["dispute_order_id"]
    order = await fetch_one("SELECT reseller_id FROM orders WHERE id = %s", (order_id,))

    await create_dispute(order_id, order["reseller_id"], message.text)
    await message.answer(
        "درخواست استرداد شما ثبت شد و برای بررسی مدیر کل ارسال شد. "
        "پس از بررسی، نتیجه به شما اطلاع داده خواهد شد."
    )
    await state.clear()
