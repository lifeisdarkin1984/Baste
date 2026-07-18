-- ==========================================================================
-- جدول‌های فاز ۳
-- ==========================================================================

-- پرداخت قبوض: جدا از orders نگه داشته می‌شود چون بسته/دسته‌ی مشخصی ندارد و
-- مبلغ را خود مشتری وارد می‌کند (شماره قبض + مبلغ)، نه یک sale_price ثابت.
CREATE TABLE IF NOT EXISTS bill_payments (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    bill_code     VARCHAR(32) NOT NULL,        -- شناسه یکتا مثل orders: <PREFIX>-B-YYMMDD-HHMM
    reseller_id   INT NOT NULL,
    customer_id   INT NOT NULL,
    bill_id_number VARCHAR(64) NOT NULL,        -- شناسه قبض که مشتری وارد کرده
    amount        DECIMAL(14,2) NOT NULL,
    status        ENUM('awaiting_receipt_review','confirmed','paid','rejected') NOT NULL
                  DEFAULT 'awaiting_receipt_review',
    receipt_image VARCHAR(255) NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at       DATETIME NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    UNIQUE KEY uq_bill_code (bill_code)
) ENGINE=InnoDB;

-- تاریخچه‌ی بک‌آپ‌های گرفته‌شده (برای پیگیری، نه خود فایل بک‌آپ)
CREATE TABLE IF NOT EXISTS backup_logs (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    taken_by_telegram_id BIGINT NOT NULL,
    file_size_bytes BIGINT NULL,
    note         VARCHAR(255) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
