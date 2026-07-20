"""
لایه‌ی دسترسی به دیتابیس. Connection Pooling حتماً فعال است چون چند بات
هم‌زمان (هر نماینده + ادمین کل) به یک دیتابیس مشترک وصل می‌شوند (بخش ۱۰).
"""
import aiomysql
from contextlib import asynccontextmanager
from config import Config

_pool: aiomysql.Pool | None = None


async def init_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            db=Config.DB_NAME,
            minsize=Config.DB_POOL_MIN,
            maxsize=Config.DB_POOL_MAX,
            autocommit=False,
            charset="utf8mb4",
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> aiomysql.Pool:
    if _pool is None:
        raise RuntimeError("Connection pool مقداردهی نشده؛ init_pool() را صدا بزنید.")
    return _pool


@asynccontextmanager
async def acquire_conn():
    """
    یک کانکشن از pool می‌گیرد (بدون تراکنش صریح).

    نکته‌ی مهم (رفع باگ): چون pool با autocommit=False ساخته شده، حتی یه
    SELECT ساده هم به‌صورت ضمنی یه تراکنش REPEATABLE READ باز می‌کنه که
    snapshot داده‌ها رو همون لحظه فریز می‌کنه. اگه این تراکنش قبل از برگردوندن
    کانکشن به pool commit/rollback نشه، دفعه‌ی بعد که همون کانکشن از pool
    دوباره استفاده بشه، هنوز تو همون تراکنش قدیمیه و داده‌ی جدیدی که کانکشن‌های
    دیگه commit کردن رو نمی‌بینه (مثلاً سفارشی که همین الان INSERT شده، تو
    fetch_one بعدی None برمی‌گشت). برای همین بعد از هر استفاده، commit()
    می‌زنیم تا تراکنش ضمنی بسته بشه و دفعه‌ی بعد snapshot تازه بگیره.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            yield conn
        finally:
            await conn.commit()


@asynccontextmanager
async def transaction():
    """
    کانتکست‌منیجر تراکنش اتمیک — برای عملیات مالی (کسر/افزایش کیف‌پول) که طبق
    بخش ۱۱ باید حتماً اتمیک باشند تا از race condition جلوگیری شود.
    استفاده:
        async with transaction() as conn:
            cur = await conn.cursor()
            await cur.execute(...)
    اگر داخل بلوک استثنایی رخ دهد، rollback خودکار انجام می‌شود.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.begin()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


async def fetch_one(query: str, params: tuple = ()) -> dict | None:
    async with acquire_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params)
            return await cur.fetchone()


async def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    async with acquire_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params)
            return await cur.fetchall()


async def execute(query: str, params: tuple = ()) -> int:
    """برای INSERT/UPDATE/DELETE ساده و مستقل (غیر مالی). lastrowid برمی‌گرداند."""
    async with acquire_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            await conn.commit()
            return cur.lastrowid
