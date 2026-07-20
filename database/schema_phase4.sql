-- ==========================================================================
-- فاز ۴ — طبق درخواست جدید:
--   ۱. حذف بخش‌های قبوض/VPN/درخواست‌فروش‌شارژ (فقط UI/handler حذف شده؛ جدول‌های
--      قدیمی feature_flags / bill_payments / global_settings دست‌نخورده باقی
--      می‌مانند تا داده‌ی قبلی از بین نرود، ولی دیگر از هیچ‌کجای ربات صدا زده
--      نمی‌شوند).
--   ۲. تقسیم کاتالوگ نماینده به دو بخش «بسته‌ی اینترنتی» و «شارژ» (همون
--      ساختار پوشه‌ای/جدول‌های categories و packages، فقط با یک ستون تشخیص نوع).
--   ۳. فیچر «خرید شارژ سطح» برای مشتری + مدیریت موجودی کد شارژ برای نماینده.
--
-- این فایل را (بعد از schema.sql و schema_phase3.sql) روی دیتابیس موجود اجرا کنید:
--   mysql -h "$MYSQLHOST" -u "$MYSQLUSER" -p"$MYSQLPASSWORD" "$MYSQLDATABASE" < database/schema_phase4.sql
-- ==========================================================================

-- تشخیص اینکه یک «پوشه» (اپراتور یا زیرپوشه) مربوط به کاتالوگ بسته‌ی اینترنتی
-- است یا کاتالوگ شارژ. زیرپوشه‌ها از پوشه‌ی اصلی همین مقدار را به ارث می‌برند
-- (هندلرها موقع ساخت زیرپوشه، catalog_type اپراتور والد را کپی می‌کنند).
ALTER TABLE categories ADD COLUMN IF NOT EXISTS catalog_type ENUM('package','charge') NOT NULL DEFAULT 'package';

-- تشخیص نوع سفارش (بسته‌ی اینترنتی معمولی، یا شارژ سطحی که با تحویل خودکار کد
-- انجام می‌شود) + خود کد تحویل‌داده‌شده (برای پیگیری/گزارش).
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type ENUM('package','charge') NOT NULL DEFAULT 'package';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_charge_code VARCHAR(128) NULL;

-- موجودی کدهای شارژ هر «محصول شارژ» (که خودش یک ردیف در جدول packages است،
-- داخل یک زیرپوشه‌ی کاتالوگ نوع 'charge'). هر کد فقط یک‌بار قابل فروش است.
CREATE TABLE IF NOT EXISTS charge_codes (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id          INT NOT NULL,
    package_id           INT NOT NULL,
    code                 VARCHAR(128) NOT NULL,
    status               ENUM('available','sold') NOT NULL DEFAULT 'available',
    added_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sold_at              DATETIME NULL,
    sold_to_customer_id  INT NULL,
    sold_order_id        INT NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
    INDEX idx_package_status (package_id, status)
) ENGINE=InnoDB;
