"""
بررسی منطقی قیمت (Sanity Check) — بخش ۵ اسپک.
جلوگیری از خطای تایپی نماینده (مثلاً نوشتن ۱۰۰ به‌جای ۱۰۰,۰۰۰).
"""
from decimal import Decimal
from database.db import fetch_one


async def get_min_sane_price(operator_name: str) -> Decimal | None:
    row = await fetch_one(
        "SELECT min_sane_price FROM category_price_floors WHERE operator_name = %s",
        (operator_name,),
    )
    return Decimal(row["min_sane_price"]) if row else None


async def is_price_suspicious(operator_name: str, sale_price: Decimal) -> bool:
    """
    اگر قیمت وارد شده کمتر از حداقل قیمت منطقی همان اپراتور/دسته باشد True
    برمی‌گرداند. در این حالت handler باید پیام هشدار زیر را نشان دهد و قبل از
    ثبت نهایی، تأیید صریح نماینده را بگیرد:
    «⚠️ این قیمت غیرعادی به نظر می‌رسه، مطمئنی؟»
    """
    min_price = await get_min_sane_price(operator_name)
    if min_price is None:
        return False  # برای این اپراتور آستانه‌ای تعریف نشده
    return Decimal(sale_price) < min_price
