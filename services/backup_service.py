"""
بک‌آپ و ریستور کامل (فاز ۳ اسپک).

به‌جای اتکا به باینری mysqldump/mysql (که ممکن است روی کانتینر Railway نصب
نباشد و طبق بخش ۱۰ اسپک باید از قفل‌شدگی به سرویس‌های اختصاصی پرهیز شود)،
بک‌آپ به‌صورت یک فایل JSON خالص پایتونی از تمام جدول‌ها گرفته می‌شود. این هم
قابل‌حمل‌تر است و هم امکان اعتبارسنجی ساختاری قبل از ریستور را می‌دهد.

ترتیب TABLES بر اساس وابستگی FK رعایت شده تا هنگام ریستور، insert با خطای
Foreign Key مواجه نشود؛ برای پاک‌سازی قبل از ریستور از ترتیب معکوس استفاده
می‌شود.
"""
import json
import os
from datetime import datetime, date
from decimal import Decimal

from database.db import fetch_all, transaction

TABLES_IN_DEPENDENCY_ORDER = [
    "resellers",
    "reseller_operators",
    "wallet_transactions",
    "categories",
    "packages",
    "customers",
    "orders",
    "disputes",
    "activity_logs",
    "category_price_floors",
    "discount_codes",
    "referrals",
    "referral_links",
    "forced_join_channels",
    "blacklist",
    "crypto_settings",
    "feature_flags",
    "broadcasts",
    "global_settings",
    "bill_payments",
    "backup_logs",
]


class BackupValidationError(Exception):
    """بک‌آپ آپلودشده معتبر/سالم نیست."""
    pass


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"نوع غیرقابل سریالایز: {type(value)}")


async def create_backup_dict() -> dict:
    backup = {"created_at": datetime.now().isoformat(), "tables": {}}
    for table in TABLES_IN_DEPENDENCY_ORDER:
        backup["tables"][table] = await fetch_all(f"SELECT * FROM {table}")
    return backup


async def save_backup_to_file(filepath: str) -> int:
    """بک‌آپ می‌گیرد و در filepath ذخیره می‌کند؛ سایز فایل (بایت) را برمی‌گرداند."""
    backup = await create_backup_dict()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, default=_json_default)
    return os.path.getsize(filepath)


def validate_backup_file(filepath: str) -> dict:
    """
    اعتبارسنجی ساختاری قبل از ریستور (بخش امنیتی مهم — رسید/فایل فیک نپذیرد):
      - باید JSON معتبر باشد
      - باید کلیدهای created_at و tables را داشته باشد
      - tables باید dict باشد و حداقل چند جدول شناخته‌شده در آن باشد
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise BackupValidationError(f"فایل بک‌آپ معتبر نیست (JSON خراب است): {e}")

    if not isinstance(data, dict) or "tables" not in data or "created_at" not in data:
        raise BackupValidationError("ساختار فایل بک‌آپ صحیح نیست (کلیدهای الزامی موجود نیست).")

    if not isinstance(data["tables"], dict):
        raise BackupValidationError("بخش tables باید یک آبجکت شامل جدول‌ها باشد.")

    known_tables_found = [t for t in data["tables"].keys() if t in TABLES_IN_DEPENDENCY_ORDER]
    if len(known_tables_found) < 3:
        raise BackupValidationError(
            "این فایل شبیه بک‌آپ معتبر این پروژه نیست (جدول‌های شناخته‌شده‌ی کافی پیدا نشد)."
        )

    return data


async def restore_from_dict(data: dict) -> None:
    """
    ریستور اتمیک: تمام جدول‌ها در یک تراکنش پاک و از نو پر می‌شوند. اگر در
    وسط راه خطایی رخ دهد، rollback خودکار انجام می‌شود (هیچ حالت نیمه‌کاره‌ای
    باقی نمی‌ماند).
    """
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute("SET FOREIGN_KEY_CHECKS = 0")

        for table in reversed(TABLES_IN_DEPENDENCY_ORDER):
            await cur.execute(f"DELETE FROM {table}")

        for table in TABLES_IN_DEPENDENCY_ORDER:
            rows = data["tables"].get(table, [])
            for row in rows:
                if not row:
                    continue
                columns = list(row.keys())
                placeholders = ", ".join(["%s"] * len(columns))
                col_names = ", ".join(columns)
                values = [row[c] for c in columns]
                await cur.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values
                )

        await cur.execute("SET FOREIGN_KEY_CHECKS = 1")


async def perform_safe_restore(uploaded_filepath: str, safety_backup_dir: str) -> str:
    """
    فلوی کامل و امن ریستور:
      ۱. فایل آپلودشده اعتبارسنجی می‌شود (validate_backup_file)
      ۲. قبل از هرگونه overwrite، یک بک‌آپ ایمنی از وضعیت فعلی گرفته می‌شود
      ۳. ریستور اتمیک انجام می‌شود
    خروجی: مسیر فایل بک‌آپ ایمنی (برای اطلاع ادمین/بازگشت در صورت مشکل)
    """
    data = validate_backup_file(uploaded_filepath)

    os.makedirs(safety_backup_dir, exist_ok=True)
    safety_path = os.path.join(
        safety_backup_dir, f"safety_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    await save_backup_to_file(safety_path)

    await restore_from_dict(data)
    return safety_path
