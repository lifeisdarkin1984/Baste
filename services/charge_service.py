"""
سرویس «شارژ سطح»: هم مدیریت موجودی کد توسط نماینده (افزودن/نمایش/حذف/فروخته‌شده)
و هم خرید آنی توسط مشتری.

نکته‌ی کلیدی که این ماژول را از services/order_service.py متفاوت می‌کند:
محصول شارژ نیازی به شماره‌خط یا فعال‌سازی دستی نماینده ندارد — چون خودِ
«کالا» یک کد از پیش تولیدشده است. برای همین خرید فقط وقتی ممکن است که موجودی
کیف‌پول مشتری کافی باشد (تحویل باید همان لحظه انجام شود، نه با فلوی رسید/تأیید
که ممکن است ساعت‌ها طول بکشد)؛ اگر موجودی کافی نبود، مشتری باید اول کیف‌پولش
را شارژ کند.
"""
import random
import string
from datetime import datetime
from decimal import Decimal

from database.db import fetch_one, fetch_all, execute, transaction
from services.blacklist_service import is_blacklisted


class ChargeCustomerBlacklistedError(Exception):
    """مشتری در لیست سیاه (مشترک یا مخصوص این نماینده) است."""
    pass


class ChargeInsufficientBalanceError(Exception):
    """موجودی کیف‌پول مشتری برای خرید این شارژ کافی نیست."""
    pass


class ChargeOutOfStockError(Exception):
    """
    موجودی کد این محصول شارژ تمام شده است (یا برای خرید عمده، کمتر از تعداد
    درخواستی موجود است). برای خرید عمده، تعداد واقعاً موجود در `available`
    قرار می‌گیرد تا هندلر بتواند دقیقاً به مشتری بگوید چند عدد موجود است.
    """
    def __init__(self, message: str = "موجودی این شارژ تمام شده است.", available: int | None = None):
        super().__init__(message)
        self.available = available


def _generate_order_code(prefix: str, sequence: int | None = None) -> str:
    """
    شناسه‌ی سفارش را می‌سازد. `sequence` اختیاری است و برای خرید عمده استفاده
    می‌شود: چون در یک حلقه چندین کد پشت‌سرهم و در همان ثانیه ساخته می‌شوند،
    فقط ۳ کاراکتر رندوم برای یکتا ماندن کافی نیست (احتمال برخورد با
    UNIQUE KEY روی order_code در تعداد بالا قابل توجه می‌شود)؛ افزودن یک
    شماره‌ی ترتیبی، یکتایی را در همان دسته تضمین می‌کند.
    """
    now = datetime.now()
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    code = f"{prefix}-C-{now.strftime('%y%m%d')}-{now.strftime('%H%M%S')}{suffix}"
    if sequence is not None:
        code = f"{code}{sequence:03d}"
    return code


