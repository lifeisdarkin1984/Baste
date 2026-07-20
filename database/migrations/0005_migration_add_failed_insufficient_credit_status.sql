-- ==========================================================================
-- Migration: افزودن وضعیت 'failed_insufficient_credit' به ستون orders.status
-- (رفع باگ اتمیک‌نبودن کسر کمیسیون + تغییر وضعیت سفارش)
--
-- اگر تازه داری دیتابیس رو از صفر می‌سازی، لازم نیست این فایل رو اجرا کنی؛
-- schema.sql به‌روز شده و این مقدار رو از اول تو ENUM داره.
--
-- اگر قبلاً schema.sql قدیمی رو اجرا کرده بودی، همین یک فایل رو اجرا کن:
--   mysql -h $DB_HOST -u $DB_USER -p $DB_NAME < database/migration_add_failed_insufficient_credit_status.sql
--
-- نکته: چون MySQL برای MODIFY COLUMN روی ENUM نیاز داره کل لیست مقادیر رو
-- دوباره بنویسی، همه‌ی مقادیر قبلی + مقدار جدید اینجا تکرار شده‌اند.
-- ==========================================================================

ALTER TABLE orders
    MODIFY COLUMN status ENUM(
        'awaiting_payment',
        'awaiting_receipt_review',
        'confirmed',
        'activated',
        'rejected',
        'refund_pending',
        'refunded',
        'failed_insufficient_credit'
    ) NOT NULL DEFAULT 'awaiting_payment';
