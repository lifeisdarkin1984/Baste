-- Migration: شماره تلفن (خط) مقصد فعال‌سازی بسته روی سفارش
-- روی دیتابیس‌های قبلاً ساخته‌شده اجرا کنید.
-- نیازمند MySQL 8.0.29+ برای ADD COLUMN IF NOT EXISTS. اگر نسخه قدیمی‌تر دارید
-- و خطا گرفتید، بخش IF NOT EXISTS را حذف کنید (فقط یک‌بار قابل اجراست).

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20) NULL
    COMMENT 'شماره خطی که نماینده باید بسته را روی آن فعال کند (وارد شده توسط مشتری هنگام خرید)';
