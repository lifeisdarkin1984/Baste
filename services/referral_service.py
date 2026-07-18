"""
سیستم رفرال (بخش ۷ اسپک، فاز ۲).
هر نماینده می‌تواند رفرال را فعال/غیرفعال کند و درصد سود رفرال را تنظیم کند.
لینک رفرال شخصی هر مشتری به شکل start payload تلگرام پیاده می‌شود:
    https://t.me/<bot_username>?start=ref_<customer_id>
"""
from decimal import Decimal
from database.db import fetch_one, execute


async def get_referral_settings(reseller_id: int) -> dict:
    row = await fetch_one("SELECT * FROM referrals WHERE reseller_id = %s", (reseller_id,))
    if row is None:
        # پیش‌فرض: غیرفعال
        await execute(
            "INSERT INTO referrals (reseller_id, is_enabled, profit_percent) VALUES (%s, FALSE, 0)",
            (reseller_id,),
        )
        row = await fetch_one("SELECT * FROM referrals WHERE reseller_id = %s", (reseller_id,))
    return row


async def set_referral_enabled(reseller_id: int, enabled: bool) -> None:
    await get_referral_settings(reseller_id)
    await execute(
        "UPDATE referrals SET is_enabled = %s WHERE reseller_id = %s", (enabled, reseller_id)
    )


async def set_referral_profit_percent(reseller_id: int, percent: Decimal) -> None:
    await get_referral_settings(reseller_id)
    await execute(
        "UPDATE referrals SET profit_percent = %s WHERE reseller_id = %s", (percent, reseller_id)
    )


async def register_referral(reseller_id: int, referrer_customer_id: int, referred_customer_id: int) -> None:
    """وقتی مشتری جدید از طریق لینک رفرال یک مشتری دیگر وارد می‌شود، ثبت می‌شود."""
    if referrer_customer_id == referred_customer_id:
        return
    await execute(
        "INSERT IGNORE INTO referral_links (reseller_id, referrer_customer_id, referred_customer_id) "
        "VALUES (%s, %s, %s)",
        (reseller_id, referrer_customer_id, referred_customer_id),
    )


async def get_referrer_customer_id(reseller_id: int, referred_customer_id: int) -> int | None:
    row = await fetch_one(
        "SELECT referrer_customer_id FROM referral_links WHERE reseller_id = %s AND referred_customer_id = %s",
        (reseller_id, referred_customer_id),
    )
    return row["referrer_customer_id"] if row else None


def calculate_referral_profit(order_package_price: Decimal, profit_percent: Decimal) -> Decimal:
    """
    سود رفرال جدا از کمیسیون پلتفرم است و مستقیم بین نماینده و مشتری معرف حل
    می‌شود (طبق مدل اسنپ، پول فروش داخل سیستم گردش ندارد)؛ این تابع فقط برای
    گزارش/نمایش مبلغ سود محاسبه‌شده به نماینده استفاده می‌شود.
    """
    return (order_package_price * profit_percent / Decimal("100")).quantize(Decimal("1"))
