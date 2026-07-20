-- Migration: کیف‌پول مشتری + پرداخت خودکار بسته از کیف‌پول
-- روی دیتابیس‌های قبلاً ساخته‌شده اجرا کنید (بعد از schema.sql و schema_phase3.sql).
-- نیازمند MySQL 8.0.29+ برای ADD COLUMN IF NOT EXISTS. اگر نسخه قدیمی‌تر دارید
-- و خطا گرفتید، بخش IF NOT EXISTS را حذف کنید (فقط یک‌بار قابل اجراست).

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS wallet_balance DECIMAL(14,2) NOT NULL DEFAULT 0.00;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS paid_from_wallet BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS customer_wallet_topups (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id   INT NOT NULL,
    customer_id   INT NOT NULL,
    amount        DECIMAL(14,2) NOT NULL,
    method        ENUM('card', 'zarinpal') NOT NULL,
    receipt_image VARCHAR(255) NULL,
    status        ENUM(
                      'pending',
                      'confirmed',
                      'confirmed_insufficient_credit',  -- شارژ شد ولی کسر کمیسیون نماینده به‌خاطر کمبود اعتبار ناموفق بود
                      'rejected'
                  ) NOT NULL DEFAULT 'pending',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at  DATETIME NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB;
