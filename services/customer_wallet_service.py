"""
سرویس کیف‌پول مشتری (بخش جدید — درخواست شما).

این کیف‌پول کاملاً جدا از دو کیف‌پول دیگر پروژه است:
  - services/wallet_service.py -> کیف‌پول کمیسیون نماینده نزد پلتفرم.
  - services/payment_methods_service.py -> کارت‌های شخصی نماینده برای دریافت وجه.

کیف‌پول مشتری یعنی: مشتری از قبل مبلغی به‌صورت کارت‌به‌کارت/زرین‌پال به حساب
شخصی نماینده واریز می‌کند (رسید می‌فرستد)، نماینده تأیید دستی می‌کند، و آن مبلغ
به‌صورت اعتبار داخل ربات (customers.wallet_balance) در اختیار مشتری قرار
می‌گیرد تا دفعات بعد بدون رسید/تأیید مرحله‌ای بسته بخرد (services/order_service.py
در create_order_paid_by_wallet این اعتبار را مصرف می‌کند).

طبق تصمیم محصول: همان لحظه که نماینده افزایش موجودی را تأیید می‌کند، درصد
کمیسیون نماینده (همان commission_percent که برای سفارش‌های عادی هم استفاده
می‌شود) از کیف‌پول کمیسیون او (wallet_credit_balance) کسر می‌شود — یعنی
نماینده انگار همان لحظه به مشتری «پیش‌فروش» کرده. به همین دلیل وقتی بعداً
مشتری از این اعتبار برای خرید بسته استفاده می‌کند، کمیسیون دوباره کسر
نمی‌شود (services/order_service.py -> create_order_paid_by_wallet).
"""
from decimal import Decimal

from database.db import fetch_one, execute, transaction
from services.wallet_service import deduct_commission_in_tx, InsufficientCreditError


class WalletTopupInsufficientCreditError(Exception):
    """کیف‌پول مشتری شارژ شد ولی کسر کمیسیون نماینده به‌خاطر کمبود اعتبار ناموفق بود."""
    def __init__(self, topup_id: int, reseller_id: int):
        self.topup_id = topup_id
        self.reseller_id = reseller_id
        super().__init__(
            f"شارژ کیف‌پول مشتری ثبت شد ولی کسر کمیسیون نماینده {reseller_id} به‌خاطر کمبود اعتبار ناموفق بود."
        )


async def get_wallet_balance(customer_id: int) -> Decimal:
    row = await fetch_one("SELECT wallet_balance FROM customers WHERE id = %s", (customer_id,))
    return Decimal(row["wallet_balance"]) if row else Decimal("0.00")


async def create_topup_request(reseller_id: int, customer_id: int, amount: Decimal, method: str) -> int:
    """ثبت درخواست افزایش موجودی با وضعیت pending (هنوز رسید ضمیمه نشده)."""
    return await execute(
        "INSERT INTO customer_wallet_topups (reseller_id, customer_id, amount, method, status) "
        "VALUES (%s, %s, %s, %s, 'pending')",
        (reseller_id, customer_id, amount, method),
    )


async def attach_topup_receipt(topup_id: int, receipt_file_id: str) -> None:
    await execute(
        "UPDATE customer_wallet_topups SET receipt_image = %s WHERE id = %s",
        (receipt_file_id, topup_id),
    )


async def get_topup(topup_id: int) -> dict | None:
    return await fetch_one("SELECT * FROM customer_wallet_topups WHERE id = %s", (topup_id,))


async def confirm_topup(topup_id: int) -> dict:
    """
    نماینده/اپراتور رسید افزایش موجودی را تأیید می‌کند:
      ۱. موجودی کیف‌پول مشتری افزایش می‌یابد.
      ۲. درصد کمیسیون نماینده از همان مبلغ، از کیف‌پول کمیسیونش کسر می‌شود.
    هر دو در یک تراکنش اتمیک (مطابق همان الگوی رفع‌باگ‌شده‌ی order_service.py:
    اگر کسر کمیسیون به‌خاطر کمبود اعتبار شکست بخورد، وضعیت روی
    confirmed_insufficient_credit ثبت می‌شود، نه اینکه سیستم در حالت متناقض بماند).
    """
    topup = await fetch_one("SELECT * FROM customer_wallet_topups WHERE id = %s", (topup_id,))
    if topup is None:
        raise ValueError("درخواست شارژ پیدا نشد.")
    if topup["status"] != "pending":
        raise ValueError("این درخواست قبلاً پردازش شده است.")

    reseller = await fetch_one(
        "SELECT commission_percent FROM resellers WHERE id = %s", (topup["reseller_id"],)
    )
    commission_amount = Decimal(topup["amount"]) * Decimal(reseller["commission_percent"]) / Decimal("100")

    insufficient_credit = False
    async with transaction() as conn:
        cur = await conn.cursor()

        await cur.execute(
            "UPDATE customers SET wallet_balance = wallet_balance + %s WHERE id = %s",
            (topup["amount"], topup["customer_id"]),
        )

        try:
            await deduct_commission_in_tx(
                conn, topup["reseller_id"], commission_amount, f"wallet-topup-{topup_id}"
            )
        except InsufficientCreditError:
            insufficient_credit = True
            await cur.execute(
                "UPDATE customer_wallet_topups SET status = 'confirmed_insufficient_credit', "
                "confirmed_at = NOW() WHERE id = %s",
                (topup_id,),
            )
        else:
            await cur.execute(
                "UPDATE customer_wallet_topups SET status = 'confirmed', confirmed_at = NOW() WHERE id = %s",
                (topup_id,),
            )

    if insufficient_credit:
        raise WalletTopupInsufficientCreditError(topup_id, topup["reseller_id"])

    return await fetch_one("SELECT * FROM customer_wallet_topups WHERE id = %s", (topup_id,))


async def reject_topup(topup_id: int) -> None:
    await execute(
        "UPDATE customer_wallet_topups SET status = 'rejected' WHERE id = %s",
        (topup_id,),
    )
