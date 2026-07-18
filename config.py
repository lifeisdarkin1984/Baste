"""
تنظیمات سراسری پروژه.
تمام مقادیر حساس (توکن ادمین کل، اطلاعات دیتابیس، کلید رمزنگاری) از Environment
Variables خوانده می‌شوند (نه هاردکد) طبق بخش ۱۰ اسپک.
توکن نماینده‌ها چون داینامیک هستند، در دیتابیس (رمزنگاری‌شده) نگه‌داری می‌شوند،
نه در env.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"متغیر محیطی الزامی تنظیم نشده: {name}")
    return value


class Config:
    # توکن ربات مدیر کل (Super Admin Bot)
    SUPER_ADMIN_BOT_TOKEN: str = _require("SUPER_ADMIN_BOT_TOKEN")

    # آیدی عددی تلگرام مدیر کل، برای هشدارهای خودکار (رسید تأییدنشده بعد از X ساعت و ...)
    SUPER_ADMIN_TELEGRAM_ID: int = int(_require("SUPER_ADMIN_TELEGRAM_ID"))

    # اطلاعات اتصال MySQL (افزونه‌ی Railway)
    DB_HOST: str = _require("DB_HOST")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = _require("DB_USER")
    DB_PASSWORD: str = _require("DB_PASSWORD")
    DB_NAME: str = _require("DB_NAME")
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "10"))

    # کلید رمزنگاری توکن ربات نماینده‌ها (Fernet key - باید ۳۲ بایت urlsafe base64 باشد)
    TOKEN_ENCRYPTION_KEY: str = _require("TOKEN_ENCRYPTION_KEY")

    # حداکثر تعداد سفارش هم‌زمان «در انتظار تأیید» به‌ازای هر مشتری
    MAX_PENDING_ORDERS_PER_CUSTOMER: int = int(os.getenv("MAX_PENDING_ORDERS_PER_CUSTOMER", "3"))

    # چند ساعت بعد از آپلود رسید، اگر «فعال شد» زده نشده بود، به مدیر کل هشدار بده
    PENDING_ACTIVATION_ALERT_HOURS: int = int(os.getenv("PENDING_ACTIVATION_ALERT_HOURS", "6"))
