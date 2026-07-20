-- ==========================================================================
-- اسکیمای فاز ۱ (MVP) — طبق بخش ۶ و ۸ اسپک
-- جدول‌های فاز ۲/۳ (discount_codes, referrals, forced_join_channels, blacklist,
-- crypto_settings, feature_flags, broadcasts) در این فایل نیستند و در فاز
-- بعدی اضافه می‌شوند.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS resellers (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    bot_token_encrypted TEXT        NOT NULL,          -- توکن رمزنگاری‌شده (Fernet)
    bot_username        VARCHAR(64) NOT NULL,
    telegram_numeric_id BIGINT      NOT NULL,          -- آیدی عددی صاحب نماینده
    commission_percent  DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    wallet_credit_balance DECIMAL(14,2) NOT NULL DEFAULT 0.00,  -- فقط اعتبار کمیسیون
    credit_limit_negative DECIMAL(14,2) NOT NULL DEFAULT 0.00,  -- سقف منفی مجاز (عدد مثبت وارد می‌شود)
    status              ENUM('active','suspended') NOT NULL DEFAULT 'active',
    order_prefix        VARCHAR(8)  NOT NULL,          -- مثال: AR
    support_contact     VARCHAR(128) NULL,
    zarinpal_merchant_id VARCHAR(64) NULL,             -- مرچنت‌کد زرین‌پال خود نماینده (برای دریافت وجه بسته از مشتری)
    end_order_message   TEXT NULL,                     -- پیام پایان سفارش قابل شخصی‌سازی

    -- حالت تست (بخش ۳ - "حالت تست/آزمایشی برای نماینده جدید")
    test_mode_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    test_mode_order_limit INT NOT NULL DEFAULT 0,      -- N سفارش موفق تستی
    test_mode_orders_used INT NOT NULL DEFAULT 0,

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_prefix (order_prefix)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reseller_operators (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id   INT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    permissions   JSON NULL,
    status        ENUM('active','disabled') NOT NULL DEFAULT 'active',
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- «روش دریافت وجه از مشتری» — حساب/کارت شخصی خود نماینده (نه کیف‌پول
-- کمیسیون پلتفرم). هر نماینده می‌تواند چند کارت/بانک ثبت کند و هرکدام را
-- جدا روشن/خاموش کند (مثلاً وقتی موجودی یک کارت پر شده موقتاً غیرفعالش کند).
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

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    reseller_id  INT NOT NULL,
    type         ENUM('topup','commission_deduction','refund') NOT NULL,
    amount       DECIMAL(14,2) NOT NULL,       -- برای deduction به‌صورت منفی ذخیره می‌شود
    method        ENUM('card','zarinpal','crypto') NULL,   -- فقط برای topup
    status       ENUM('pending','confirmed','rejected') NOT NULL DEFAULT 'confirmed',
    reference    VARCHAR(64) NULL,             -- شماره پیگیری / order_code مرتبط
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    INDEX idx_reseller_created (reseller_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS categories (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id       INT NOT NULL,
    operator_name     VARCHAR(64) NOT NULL,     -- ایرانسل / همراه اول / رایتل / ...
    parent_category_id INT NULL,
    title             VARCHAR(64) NOT NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_category_id) REFERENCES categories(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS packages (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id  INT NOT NULL,
    category_id  INT NOT NULL,
    name         VARCHAR(128) NOT NULL,
    sale_price   DECIMAL(14,2) NOT NULL,
    cost_price   DECIMAL(14,2) NULL,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS customers (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id       INT NOT NULL,
    telegram_user_id  BIGINT NOT NULL,
    phone             VARCHAR(20) NULL,
    total_orders      INT NOT NULL DEFAULT 0,
    total_spent       DECIMAL(14,2) NOT NULL DEFAULT 0.00,
    UNIQUE KEY uq_reseller_customer (reseller_id, telegram_user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    order_code        VARCHAR(32) NOT NULL,     -- مثال: AR-240718-1532
    reseller_id       INT NOT NULL,
    package_id        INT NOT NULL,
    customer_id       INT NOT NULL,
    status            ENUM(
                          'awaiting_payment',
                          'awaiting_receipt_review',   -- کمیسیون کسر شده
                          'confirmed',
                          'activated',
                          'rejected',
                          'refund_pending',
                          'refunded',
                          'failed_insufficient_credit' -- کسر کمیسیون به‌خاطر کمبود اعتبار نماینده ناموفق بود
                      ) NOT NULL DEFAULT 'awaiting_payment',
    receipt_image     VARCHAR(255) NULL,        -- فقط اطلاعاتی، بدون اثر مالی
    package_price     DECIMAL(14,2) NOT NULL,   -- کپی از قیمت بسته در لحظه ثبت
    commission_amount DECIMAL(14,2) NOT NULL DEFAULT 0.00,
    is_test_order     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at      DATETIME NULL,
    activated_at      DATETIME NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (package_id) REFERENCES packages(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    UNIQUE KEY uq_order_code (order_code),
    INDEX idx_customer_status (customer_id, status)
) ENGINE=InnoDB;

-- جدول رسمی استرداد/اختلاف (بخش ۳ - سیستم Refund/Dispute)
CREATE TABLE IF NOT EXISTS disputes (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    order_id          INT NOT NULL,
    reseller_id       INT NOT NULL,
    reason            TEXT NOT NULL,
    review_status     ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    refunded_amount   DECIMAL(14,2) NULL,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at       DATETIME NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS activity_logs (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_type   ENUM('admin','reseller','operator') NOT NULL,
    actor_id     BIGINT NOT NULL,
    reseller_id  INT NULL,
    action       VARCHAR(64) NOT NULL,
    details      JSON NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_reseller (reseller_id)
) ENGINE=InnoDB;

-- حداقل قیمت منطقی هر دسته/اپراتور برای Sanity Check (بخش ۵)
CREATE TABLE IF NOT EXISTS category_price_floors (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    operator_name   VARCHAR(64) NOT NULL,
    min_sane_price  DECIMAL(14,2) NOT NULL,
    UNIQUE KEY uq_operator (operator_name)
) ENGINE=InnoDB;

-- ==========================================================================
-- جدول‌های فاز ۲ — طبق بخش ۶ و ۸ اسپک
-- ==========================================================================

CREATE TABLE IF NOT EXISTS discount_codes (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id   INT NOT NULL,
    code          VARCHAR(32) NOT NULL,
    percent       DECIMAL(5,2) NOT NULL,
    usage_limit   INT NOT NULL DEFAULT 0,        -- 0 = نامحدود
    usage_count   INT NOT NULL DEFAULT 0,
    expires_at    DATETIME NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    UNIQUE KEY uq_reseller_code (reseller_id, code)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS referrals (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id   INT NOT NULL,
    is_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
    profit_percent DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    UNIQUE KEY uq_reseller (reseller_id),
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- چه کسی چه کسی را رفر کرده (برای محاسبه‌ی سود رفرال به‌ازای هر سفارش موفق)
CREATE TABLE IF NOT EXISTS referral_links (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id        INT NOT NULL,
    referrer_customer_id INT NOT NULL,   -- مشتری‌ای که لینکش استفاده شده
    referred_customer_id INT NOT NULL,   -- مشتری جدیدی که با این لینک آمده
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_referred (reseller_id, referred_customer_id),
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forced_join_channels (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id  INT NOT NULL,
    channel_id   VARCHAR(64) NOT NULL,     -- مثال: @channel یا -100xxxxxxxxxx
    set_by       ENUM('admin','reseller') NOT NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS blacklist (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    telegram_user_id      BIGINT NOT NULL,
    reported_by_reseller_id INT NULL,
    reason                VARCHAR(255) NULL,
    is_global             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_telegram_user (telegram_user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS crypto_settings (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    coin_name    VARCHAR(32) NOT NULL,
    address      VARCHAR(128) NOT NULL,
    network      VARCHAR(32) NOT NULL,
    price        DECIMAL(18,2) NOT NULL,   -- نرخ تبدیل لحظه‌ای (تومان به ازای یک واحد کوین)
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS feature_flags (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    reseller_id  INT NOT NULL,
    feature      ENUM('recharge','vpn','bills') NOT NULL,
    status       ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at   DATETIME NULL,
    UNIQUE KEY uq_reseller_feature (reseller_id, feature),
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS broadcasts (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    message      TEXT NOT NULL,
    sent_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- گزینه‌ی «پرداخت قبوض» یک فیچر سراسری است (فقط مدیر کل روشن/خاموش می‌کند)،
-- نه به‌ازای هر نماینده؛ برای همین در جدول جدا نگه‌داری می‌شود.
CREATE TABLE IF NOT EXISTS global_settings (
    setting_key   VARCHAR(64) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

INSERT IGNORE INTO global_settings (setting_key, setting_value) VALUES ('bills_payment_enabled', 'false');

-- ==========================================================================
-- کیف‌پول مشتری (نصب تازه؛ برای دیتابیس موجود از migration_customer_wallet.sql استفاده کنید)
-- ==========================================================================
ALTER TABLE customers ADD COLUMN IF NOT EXISTS wallet_balance DECIMAL(14,2) NOT NULL DEFAULT 0.00;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS paid_from_wallet BOOLEAN NOT NULL DEFAULT FALSE;

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
                      'confirmed_insufficient_credit',
                      'rejected'
                  ) NOT NULL DEFAULT 'pending',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at  DATETIME NULL,
    FOREIGN KEY (reseller_id) REFERENCES resellers(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB;
