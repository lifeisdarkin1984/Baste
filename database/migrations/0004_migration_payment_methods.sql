-- ==========================================================================
-- Migration: «روش دریافت وجه از مشتری» به‌صورت چند کارت مستقل + مرچنت زرین‌پال
-- اختصاصی هر نماینده — جایگزین رویکرد قبلی (یک ستون card_number روی resellers).
--
-- اگر تازه داری دیتابیس رو از صفر می‌سازی، لازم نیست این فایل رو اجرا کنی؛
-- schema.sql به‌روز شده و این جدول رو از اول داره.
--
-- اگر قبلاً migration_add_card_number.sql (نسخه‌ی قبلی) رو اجرا کرده بودی،
-- همین یک فایل کافیه؛ خودش کارت قبلی رو منتقل و ستون‌های قدیمی رو حذف می‌کند:
--   mysql -h $DB_HOST -u $DB_USER -p $DB_NAME < database/migration_payment_methods.sql
-- ==========================================================================

CREATE TABLE IF NOT EXISTS reseller_payment_cards (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id       INT NOT NULL,
    card_number       VARCHAR(32) NOT NULL,
    card_holder_name  VARCHAR(64) NOT NULL,
    bank_name         VARCHAR(64) NULL,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

ALTER TABLE resellers
    ADD COLUMN IF NOT EXISTS zarinpal_merchant_id VARCHAR(64) NULL AFTER support_contact;

-- اگر ستون‌های قدیمی card_number/card_holder_name روی resellers وجود دارن
-- (یعنی migration قبلی رو اجرا کرده بودی)، دیتاشون رو منتقل کن و بعد حذفشون کن:
INSERT INTO reseller_payment_cards (reseller_id, card_number, card_holder_name, is_active)
SELECT id, card_number, card_holder_name, TRUE
FROM resellers
WHERE card_number IS NOT NULL;

ALTER TABLE resellers DROP COLUMN IF EXISTS card_number;
ALTER TABLE resellers DROP COLUMN IF EXISTS card_holder_name;
