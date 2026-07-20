"""
هشدارهای فوری به نماینده و مدیر کل — فایل جدید برای رفع باگ:
قبلاً وقتی کسر کمیسیون به‌خاطر کمبود اعتبار شکست می‌خورد، هیچ پیامی به کسی
ارسال نمی‌شد (فقط کامنتی در کد بود که ادعا می‌کرد این کار انجام می‌شود).
"""
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config
from database.db import fetch_one

logger = logging.getLogger("notifications")


async def notify_reseller_insufficient_credit(reseller_bot: Bot, reseller_id: int, order_code: str) -> None:
    """
    از همان بات نماینده (که هندلر با آن در حال اجراست) برای خود صاحب نماینده
    پیام می‌فرستد. نیازی به توکن/بات جدا نیست چون هر نماینده بات مستقل خودش
    را دارد.
    """
    reseller = await fetch_one(
        "SELECT telegram_numeric_id, bot_username FROM resellers WHERE id = %s",
        (reseller_id,),
    )
    if reseller is None:
        logger.warning(f"نماینده {reseller_id} برای اطلاع‌رسانی کمبود اعتبار پیدا نشد.")
        return
    try:
        await reseller_bot.send_message(
            reseller["telegram_numeric_id"],
            f"⚠️ سفارش {order_code} دریافت شد ولی به‌خاطر کمبود اعتبار کیف‌پول شما، "
            f"کمیسیون کسر نشد. لطفاً هرچه سریع‌تر کیف‌پول خود را شارژ کنید تا سفارش "
            f"پردازش شود؛ در غیر این صورت سفارش در وضعیت معلق باقی می‌ماند.",
        )
    except Exception:
        logger.exception(f"ارسال هشدار کمبود اعتبار به نماینده {reseller_id} ناموفق بود.")


async def notify_reseller_wallet_topup_insufficient_credit(reseller_bot: Bot, reseller_id: int, topup_id: int) -> None:
    """کیف‌پول مشتری شارژ شد، ولی کسر کمیسیون نماینده از افزایش موجودی ناموفق بود."""
    reseller = await fetch_one(
        "SELECT telegram_numeric_id FROM resellers WHERE id = %s", (reseller_id,)
    )
    if reseller is None:
        logger.warning(f"نماینده {reseller_id} برای اطلاع‌رسانی کمبود اعتبار (شارژ کیف‌پول مشتری) پیدا نشد.")
        return
    try:
        await reseller_bot.send_message(
            reseller["telegram_numeric_id"],
            f"⚠️ افزایش موجودی کیف‌پول مشتری (درخواست شماره {topup_id}) تأیید و برای مشتری اعمال شد، "
            f"ولی کمیسیون آن به‌خاطر کمبود اعتبار کیف‌پول شما کسر نشد. لطفاً هرچه سریع‌تر کیف‌پول کمیسیون "
            f"خود را شارژ کنید.",
        )
    except Exception:
        logger.exception(f"ارسال هشدار کمبود اعتبار (شارژ کیف‌پول مشتری) به نماینده {reseller_id} ناموفق بود.")


async def notify_super_admin_wallet_topup_insufficient_credit(reseller_id: int, topup_id: int) -> None:
    admin_bot = Bot(
        token=Config.SUPER_ADMIN_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await admin_bot.send_message(
            Config.SUPER_ADMIN_TELEGRAM_ID,
            f"🚨 افزایش موجودی کیف‌پول مشتری (درخواست {topup_id}, نماینده {reseller_id}) تأیید شد ولی "
            f"کمیسیون آن به‌خاطر کمبود اعتبار نماینده کسر نشد.",
        )
    except Exception:
        logger.exception("ارسال هشدار کمبود اعتبار (شارژ کیف‌پول مشتری) به مدیر کل ناموفق بود.")
    finally:
        await admin_bot.session.close()


async def notify_super_admin_insufficient_credit(reseller_id: int, order_code: str) -> None:
    """
    یک بات موقت با توکن مدیر کل می‌سازد، پیام هشدار را می‌فرستد و سشن را می‌بندد.
    چون این مسیر فقط در حالت خطا (کمبود اعتبار نماینده) اجرا می‌شود، فرکانس آن
    کم است و ساخت بات موقت مشکلی ایجاد نمی‌کند.
    """
    admin_bot = Bot(
        token=Config.SUPER_ADMIN_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await admin_bot.send_message(
            Config.SUPER_ADMIN_TELEGRAM_ID,
            f"🚨 سفارش {order_code} (نماینده {reseller_id}) به‌خاطر کمبود اعتبار "
            f"کیف‌پول نماینده، کمیسیون‌اش کسر نشد و سفارش معلق مانده است.",
        )
    except Exception:
        logger.exception("ارسال هشدار کمبود اعتبار به مدیر کل ناموفق بود.")
    finally:
        await admin_bot.session.close()
