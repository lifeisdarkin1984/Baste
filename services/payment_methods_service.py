"""
«روش دریافت وجه از مشتری» — حساب/کارت شخصی خود نماینده که مشتری مستقیم به
آن پول واریز می‌کند. این کاملاً جدا از کیف‌پول کمیسیون پلتفرم
(services/wallet_service.py) است که فقط اعتبار پیش‌شارژشده‌ی داخل سیستم است.
"""
from database.db import fetch_all, fetch_one, execute


async def add_card(reseller_id: int, card_number: str, card_holder_name: str, bank_name: str | None = None) -> int:
    return await execute(
        "INSERT INTO reseller_payment_cards (reseller_id, card_number, card_holder_name, bank_name, is_active) "
        "VALUES (%s, %s, %s, %s, TRUE)",
        (reseller_id, card_number, card_holder_name, bank_name),
    )


async def list_cards(reseller_id: int, only_active: bool = False) -> list[dict]:
    if only_active:
        return await fetch_all(
            "SELECT * FROM reseller_payment_cards WHERE reseller_id = %s AND is_active = TRUE "
            "ORDER BY id",
            (reseller_id,),
        )
    return await fetch_all(
        "SELECT * FROM reseller_payment_cards WHERE reseller_id = %s ORDER BY id", (reseller_id,)
    )


async def toggle_card(card_id: int, reseller_id: int) -> bool | None:
    """کارت را روشن/خاموش می‌کند (فقط اگر متعلق به همین نماینده باشد). خروجی وضعیت جدید است."""
    row = await fetch_one(
        "SELECT is_active FROM reseller_payment_cards WHERE id = %s AND reseller_id = %s",
        (card_id, reseller_id),
    )
    if row is None:
        return None
    new_status = not row["is_active"]
    await execute(
        "UPDATE reseller_payment_cards SET is_active = %s WHERE id = %s", (new_status, card_id)
    )
    return new_status


async def remove_card(card_id: int, reseller_id: int) -> bool:
    row = await fetch_one(
        "SELECT id FROM reseller_payment_cards WHERE id = %s AND reseller_id = %s",
        (card_id, reseller_id),
    )
    if row is None:
        return False
    await execute("DELETE FROM reseller_payment_cards WHERE id = %s", (card_id,))
    return True


async def set_zarinpal_merchant(reseller_id: int, merchant_id: str) -> None:
    await execute(
        "UPDATE resellers SET zarinpal_merchant_id = %s WHERE id = %s", (merchant_id, reseller_id)
    )


async def get_zarinpal_merchant(reseller_id: int) -> str | None:
    row = await fetch_one("SELECT zarinpal_merchant_id FROM resellers WHERE id = %s", (reseller_id,))
    return row["zarinpal_merchant_id"] if row else None


def format_card_number(card_number: str) -> str:
    """
    خروجی برای نمایش تو پیام‌های فارسی (RTL):
      - داخل <code> می‌ذاریمش تا تلگرام رو عدد لمس‌کردنی/کپی‌شونده نشونش بده
        (چون ParseMode.HTML سراسریه).
      - یه \u200e (LRM) اول رشته می‌ذاریم تا تلگرام گروه‌های ۴رقمی رو، وسط
        متن فارسیِ راست‌به‌چپ، برعکس (از راست به چپ) نچینه.
    """
    grouped = " ".join(card_number[i:i + 4] for i in range(0, len(card_number), 4))
    return f"<code>\u200e{grouped}</code>"
