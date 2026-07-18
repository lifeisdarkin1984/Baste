"""
گزارش سود واقعی و خروجی اکسل (بخش ۷ اسپک، فاز ۲).
"""
from datetime import datetime, timedelta
from decimal import Decimal

from openpyxl import Workbook

from database.db import fetch_all, fetch_one


async def reseller_sales_summary(reseller_id: int, days: int = 30) -> dict:
    rows = await fetch_all(
        "SELECT o.*, p.cost_price FROM orders o JOIN packages p ON o.package_id = p.id "
        "WHERE o.reseller_id = %s AND o.status IN ('activated') "
        "AND o.created_at >= (NOW() - INTERVAL %s DAY)",
        (reseller_id, days),
    )
    total_sales = sum(Decimal(r["package_price"]) for r in rows)
    total_cost = sum(Decimal(r["cost_price"] or 0) for r in rows)
    total_commission_paid = sum(Decimal(r["commission_amount"]) for r in rows)
    real_profit = total_sales - total_cost - total_commission_paid
    return {
        "order_count": len(rows),
        "total_sales": total_sales,
        "total_cost": total_cost,
        "total_commission_paid": total_commission_paid,
        "real_profit": real_profit,
        "orders": rows,
    }


async def platform_wide_summary(days: int = 30) -> dict:
    """گزارش سود واقعی کل سیستم برای پنل مدیر کل (فروش کل / سود نمایندگان / کارمزد جمع‌شده)."""
    rows = await fetch_all(
        "SELECT o.*, p.cost_price FROM orders o JOIN packages p ON o.package_id = p.id "
        "WHERE o.status = 'activated' AND o.created_at >= (NOW() - INTERVAL %s DAY)",
        (days,),
    )
    total_sales = sum(Decimal(r["package_price"]) for r in rows)
    total_commission = sum(Decimal(r["commission_amount"]) for r in rows)
    total_cost = sum(Decimal(r["cost_price"] or 0) for r in rows)
    reseller_profit = total_sales - total_cost - total_commission
    return {
        "order_count": len(rows),
        "total_sales": total_sales,
        "total_commission_collected": total_commission,
        "total_reseller_profit": reseller_profit,
    }


def build_excel_report(orders: list[dict], filepath: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "گزارش فروش"
    ws.append(["شناسه سفارش", "تاریخ", "قیمت بسته", "کمیسیون", "وضعیت", "سفارش تستی"])
    for o in orders:
        ws.append([
            o["order_code"],
            o["created_at"].strftime("%Y-%m-%d %H:%M") if isinstance(o["created_at"], datetime) else str(o["created_at"]),
            float(o["package_price"]),
            float(o["commission_amount"]),
            o["status"],
            "بله" if o["is_test_order"] else "خیر",
        ])
    wb.save(filepath)
