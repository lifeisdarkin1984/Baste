"""
سرویس فلوی سفارش (بخش ۴ اسپک).

نکات کلیدی که این فایل پیاده‌سازی می‌کند:
  - شناسه یکتای سفارش با پیشوند اختصاصی هر نماینده: <PREFIX>-YYMMDD-HHMM
  - سقف ۳ سفارش هم‌زمان «در انتظار تأیید» به‌ازای هر مشتری (ضد اسپم رسید فیک)
  - کسر خودکار کمیسیون دقیقاً در لحظه‌ی آپلود رسید (مگر در حالت تست)
  - افزایش شمارنده‌ی سفارش تستی و خروج خودکار از حالت تست بعد از N سفارش موفق

--- تغییر نسبت به نسخه‌ی قبل (رفع باگ) ---
قبلاً تغییر وضعیت سفارش به awaiting_receipt_review و کسر کمیسیون در دو تراکنش
جدا انجام می‌شد. اگر کسر کمیسیون با InsufficientCreditError شکست می‌خورد،
وضعیت سفارش از قبل commit شده بود و سیستم در وضعیت متناقض (سفارش «در انتظار
بررسی» بدون کسر واقعی کمیسیون، بدون اطلاع به کسی) می‌ماند.
حالا هر دو عملیات در یک تراکنش اتمیک واحد انجام می‌شوند: اگر اعتبار کافی نبود،
وضعیت سفارش روی failed_insufficient_credit ثبت می‌شود (نه awaiting_receipt_review)
و این وضعیت با موفقیت commit می‌شود؛ سپس یک استثنا به لایه‌ی هندلر بالا می‌رود
تا هم به مشتری هم به نماینده/مدیر کل اطلاع داده شود.

نکته‌ی دیتابیس لازم: مقدار 'failed_insufficient_credit' باید به ستون ENUM
`orders.status` اضافه شود (فایل migration پیوست را اجرا کنید).
"""
from datetime import datetime
from decimal import Decimal

from config import Config
from database.db import fetch_one, fetch_all, execute, transaction
from services.wallet_service import deduct_commission_in_tx, InsufficientCreditError
from services.blacklist_service import is_blacklisted


class PendingOrderLimitExceeded(Exception):
    """مشتری به سقف مجاز سفارش‌های «در انتظار تأیید» رسیده است."""
    pass


class CustomerBlacklistedError(Exception):
    """مشتری در لیست سیاه (مشترک یا مخصوص این نماینده) است."""
    pass


class OrderInsufficientCreditError(Exception):
    """
    کسر کمیسیون به‌خاطر کمبود اعتبار نماینده انجام نشد. برخلاف
    InsufficientCreditError خام، این خطا با اطلاعات سفارش/نماینده همراه است
    تا هندلر بتواند به نماینده و مدیر کل اطلاع دهد.
    """
    def __init__(self, order_id: int, reseller_id: int, order_code: str):
        self.order_id = order_id
        self.reseller_id = reseller_id
        self.order_code = order_code
        super().__init__(
            f"کسر کمیسیون سفارش {order_code} به‌خاطر کمبود اعتبار نماینده {reseller_id} ناموفق بود."
        )


async def get_or_create_customer(reseller_id: int, telegram_user_id: int) -> dict:
    row = await fetch_one(
        "SELECT * FROM customers WHERE reseller_id = %s AND telegram_user_id = %s",
        (reseller_id, telegram_user_id),
    )
    if row:
        return row
    customer_id = await execute(
        "INSERT INTO customers (reseller_id, telegram_user_id) VALUES (%s, %s)",
        (reseller_id, telegram_user_id),
    )
    return await fetch_one("SELECT * FROM customers WHERE id = %s", (customer_id,))


async def count_pending_orders(customer_id: int) -> int:
    row = await fetch_one(
        "SELECT COUNT(*) AS c FROM orders WHERE customer_id = %s "
        "AND status = 'awaiting_receipt_review'",
        (customer_id,),
    )
    return row["c"]


def _generate_order_code(prefix: str) -> str:
    now = datetime.now()
    return f"{prefix}-{now.strftime('%y%m%d')}-{now.strftime('%H%M')}"