# ==========================================================================
# مدیریت موجودی کد (پنل نماینده)
# ==========================================================================
async def add_charge_codes(reseller_id: int, package_id: int, raw_text: str) -> int:
    """
    کدها را از یک متن چندخطی (یکی در هر خط) استخراج و اضافه می‌کند.
    خط‌های خالی و تکراری‌های داخل همین ورودی نادیده گرفته می‌شوند.
    تعداد کدهای واقعاً اضافه‌شده را برمی‌گرداند.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        cleaned.append(line)

    for code in cleaned:
        await execute(
            "INSERT INTO charge_codes (reseller_id, package_id, code, status) VALUES (%s, %s, %s, 'available')",
            (reseller_id, package_id, code),
        )
    return len(cleaned)


async def count_available_codes(package_id: int) -> int:
    row = await fetch_one(
        "SELECT COUNT(*) AS c FROM charge_codes WHERE package_id = %s AND status = 'available'",
        (package_id,),
    )
    return row["c"]


async def list_available_codes(package_id: int, limit: int = 60) -> list[dict]:
    return await fetch_all(
        "SELECT id, code, added_at FROM charge_codes WHERE package_id = %s AND status = 'available' "
        "ORDER BY id ASC LIMIT %s",
        (package_id, limit),
    )


async def list_sold_codes(package_id: int, limit: int = 60) -> list[dict]:
    return await fetch_all(
        "SELECT cc.id, cc.code, cc.sold_at, o.order_code, c.telegram_user_id "
        "FROM charge_codes cc "
        "LEFT JOIN orders o ON cc.sold_order_id = o.id "
        "LEFT JOIN customers c ON cc.sold_to_customer_id = c.id "
        "WHERE cc.package_id = %s AND cc.status = 'sold' "
        "ORDER BY cc.sold_at DESC LIMIT %s",
        (package_id, limit),
    )


async def delete_available_code(code_id: int) -> None:
    """فقط کدهای هنوز فروخته‌نشده قابل حذف‌اند (کد فروخته‌شده باید برای پیگیری بماند)."""
    await execute("DELETE FROM charge_codes WHERE id = %s AND status = 'available'", (code_id,))


async def clear_available_codes(package_id: int) -> int:
    """همه‌ی کدهای موجودِ (فروخته‌نشده‌ی) این محصول را حذف می‌کند و تعدادشان را برمی‌گرداند."""
    row = await fetch_one(
        "SELECT COUNT(*) AS c FROM charge_codes WHERE package_id = %s AND status = 'available'",
        (package_id,),
    )
    count = row["c"]
    await execute("DELETE FROM charge_codes WHERE package_id = %s AND status = 'available'", (package_id,))
    return count


# ==========================================================================
# خرید (پنل مشتری)
# ==========================================================================
async def purchase_charge(reseller_id: int, package_id: int, customer_id: int) -> dict:
    """
    خرید آنی یک محصول شارژ از کیف‌پول مشتری + تحویل خودکار یک کد از موجودی.
    اتمیک: قفل ردیف مشتری و قفل یک کد موجود در یک تراکنش واحد، تا دو خرید
    هم‌زمان یک کد را دوبار تحویل ندهند.
    خروجی: {"order": <ردیف orders>, "code": <رشته‌ی کد تحویل‌داده‌شده>}
    """
    customer_row = await fetch_one(
        "SELECT telegram_user_id, wallet_balance FROM customers WHERE id = %s", (customer_id,)
    )
    if customer_row and await is_blacklisted(customer_row["telegram_user_id"], reseller_id):
        raise ChargeCustomerBlacklistedError("این مشتری در لیست سیاه است و امکان خرید ندارد.")

    reseller = await fetch_one("SELECT order_prefix FROM resellers WHERE id = %s", (reseller_id,))
    package = await fetch_one("SELECT sale_price FROM packages WHERE id = %s", (package_id,))
    if package is None:
        raise ValueError("محصول شارژ پیدا نشد.")

    price = Decimal(package["sale_price"])
    order_code = _generate_order_code(reseller["order_prefix"])
    code_id = None
    code_value = None

    async with transaction() as conn:
        cur = await conn.cursor()

        await cur.execute("SELECT wallet_balance FROM customers WHERE id = %s FOR UPDATE", (customer_id,))
        row = await cur.fetchone()
        current_balance = Decimal(row[0])
        if current_balance < price:
            raise ChargeInsufficientBalanceError("موجودی کیف‌پول کافی نیست.")

        await cur.execute(
            "SELECT id, code FROM charge_codes WHERE package_id = %s AND status = 'available' "
            "ORDER BY id ASC LIMIT 1 FOR UPDATE",
            (package_id,),
        )
        code_row = await cur.fetchone()
        if code_row is None:
            raise ChargeOutOfStockError("موجودی این شارژ تمام شده است.")
        code_id, code_value = code_row[0], code_row[1]

        await cur.execute(
            "UPDATE customers SET wallet_balance = wallet_balance - %s WHERE id = %s",
            (price, customer_id),
        )
        await cur.execute(
            "INSERT INTO orders (order_code, reseller_id, package_id, customer_id, status, order_type, "
            "package_price, commission_amount, is_test_order, paid_from_wallet, confirmed_at, activated_at, "
            "delivered_charge_code) "
            "VALUES (%s, %s, %s, %s, 'activated', 'charge', %s, 0.00, FALSE, TRUE, NOW(), NOW(), %s)",
            (order_code, reseller_id, package_id, customer_id, price, code_value),
        )
        await cur.execute(
            "UPDATE charge_codes SET status = 'sold', sold_at = NOW(), sold_to_customer_id = %s WHERE id = %s",
            (customer_id, code_id),
        )

    order = await fetch_one("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    if order is None:
        raise RuntimeError(f"سفارش {order_code} ثبت شد ولی بلافاصله پیدا نشد.")

    await execute("UPDATE charge_codes SET sold_order_id = %s WHERE id = %s", (order["id"], code_id))

    return {"order": order, "code": code_value}


async def purchase_charge_bulk(reseller_id: int, package_id: int, customer_id: int, quantity: int) -> dict:
    """
    خرید عمده (چندتایی) یک محصول شارژ از کیف‌پول مشتری + تحویل خودکار `quantity`
    کد از موجودی، هرکدام در یک ردیف جدای `orders` (چون ستون
    `orders.delivered_charge_code` تک‌مقداره است).

    اتمیک: قفل ردیف کیف‌پول مشتری و قفل `quantity` تا ردیف از کدهای موجود در
    یک تراکنش واحد، تا دو خرید هم‌زمان کدهای همدیگر را دوبار تحویل ندهند. اگر
    هر بخشی از تراکنش شکست بخورد، هیچ سفارشی ثبت و هیچ کدی sold نمی‌شود
    (rollback کامل توسط `transaction()`).

    خروجی: {"orders": [{"order_id", "order_code", "code"}, ...], "total_price": Decimal,
             "unit_price": Decimal, "quantity": int}
    """
    if quantity < 1:
        raise ValueError("تعداد باید حداقل ۱ باشد.")

    customer_row = await fetch_one(
        "SELECT telegram_user_id, wallet_balance FROM customers WHERE id = %s", (customer_id,)
    )
    if customer_row and await is_blacklisted(customer_row["telegram_user_id"], reseller_id):
        raise ChargeCustomerBlacklistedError("این مشتری در لیست سیاه است و امکان خرید ندارد.")

    reseller = await fetch_one("SELECT order_prefix FROM resellers WHERE id = %s", (reseller_id,))
    package = await fetch_one("SELECT sale_price FROM packages WHERE id = %s", (package_id,))
    if package is None:
        raise ValueError("محصول شارژ پیدا نشد.")

    unit_price = Decimal(package["sale_price"])
    total_price = unit_price * quantity

    delivered: list[dict] = []

    async with transaction() as conn:
        cur = await conn.cursor()

        await cur.execute("SELECT wallet_balance FROM customers WHERE id = %s FOR UPDATE", (customer_id,))
        row = await cur.fetchone()
        current_balance = Decimal(row[0])
        if current_balance < total_price:
            raise ChargeInsufficientBalanceError("موجودی کیف‌پول کافی نیست.")

        await cur.execute(
            "SELECT id, code FROM charge_codes WHERE package_id = %s AND status = 'available' "
            "ORDER BY id ASC LIMIT %s FOR UPDATE",
            (package_id, quantity),
        )
        available_rows = await cur.fetchall()
        if len(available_rows) < quantity:
            raise ChargeOutOfStockError(
                f"تنها {len(available_rows)} عدد از این شارژ موجود است.",
                available=len(available_rows),
            )

        await cur.execute(
            "UPDATE customers SET wallet_balance = wallet_balance - %s WHERE id = %s",
            (total_price, customer_id),
        )

        for seq, (code_id, code_value) in enumerate(available_rows, start=1):
            order_code = _generate_order_code(reseller["order_prefix"], sequence=seq)
            await cur.execute(
                "INSERT INTO orders (order_code, reseller_id, package_id, customer_id, status, order_type, "
                "package_price, commission_amount, is_test_order, paid_from_wallet, confirmed_at, activated_at, "
                "delivered_charge_code) "
                "VALUES (%s, %s, %s, %s, 'activated', 'charge', %s, 0.00, FALSE, TRUE, NOW(), NOW(), %s)",
                (order_code, reseller_id, package_id, customer_id, unit_price, code_value),
            )
            order_id = cur.lastrowid
            await cur.execute(
                "UPDATE charge_codes SET status = 'sold', sold_at = NOW(), sold_to_customer_id = %s, "
                "sold_order_id = %s WHERE id = %s",
                (customer_id, order_id, code_id),
            )
            delivered.append({"order_id": order_id, "order_code": order_code, "code": code_value})

    return {
        "orders": delivered,
        "total_price": total_price,
        "unit_price": unit_price,
        "quantity": quantity,
    }
