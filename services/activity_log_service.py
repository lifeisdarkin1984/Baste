"""
لاگ کامل فعالیت‌ها (بخش ۶ و ۷ اسپک) — قابل فیلتر بر اساس نماینده از پنل مدیر کل.
"""
import json
from database.db import execute, fetch_all


async def log_activity(actor_type: str, actor_id: int, action: str,
                        reseller_id: int | None = None, details: dict | None = None) -> None:
    await execute(
        "INSERT INTO activity_logs (actor_type, actor_id, reseller_id, action, details) "
        "VALUES (%s, %s, %s, %s, %s)",
        (actor_type, actor_id, reseller_id, action, json.dumps(details or {}, ensure_ascii=False)),
    )


async def get_logs(reseller_id: int | None = None, limit: int = 50) -> list[dict]:
    if reseller_id is not None:
        return await fetch_all(
            "SELECT * FROM activity_logs WHERE reseller_id = %s ORDER BY created_at DESC LIMIT %s",
            (reseller_id, limit),
        )
    return await fetch_all(
        "SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT %s", (limit,)
    )
