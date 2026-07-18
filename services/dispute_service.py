"""
سیستم استرداد/اختلاف رسمی (بخش ۳ اسپک) — به‌جای پیام دستی به پشتیبانی، یک
رکورد در جدول disputes ثبت می‌شود تا هم قابل پیگیری باشد هم گزارش‌گیری از
تعداد رسیدهای فیک هر نماینده/مشتری ممکن شود.
"""
from decimal import Decimal
from database.db import fetch_one, execute
from services.wallet_service import refund_commission
from services.blacklist_service import maybe_auto_blacklist


async def create_dispute(order_id: int, reseller_id: int, reason: str) -> int:
    """نماینده وقتی رسید را فیک/نامعتبر تشخیص می‌دهد، درخواست استرداد ثبت می‌کند."""
    await execute(
        "UPDATE orders SET status = 'refund_pending' WHERE id = %s",
        (order_id,),
    )
    return await execute(
        "INSERT INTO disputes (order_id, reseller_id, reason, review_status) "
        "VALUES (%s, %s, %s, 'pending')",
        (order_id, reseller_id, reason),
    )


async def approve_dispute(dispute_id: int) -> None:
    """مدیر کل درخواست را بررسی و تأیید می‌کند -> کمیسیون به اعتبار نماینده برمی‌گردد."""
    dispute = await fetch_one("SELECT * FROM disputes WHERE id = %s", (dispute_id,))
    if dispute is None:
        raise ValueError("درخواست استرداد پیدا نشد.")
    order = await fetch_one("SELECT * FROM orders WHERE id = %s", (dispute["order_id"],))

    await refund_commission(
        reseller_id=dispute["reseller_id"],
        amount=Decimal(order["commission_amount"]),
        order_code=order["order_code"],
    )
    await execute(
        "UPDATE disputes SET review_status = 'approved', refunded_amount = %s, reviewed_at = NOW() "
        "WHERE id = %s",
        (order["commission_amount"], dispute_id),
    )
    await execute(
        "UPDATE orders SET status = 'refunded' WHERE id = %s",
        (order["id"],),
    )

    customer = await fetch_one("SELECT telegram_user_id FROM customers WHERE id = %s", (order["customer_id"],))
    if customer:
        await maybe_auto_blacklist(customer["telegram_user_id"])


async def reject_dispute(dispute_id: int) -> None:
    """مدیر کل درخواست استرداد را رد می‌کند (رسید معتبر تشخیص داده شد)."""
    await execute(
        "UPDATE disputes SET review_status = 'rejected', reviewed_at = NOW() WHERE id = %s",
        (dispute_id,),
    )
