"""
آمار پیشرفته مشتری (فاز ۳ اسپک).
"""
from decimal import Decimal
from database.db import fetch_all, fetch_one


async def top_customers(reseller_id: int, limit: int = 10) -> list[dict]:
    return await fetch_all(
        "SELECT cu.telegram_user_id, COUNT(o.id) AS order_count, "
        "SUM(o.package_price) AS total_spent "
        "FROM customers cu JOIN orders o ON o.customer_id = cu.id "
        "WHERE cu.reseller_id = %s AND o.status = 'activated' "
        "GROUP BY cu.id ORDER BY total_spent DESC LIMIT %s",
        (reseller_id, limit),
    )


async def repeat_customer_rate(reseller_id: int) -> dict:
    row = await fetch_one(
        "SELECT COUNT(*) AS total_customers, "
        "SUM(CASE WHEN order_count > 1 THEN 1 ELSE 0 END) AS repeat_customers FROM ("
        "  SELECT cu.id, COUNT(o.id) AS order_count FROM customers cu "
        "  JOIN orders o ON o.customer_id = cu.id "
        "  WHERE cu.reseller_id = %s AND o.status = 'activated' "
        "  GROUP BY cu.id"
        ") AS sub",
        (reseller_id,),
    )
    total = row["total_customers"] or 0
    repeat = row["repeat_customers"] or 0
    rate = (Decimal(repeat) / Decimal(total) * 100) if total else Decimal("0")
    return {"total_customers": total, "repeat_customers": repeat, "repeat_rate_percent": rate}


async def average_order_value(reseller_id: int) -> Decimal:
    row = await fetch_one(
        "SELECT AVG(package_price) AS avg_price FROM orders "
        "WHERE reseller_id = %s AND status = 'activated'",
        (reseller_id,),
    )
    return Decimal(row["avg_price"]) if row and row["avg_price"] is not None else Decimal("0")
