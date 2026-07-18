"""
پرداخت قبوض (فاز ۳ اسپک). فیچر سراسری است (global_settings.bills_payment_enabled)
و از orders جدا نگه داشته شده چون مبلغ/شناسه‌اش را خود مشتری وارد می‌کند.
"""
from datetime import datetime
from database.db import fetch_one, execute
from services.feature_flag_service import is_bills_payment_enabled


def _generate_bill_code(prefix: str) -> str:
    now = datetime.now()
    return f"{prefix}-B-{now.strftime('%y%m%d')}-{now.strftime('%H%M')}"


async def create_bill_payment_request(reseller_id: int, customer_id: int, bill_id_number: str, amount) -> dict:
    if not await is_bills_payment_enabled():
        raise PermissionError("قابلیت پرداخت قبوض در حال حاضر برای کل پلتفرم غیرفعال است.")

    reseller = await fetch_one("SELECT order_prefix FROM resellers WHERE id = %s", (reseller_id,))
    bill_code = _generate_bill_code(reseller["order_prefix"])

    bill_id = await execute(
        "INSERT INTO bill_payments (bill_code, reseller_id, customer_id, bill_id_number, amount, status) "
        "VALUES (%s, %s, %s, %s, %s, 'awaiting_receipt_review')",
        (bill_code, reseller_id, customer_id, bill_id_number, amount),
    )
    return await fetch_one("SELECT * FROM bill_payments WHERE id = %s", (bill_id,))


async def attach_receipt(bill_payment_id: int, receipt_file_id: str) -> None:
    await execute(
        "UPDATE bill_payments SET receipt_image = %s WHERE id = %s",
        (receipt_file_id, bill_payment_id),
    )


async def confirm_bill_payment(bill_payment_id: int) -> None:
    await execute(
        "UPDATE bill_payments SET status = 'confirmed' WHERE id = %s", (bill_payment_id,)
    )


async def reject_bill_payment(bill_payment_id: int) -> None:
    await execute(
        "UPDATE bill_payments SET status = 'rejected' WHERE id = %s", (bill_payment_id,)
    )


async def mark_bill_paid(bill_payment_id: int) -> None:
    """نماینده دستی قبض را پرداخت می‌کند (مشابه فعال‌سازی سفارش)."""
    await execute(
        "UPDATE bill_payments SET status = 'paid', paid_at = NOW() WHERE id = %s",
        (bill_payment_id,),
    )
