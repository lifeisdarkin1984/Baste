"""
اجراکننده‌ی خودکار Migration ها.

هدف: دیگه لازم نیست دستی بری Console دیتابیس روی Railway و SQL بزنی. کافیه
یه فایل .sql جدید تو پوشه‌ی database/migrations/ اضافه کنی (با یه پیشوند
عددی بزرگ‌تر از آخرین فایل، مثلاً 0007_...sql) و سورس رو پوش کنی؛ دفعه‌ی
بعد که بات بالا میاد، خودش تشخیص میده این فایل جدیده و اجراش می‌کنه.

نحوه‌ی کار:
  - یه جدول schema_migrations تو دیتابیس نگه‌داری میشه که اسم فایل‌های
    اجراشده رو ثبت می‌کنه.
  - موقع اولین اجرا (وقتی این جدول خالیه ولی فایل‌های migrations/ هست)،
    فرض می‌کنیم دیتابیس فعلی از قبل (دستی) آپدیت شده — چون این پروژه از قبل
    در حال اجراست. پس فایل‌های موجود رو فقط علامت "اجراشده" می‌زنیم، بدون
    اینکه واقعاً دوباره اجراشون کنیم (چون بعضیاشون مثل migration_payment_methods
    اگه دوباره اجرا بشن روی دیتابیسی که قبلاً اجرا شده، خطا می‌گیرن).
  - از دفعه‌ی بعد، فقط فایل‌های جدیدی که به پوشه اضافه بشن واقعاً اجرا میشن.

نکته برای هر AI/توسعه‌دهنده‌ای که بعداً یه تغییر دیتابیس لازم داره:
  یه فایل جدید با پیشوند عددی بعدی تو database/migrations/ بساز (SQL خالص،
  چندتا دستور با ; از هم جدا). لازم نیست idempotent باشه (IF NOT EXISTS و
  از این‌جور چیزا) چون این سیستم تضمین می‌کنه هر فایل فقط یک‌بار اجرا بشه.
"""
import logging
from pathlib import Path

from database.db import get_pool

logger = logging.getLogger("migrator")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _split_statements(sql_text: str) -> list[str]:
    """SQL رو به دستورات جدا تبدیل می‌کند (بر اساس ;)، کامنت‌های تک‌خطی را حذف می‌کند."""
    lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    statements = [s.strip() for s in cleaned.split(";")]
    return [s for s in statements if s]


async def run_migrations() -> None:
    pool = get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename    VARCHAR(255) PRIMARY KEY,
                    applied_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
                """
            )
            await cur.execute("SELECT COUNT(*) FROM schema_migrations")
            (already_applied_count,) = await cur.fetchone()
        await conn.commit()

    if not MIGRATIONS_DIR.exists():
        return

    all_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not all_files:
        return

    # اولین اجرا روی دیتابیسی که از قبل (دستی) آپدیت بوده: فقط baseline رو ثبت کن.
    if already_applied_count == 0:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                for f in all_files:
                    await cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,)
                    )
            await conn.commit()
        logger.info(
            "Migration baseline ثبت شد (%d فایل موجود، بدون اجرا — فرض بر آپدیت‌بودن دیتابیس فعلی).",
            len(all_files),
        )
        return

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT filename FROM schema_migrations")
            applied = {row[0] for row in await cur.fetchall()}

    pending = [f for f in all_files if f.name not in applied]
    if not pending:
        logger.info("Migration جدیدی برای اجرا نیست.")
        return

    for f in pending:
        logger.info("در حال اجرای migration: %s", f.name)
        statements = _split_statements(f.read_text(encoding="utf-8"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    for stmt in statements:
                        await cur.execute(stmt)
                    await cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,)
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    logger.exception(
                        "اجرای migration %s شکست خورد؛ بات متوقف می‌شود تا دستی بررسی بشه.",
                        f.name,
                    )
                    raise
        logger.info("migration %s با موفقیت اجرا شد.", f.name)