async def create_order(reseller_id: int, package_id: int, customer_id: int) -> dict:
    """
    مرحله‌ی ۱-۲ فلو: مشتری بسته را انتخاب می‌کند -> سفارش با وضعیت
    awaiting_payment ساخته می‌شود (هنوز رسیدی آپلود نشده، پس هنوز کمیسیونی
    کسر نمی‌شود).
    """
    customer_row = await fetch_one("SELECT telegram_user_id FROM customers WHERE id = %s", (customer_id,))
    if customer_row and await is_blacklisted(customer_row["telegram_user_id"], reseller_id):
        raise CustomerBlacklistedError("این مشتری در لیست سیاه است و امکان ثبت سفارش ندارد.")

    reseller = await fetch_one("SELECT order_prefix FROM resellers WHERE id = %s", (reseller_id,))
    package = await fetch_one("SELECT sale_price FROM packages WHERE id = %s", (package_id,))
    if package is None:
        raise ValueError("بسته پیدا نشد.")

    order_code = _generate_order_code(reseller["order_prefix"])
    order_id = await execute(
        "INSERT INTO orders (order_code, reseller_id, package_id, customer_id, status, package_price) "
        "VALUES (%s, %s, %s, %s, 'awaiting_payment', %s)",
        (order_code, reseller_id, package_id, customer_id, package["sale_price"]),
    )
    return await fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))


class WalletInsufficientBalanceError(Exception):
    """موجودی کیف‌پول مشتری برای خرید خودکار این بسته کافی نیست."""
    pass


async def create_order_paid_by_wallet(reseller_id: int, package_id: int, customer_id: int) -> dict:
    """
    خرید بسته با کسر خودکار از کیف‌پول مشتری (services/customer_wallet_service.py).
    چون کمیسیون نماینده همان لحظه‌ی شارژ کیف‌پول کسر شده (نه الان)، این‌جا دیگر
    نیازی به کسر کمیسیون یا رسید/تأیید نماینده نیست؛ سفارش مستقیم با وضعیت
    'confirmed' ثبت می‌شود و فقط منتظر فعال‌سازی دستی نماینده می‌ماند (مرحله ۵).
    اگر موجودی کافی نبود WalletInsufficientBalanceError بالا می‌رود تا هندلر
    برگردد به فلوی عادی رسید.
    """
    customer_row = await fetch_one(
        "SELECT telegram_user_id, wallet_balance FROM customers WHERE id = %s", (customer_id,)
    )
    if customer_row and await is_blacklisted(customer_row["telegram_user_id"], reseller_id):
        raise CustomerBlacklistedError("این مشتری در لیست سیاه است و امکان ثبت سفارش ندارد.")

    reseller = await fetch_one("SELECT order_prefix FROM resellers WHERE id = %s", (reseller_id,))
    package = await fetch_one("SELECT sale_price FROM packages WHERE id = %s", (package_id,))
    if package is None:
        raise ValueError("بسته پیدا نشد.")

    price = Decimal(package["sale_price"])
    if Decimal(customer_row["wallet_balance"]) < price:
        raise WalletInsufficientBalanceError("موجودی کیف‌پول کافی نیست.")

    order_code = _generate_order_code(reseller["order_prefix"])
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute(
            "SELECT wallet_balance FROM customers WHERE id = %s FOR UPDATE", (customer_id,)
        )
        row = await cur.fetchone()
        current_balance = Decimal(row[0])
        if current_balance < price:
            raise WalletInsufficientBalanceError("موجودی کیف‌پول کافی نیست.")

        await cur.execute(
            "UPDATE customers SET wallet_balance = wallet_balance - %s WHERE id = %s",
            (price, customer_id),
        )
        await cur.execute(
            "INSERT INTO orders (order_code, reseller_id, package_id, customer_id, status, "
            "package_price, commission_amount, is_test_order, paid_from_wallet, confirmed_at) "
            "VALUES (%s, %s, %s, %s, 'confirmed', %s, 0.00, FALSE, TRUE, NOW())",
            (order_code, reseller_id, package_id, customer_id, price),
        )
        order_id = cur.lastrowid

    return await fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))


