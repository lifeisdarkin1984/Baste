"""
کدهای تخفیف درصدی (بخش ۷ اسپک، فاز ۲).
"""
from datetime import datetime
from decimal import Decimal
from database.db import fetch_one, execute


class InvalidDiscountCode(Exception):
    pass


async def validate_discount_code(reseller_id: int, code: str) -> dict:
    row = await fetch_one(
        "SELECT * FROM discount_codes WHERE reseller_id = %s AND code = %s AND is_active = TRUE",
        (reseller_id, code.strip().upper()),
    )
    if row is None:
        raise InvalidDiscountCode("کد تخفیف پیدا نشد یا غیرفعال است.")
    if row["expires_at"] and row["expires_at"] < datetime.now():
        raise InvalidDiscountCode("این کد تخفیف منقضی شده است.")
    if row["usage_limit"] and row["usage_count"] >= row["usage_limit"]:
        raise InvalidDiscountCode("سقف استفاده از این کد تخفیف پر شده است.")
    return row


def apply_discount(price: Decimal, discount_row: dict) -> Decimal:
    percent = Decimal(discount_row["percent"])
    return (price * (Decimal("100") - percent) / Decimal("100")).quantize(Decimal("1"))


async def increment_usage(discount_code_id: int) -> None:
    await execute(
        "UPDATE discount_codes SET usage_count = usage_count + 1 WHERE id = %s",
        (discount_code_id,),
    )
