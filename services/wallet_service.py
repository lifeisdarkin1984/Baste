"""
سرویس کیف‌پول کمیسیون. طبق بخش ۱۱ اسپک، هر عملیات مالی باید در تراکنش اتمیک
انجام شود (SELECT ... FOR UPDATE + UPDATE در یک تراکنش) تا race condition
(مثلاً دو سفارش هم‌زمان که هر دو موجودی را چک می‌کنند) رخ ندهد.
یادآوری مهم: این کیف‌پول فقط برای کمیسیون پلتفرم است، نه گردش مالی فروش بسته.

--- تغییر نسبت به نسخه‌ی قبل (رفع باگ) ---
قبلاً deduct_commission همیشه تراکنش خودش را باز/بسته می‌کرد، که در order_service.py
باعث می‌شد کسر کمیسیون در یک تراکنش جدا از تغییر وضعیت سفارش انجام شود؛ اگر کسر
کمیسیون شکست می‌خورد (InsufficientCreditError)، سفارش از قبل با وضعیت
awaiting_receipt_review کامیت شده بود و سیستم در وضعیت متناقض می‌ماند.
حالا یک نسخه‌ی «tx» هم اضافه شده که یک کانکشن/کِرسر از بیرون می‌گیرد تا بتوان آن
را در همان تراکنش اتمیک تغییر وضعیت سفارش فراخوانی کرد.
"""
from decimal import Decimal
from database.db import transaction


class InsufficientCreditError(Exception):
    """وقتی کسر کمیسیون از سقف اعتبار منفی مجاز نماینده عبور کند."""
    pass


async def deduct_commission_in_tx(conn, reseller_id: int, amount: Decimal, order_code: str) -> None:
    """
    نسخه‌ی «تراکنش‌محور» کسر کمیسیون: به‌جای باز کردن تراکنش خودش، یک کانکشنی
    که از قبل در حال تراکنش است (conn) می‌گیرد. باید داخل یک
    `async with transaction() as conn:` بیرونی فراخوانی شود (مثلاً همراه با
    تغییر وضعیت سفارش) تا هر دو عملیات atomically با هم commit یا rollback شوند.
    در صورت کمبود اعتبار، InsufficientCreditError بالا می‌رود و چون داخل تراکنش
    بیرونی هستیم، کالر مسئول تصمیم‌گیری است (مثلاً catch کردن و ثبت وضعیت شکست
    به‌جای propagate کردن خام خطا، تا تراکنش commit شود نه rollback).
    """
    cur = await conn.cursor()
    await cur.execute(
        "SELECT wallet_credit_balance, credit_limit_negative FROM resellers "
        "WHERE id = %s FOR UPDATE",
        (reseller_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError(f"نماینده {reseller_id} پیدا نشد.")
    current_balance, credit_limit_negative = row
    new_balance = Decimal(current_balance) - Decimal(amount)

    if new_balance < -Decimal(credit_limit_negative):
        raise InsufficientCreditError(
            f"موجودی نماینده {reseller_id} پس از کسر کمیسیون از سقف اعتبار منفی "
            f"({credit_limit_negative}) عبور می‌کند."
        )

    await cur.execute(
        "UPDATE resellers SET wallet_credit_balance = %s WHERE id = %s",
        (new_balance, reseller_id),
    )
    await cur.execute(
        "INSERT INTO wallet_transactions (reseller_id, type, amount, status, reference) "
        "VALUES (%s, 'commission_deduction', %s, 'confirmed', %s)",
        (reseller_id, -Decimal(amount), order_code),
    )


async def deduct_commission(reseller_id: int, amount: Decimal, order_code: str) -> None:
    """
    نسخه‌ی مستقل (تراکنش خودش را باز/می‌بندد) — برای جاهایی که کسر کمیسیون
    نیازی به هماهنگی اتمیک با یک عملیات دیگر ندارد. برای فلوی سفارش از
    deduct_commission_in_tx داخل order_service.py استفاده می‌شود.
    """
    async with transaction() as conn:
        await deduct_commission_in_tx(conn, reseller_id, amount, order_code)


async def refund_commission(reseller_id: int, amount: Decimal, order_code: str) -> None:
    """برگشت کمیسیون بعد از تأیید مدیر کل روی یک درخواست استرداد (dispute)."""
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute(
            "SELECT wallet_credit_balance FROM resellers WHERE id = %s FOR UPDATE",
            (reseller_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError(f"نماینده {reseller_id} پیدا نشد.")
        new_balance = Decimal(row[0]) + Decimal(amount)

        await cur.execute(
            "UPDATE resellers SET wallet_credit_balance = %s WHERE id = %s",
            (new_balance, reseller_id),
        )
        await cur.execute(
            "INSERT INTO wallet_transactions (reseller_id, type, amount, status, reference) "
            "VALUES (%s, 'refund', %s, 'confirmed', %s)",
            (reseller_id, Decimal(amount), order_code),
        )


async def request_topup(reseller_id: int, amount: Decimal, method: str, reference: str | None) -> int:
    """
    ثبت درخواست شارژ (کارت‌به‌کارت با تأیید دستی مدیر کل، یا زرین‌پال/رمزارز که
    فاز ۲ است). وضعیت اولیه pending است.
    """
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute(
            "INSERT INTO wallet_transactions (reseller_id, type, amount, method, status, reference) "
            "VALUES (%s, 'topup', %s, %s, 'pending', %s)",
            (reseller_id, amount, method, reference),
        )
        return cur.lastrowid


async def confirm_topup(transaction_id: int) -> None:
    """مدیر کل شارژ کارت‌به‌کارت را دستی تأیید می‌کند -> موجودی نماینده افزایش می‌یابد."""
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute(
            "SELECT reseller_id, amount, status FROM wallet_transactions WHERE id = %s FOR UPDATE",
            (transaction_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError("تراکنش پیدا نشد.")
        reseller_id, amount, status = row
        if status != "pending":
            raise ValueError("این تراکنش قبلاً پردازش شده است.")

        await cur.execute(
            "UPDATE wallet_transactions SET status = 'confirmed' WHERE id = %s",
            (transaction_id,),
        )
        await cur.execute(
            "SELECT wallet_credit_balance FROM resellers WHERE id = %s FOR UPDATE",
            (reseller_id,),
        )
        balance_row = await cur.fetchone()
        new_balance = Decimal(balance_row[0]) + Decimal(amount)
        await cur.execute(
            "UPDATE resellers SET wallet_credit_balance = %s WHERE id = %s",
            (new_balance, reseller_id),
        )
