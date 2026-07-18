"""
شارژ کیف‌پول با رمزارز (بخش ۳ اسپک، فاز ۲).
مدیر کل از پنل خودش نام رمزارز، آدرس، شبکه و نرخ تبدیل را تنظیم می‌کند.
تأیید واریز می‌تواند دستی یا با هش تراکنش باشد (در فاز ۲، دستی ساده‌تر و
امن‌تر است؛ تأیید خودکار با هش نیازمند اتصال به یک بلاک‌اکسپلورر است که خارج
از این اسکوپ می‌ماند و به‌عنوان TODO علامت‌گذاری شده).
"""
from decimal import Decimal
from database.db import fetch_all, fetch_one, execute
from services.wallet_service import request_topup


async def list_crypto_options() -> list[dict]:
    return await fetch_all("SELECT * FROM crypto_settings")


async def upsert_crypto_setting(coin_name: str, address: str, network: str, price: Decimal) -> None:
    existing = await fetch_one("SELECT id FROM crypto_settings WHERE coin_name = %s", (coin_name,))
    if existing:
        await execute(
            "UPDATE crypto_settings SET address = %s, network = %s, price = %s WHERE id = %s",
            (address, network, price, existing["id"]),
        )
    else:
        await execute(
            "INSERT INTO crypto_settings (coin_name, address, network, price) VALUES (%s, %s, %s, %s)",
            (coin_name, address, network, price),
        )


async def request_crypto_topup(reseller_id: int, coin_name: str, tx_hash: str, amount_toman_estimate: Decimal) -> int:
    """
    نماینده مبلغ رمزارز را واریز کرده و هش تراکنش را ارسال می‌کند. رکورد topup
    با status='pending' ثبت می‌شود و باید توسط مدیر کل دستی (یا در آینده با
    بررسی خودکار هش روی بلاک‌چین) تأیید شود.
    """
    return await request_topup(
        reseller_id, amount_toman_estimate, method="crypto", reference=f"{coin_name}:{tx_hash}"
    )