async def submit_receipt(order_id: int, receipt_file_id: str) -> dict:
    """
    مرحله‌ی ۳ فلو: مشتری رسید را آپلود می‌کند.
      ۱. سقف ۳ سفارش هم‌زمان «در انتظار تأیید» چک می‌شود.
      ۲. اگر نماینده در حالت تست است و به سقف N سفارش موفق نرسیده -> کمیسیون
         کسر نمی‌شود (is_test_order = True).
      ۳. در غیر این صورت، تغییر وضعیت سفارش + کسر خودکار کمیسیون در یک تراکنش
         اتمیک واحد انجام می‌شود (رفع باگ نسخه‌ی قبل).
    """
    order = await fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))
    if order is None:
        raise ValueError("سفارش پیدا نشد.")

    pending_count = await count_pending_orders(order["customer_id"])
    if pending_count >= Config.MAX_PENDING_ORDERS_PER_CUSTOMER:
        raise PendingOrderLimitExceeded(
            f"این مشتری در حال حاضر {pending_count} سفارش در انتظار تأیید دارد؛ "
            f"باید ابتدا آن‌ها بررسی/رد یا تأیید شوند."
        )

    reseller = await fetch_one(
        "SELECT id, test_mode_enabled, test_mode_order_limit, test_mode_orders_used, commission_percent "
        "FROM resellers WHERE id = %s",
        (order["reseller_id"],),
    )

    is_test_order = bool(
        reseller["test_mode_enabled"]
        and reseller["test_mode_orders_used"] < reseller["test_mode_order_limit"]
    )

    commission_amount = Decimal("0.00")
    if not is_test_order:
        commission_amount = (
            Decimal(order["package_price"]) * Decimal(reseller["commission_percent"]) / Decimal("100")
        )

    insufficient_credit = False

    async with transaction() as conn:
        cur = await conn.cursor()

        if not is_test_order:
            try:
                await deduct_commission_in_tx(conn, reseller["id"], commission_amount, order["order_code"])
            except InsufficientCreditError:
                # به‌جای propagate خام، وضعیت شکست را همین‌جا (در همان تراکنش)
                # ثبت می‌کنیم تا با موفقیت commit شود؛ خطا را بعد از commit به
                # هندلر بالا اطلاع می‌دهیم (خارج از این بلوک تراکنش).
                insufficient_credit = True
                await cur.execute(
                    "UPDATE orders SET status = 'failed_insufficient_credit', "
                    "receipt_image = %s, commission_amount = %s, is_test_order = %s "
                    "WHERE id = %s",
                    (receipt_file_id, commission_amount, is_test_order, order_id),
                )
            else:
                await cur.execute(
                    "UPDATE orders SET status = 'awaiting_receipt_review', receipt_image = %s, "
                    "commission_amount = %s, is_test_order = %s WHERE id = %s",
                    (receipt_file_id, commission_amount, is_test_order, order_id),
                )
        else:
            await cur.execute(
                "UPDATE orders SET status = 'awaiting_receipt_review', receipt_image = %s, "
                "commission_amount = %s, is_test_order = %s WHERE id = %s",
                (receipt_file_id, commission_amount, is_test_order, order_id),
            )

    if insufficient_credit:
        raise OrderInsufficientCreditError(order_id, reseller["id"], order["order_code"])

    return await fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))


async def _increment_test_counter_if_needed(reseller_id: int, order_id: int) -> None:
    order = await fetch_one("SELECT is_test_order FROM orders WHERE id = %s", (order_id,))
    if order and order["is_test_order"]:
        await execute(
            "UPDATE resellers SET test_mode_orders_used = test_mode_orders_used + 1, "
            "test_mode_enabled = CASE WHEN test_mode_orders_used + 1 >= test_mode_order_limit "
            "THEN FALSE ELSE test_mode_enabled END "
            "WHERE id = %s",
            (reseller_id,),
        )


async def confirm_order(order_id: int) -> None:
    """نماینده/اپراتور رسید را تأیید می‌کند (مرحله ۴)."""
    await execute(
        "UPDATE orders SET status = 'confirmed', confirmed_at = NOW() WHERE id = %s",
        (order_id,),
    )


async def activate_order(order_id: int) -> dict:
    """نماینده دستی بسته را فعال می‌کند و دکمه‌ی «فعال شد» را می‌زند (مرحله ۵)."""
    order = await fetch_one("SELECT reseller_id FROM orders WHERE id = %s", (order_id,))
    await execute(
        "UPDATE orders SET status = 'activated', activated_at = NOW() WHERE id = %s",
        (order_id,),
    )
    # اگر این سفارش تستی موفق بود، شمارنده‌ی حالت تست را افزایش بده
    await _increment_test_counter_if_needed(order["reseller_id"], order_id)
    return await fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))


async def reject_order(order_id: int) -> None:
    """نماینده رسید را رد می‌کند (مثلاً رسید فیک تشخیص داده شد) — مرحله ۴."""
    await execute(
        "UPDATE orders SET status = 'rejected' WHERE id = %s",
        (order_id,),
    )


async def find_orders_pending_activation_alert(hours: int) -> list[dict]:
    """
    لایه‌ی دوم اطمینان: سفارش‌هایی که رسیدشان تأیید شده ولی بعد از X ساعت هنوز
    فعال نشده‌اند — برای هشدار خودکار به مدیر کل (بخش ۳).
    """
    return await fetch_all(
        "SELECT * FROM orders WHERE status = 'confirmed' "
        "AND confirmed_at < (NOW() - INTERVAL %s HOUR)",
        (hours,),
    )
