"""
درگاه آنلاین زرین‌پال — دو مصرف جدا در این پروژه دارد:
  ۱. شارژ کیف‌پول کمیسیون نماینده نزد پلتفرم (مرچنت پلتفرم، از env: ZARINPAL_MERCHANT_ID)
  ۲. دریافت مستقیم وجه بسته از مشتری به حساب خود نماینده (مرچنت اختصاصی هر
     نماینده، از ستون resellers.zarinpal_merchant_id — بخش «روش دریافت وجه از مشتری»)
برای همین merchant_id همیشه پارامتر صریح است، نه ثابت سراسری.
مستندات: https://www.zarinpal.com/docs/paymentGateway/
"""
import os
import aiohttp

PLATFORM_ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "")
ZARINPAL_REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
ZARINPAL_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
ZARINPAL_STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay/{authority}"


class ZarinpalError(Exception):
    pass


async def create_payment_request(merchant_id: str, amount_toman: int, description: str, callback_url: str) -> tuple[str, str]:
    """درخواست پرداخت می‌سازد و (لینک StartPay, authority) را برمی‌گرداند."""
    if not merchant_id:
        raise ZarinpalError("مرچنت‌کد زرین‌پال تنظیم نشده است.")

    payload = {
        "merchant_id": merchant_id,
        "amount": amount_toman * 10,  # زرین‌پال مبلغ را به ریال می‌گیرد
        "description": description,
        "callback_url": callback_url,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(ZARINPAL_REQUEST_URL, json=payload, timeout=15) as resp:
            data = await resp.json()

    if data.get("data", {}).get("code") != 100:
        raise ZarinpalError(f"خطا در ایجاد درخواست پرداخت زرین‌پال: {data}")

    authority = data["data"]["authority"]
    return ZARINPAL_STARTPAY_URL.format(authority=authority), authority


async def verify_payment(merchant_id: str, authority: str, amount_toman: int) -> bool:
    """بعد از بازگشت کاربر از درگاه، پرداخت را verify می‌کند."""
    payload = {
        "merchant_id": merchant_id,
        "amount": amount_toman * 10,
        "authority": authority,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(ZARINPAL_VERIFY_URL, json=payload, timeout=15) as resp:
            data = await resp.json()

    code = data.get("data", {}).get("code")
    return code in (100, 101)  # 101 یعنی قبلاً verify شده (idempotent)
