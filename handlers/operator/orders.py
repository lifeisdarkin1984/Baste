"""
پنل اپراتور نماینده (زیرادمین) — بخش ۷ اسپک.
فقط مشاهده و تأیید/رد سفارش + دکمه‌ی «فعال شد».
هیچ دسترسی به کیف‌پول/تنظیمات/گزارش سود ندارد چون آن هندلرها در روترهای جدا
(handlers/reseller/wallet.py و catalog.py) هستند و برای این روتر اصلاً ثبت
نمی‌شوند.

اکشن‌های واقعی تأیید/رد/فعال‌سازی در handlers/reseller/orders.py تعریف
شده‌اند و مشترک بین صاحب نماینده و اپراتور فعال او هستند؛ مجوز با
core/permissions_middleware.py (OrderActionPermissionMiddleware) کنترل
می‌شود که هم صاحب نماینده و هم اپراتور فعال (از جدول reseller_operators) را
مجاز می‌داند و بقیه را رد می‌کند.

نکته‌ی فاز ۴: قبلاً این لیست فقط متن بود و دکمه‌ی تأیید/رد نداشت — یعنی
اپراتور باید آیدی سفارش را از متن می‌خواند و دستی تایپ می‌کرد. الان از همون
دکمه‌های order_review_buttons استفاده می‌کند (همان‌هایی که در
handlers/reseller/orders.py پردازش می‌شوند).
"""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database.db import fetch_one, fetch_all
from utils.keyboards import order_review_buttons

router = Router(name="operator_orders")


async def is_active_operator(reseller_id: int, telegram_user_id: int) -> bool:
    row = await fetch_one(
        "SELECT id FROM reseller_operators WHERE reseller_id = %s AND telegram_user_id = %s "
        "AND status = 'active'",
        (reseller_id, telegram_user_id),
    )
    return row is not None


@router.message(Command("pending_orders"))
async def list_pending_orders(message: Message, reseller_id: int):
    """اپراتور/نماینده می‌تواند سفارش‌های در انتظار بررسی را ببیند.
    (نکته: پنل نماینده همین لیست را با دکمه‌ی 🧾 سفارش‌ها از منو هم دارد؛
    این دستور مخصوص اپراتوری است که هنوز عضو منوی کامل نماینده نیست.)"""
    if not (
        await is_active_operator(reseller_id, message.from_user.id)
        or (await fetch_one("SELECT telegram_numeric_id FROM resellers WHERE id = %s", (reseller_id,)))
        .get("telegram_numeric_id") == message.from_user.id
    ):
        await message.answer("⛔️ شما مجاز به مشاهده‌ی این بخش نیستید.")
        return

    rows = await fetch_all(
        "SELECT id, order_code, package_price, commission_amount FROM orders "
        "WHERE reseller_id = %s AND status = 'awaiting_receipt_review'",
        (reseller_id,),
    )
    if not rows:
        await message.answer("سفارش در انتظار بررسی‌ای وجود ندارد.")
        return
    for r in rows:
        await message.answer(
            f"سفارش {r['order_code']} | قیمت بسته: {r['package_price']:,.0f} | "
            f"کمیسیون: {r['commission_amount']:,.0f}",
            reply_markup=order_review_buttons(r["id"]),
        )
