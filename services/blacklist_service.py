"""
لیست سیاه مشترک (بخش ۳ و ۷ اسپک، فاز ۲).
اگر مشتری به‌طور مکرر رسید فیک بفرستد (چند dispute تأییدشده)، به‌صورت خودکار
به لیست سیاه مشترک اضافه می‌شود.
"""
from database.db import fetch_one, fetch_all, execute

# تعداد dispute تأییدشده (رسید فیک ثابت‌شده) که باعث بلاک خودکار می‌شود
AUTO_BLACKLIST_THRESHOLD = 3


async def is_blacklisted(telegram_user_id: int, reseller_id: int | None = None) -> bool:
    global_row = await fetch_one(
        "SELECT id FROM blacklist WHERE telegram_user_id = %s AND is_global = TRUE",
        (telegram_user_id,),
    )
    if global_row:
        return True
    if reseller_id is not None:
        local_row = await fetch_one(
            "SELECT id FROM blacklist WHERE telegram_user_id = %s AND reported_by_reseller_id = %s",
            (telegram_user_id, reseller_id),
        )
        if local_row:
            return True
    return False


async def add_to_blacklist(telegram_user_id: int, reason: str, reseller_id: int | None, is_global: bool) -> None:
    await execute(
        "INSERT INTO blacklist (telegram_user_id, reported_by_reseller_id, reason, is_global) "
        "VALUES (%s, %s, %s, %s)",
        (telegram_user_id, reseller_id, reason, is_global),
    )


async def count_confirmed_fake_receipts(telegram_user_id: int) -> int:
    """تعداد dispute هایی که مدیر کل تأیید کرده و این مشتری صاحب سفارش بوده."""
    row = await fetch_one(
        "SELECT COUNT(*) AS c FROM disputes d "
        "JOIN orders o ON d.order_id = o.id "
        "JOIN customers cu ON o.customer_id = cu.id "
        "WHERE cu.telegram_user_id = %s AND d.review_status = 'approved'",
        (telegram_user_id,),
    )
    return row["c"]


async def maybe_auto_blacklist(telegram_user_id: int) -> bool:
    """
    بعد از تأیید هر dispute صدا زده می‌شود. اگر تعداد رسیدهای فیک تأییدشده به
    آستانه برسد، مشتری به‌صورت خودکار به لیست سیاه مشترک اضافه می‌شود.
    خروجی True یعنی همین الان بلاک شد.
    """
    count = await count_confirmed_fake_receipts(telegram_user_id)
    if count >= AUTO_BLACKLIST_THRESHOLD and not await is_blacklisted(telegram_user_id):
        await add_to_blacklist(
            telegram_user_id,
            reason=f"ارسال مکرر رسید فیک ({count} مورد تأییدشده)",
            reseller_id=None,
            is_global=True,
        )
        return True
    return False


async def list_blacklist() -> list[dict]:
    return await fetch_all("SELECT * FROM blacklist ORDER BY created_at DESC")
