"""
درخواست فعال‌سازی فیچر فروش شارژ/VPN توسط نماینده و تأیید/رد مدیر کل
(بخش ۵ و ۷ اسپک، فاز ۲). پرداخت قبوض فیچر سراسری است و اینجا نیست
(global_settings در schema.sql).
"""
from database.db import fetch_one, fetch_all, execute


async def request_feature(reseller_id: int, feature: str) -> None:
    existing = await fetch_one(
        "SELECT id, status FROM feature_flags WHERE reseller_id = %s AND feature = %s",
        (reseller_id, feature),
    )
    if existing:
        await execute(
            "UPDATE feature_flags SET status = 'pending', requested_at = NOW(), decided_at = NULL "
            "WHERE id = %s",
            (existing["id"],),
        )
    else:
        await execute(
            "INSERT INTO feature_flags (reseller_id, feature, status) VALUES (%s, %s, 'pending')",
            (reseller_id, feature),
        )


async def decide_feature(flag_id: int, approve: bool) -> None:
    status = "approved" if approve else "rejected"
    await execute(
        "UPDATE feature_flags SET status = %s, decided_at = NOW() WHERE id = %s",
        (status, flag_id),
    )


async def is_feature_enabled(reseller_id: int, feature: str) -> bool:
    row = await fetch_one(
        "SELECT status FROM feature_flags WHERE reseller_id = %s AND feature = %s",
        (reseller_id, feature),
    )
    return bool(row and row["status"] == "approved")


async def list_pending_features() -> list[dict]:
    return await fetch_all("SELECT * FROM feature_flags WHERE status = 'pending'")


async def is_bills_payment_enabled() -> bool:
    row = await fetch_one(
        "SELECT setting_value FROM global_settings WHERE setting_key = 'bills_payment_enabled'"
    )
    return bool(row and row["setting_value"] == "true")


async def set_bills_payment_enabled(enabled: bool) -> None:
    await execute(
        "UPDATE global_settings SET setting_value = %s WHERE setting_key = 'bills_payment_enabled'",
        ("true" if enabled else "false",),
    )
