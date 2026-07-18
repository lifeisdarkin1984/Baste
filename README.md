# پلتفرم نمایندگی فروش بسته اینترنت / شارژ / VPN / قبوض

## نصب
```bash
pip install -r requirements.txt
cp .env.example .env   # و مقادیر واقعی را پر کنید
```

کلید رمزنگاری توکن نماینده‌ها را بسازید:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

اسکیمای دیتابیس را به ترتیب اجرا کنید:
```bash
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME < database/schema.sql
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME < database/schema_phase3.sql
```

اجرا:
```bash
python main.py
```

---

## فاز ۱ — هسته‌ی اصلی
- **Dynamic Bot Manager**: چند ربات نماینده هم‌زمان با polling؛ افزودن/تعلیق نماینده بدون ری‌استارت کل سرویس (هر ۳۰ ثانیه sync می‌شود).
- **کیف‌پول کمیسیون** با تراکنش اتمیک (`SELECT ... FOR UPDATE`) برای جلوگیری از race condition.
- فلوی کامل سفارش: انتخاب بسته → آپلود رسید → **کسر خودکار کمیسیون همان لحظه** → تأیید/رد نماینده → فعال‌سازی دستی → **پیام پایان سفارش مستقیم برای مشتری**.
- سقف ۳ سفارش هم‌زمان «در انتظار تأیید» به‌ازای هر مشتری (ضد اسپم رسید فیک).
- حالت تست نماینده (N سفارش موفق بدون کمیسیون، خروج خودکار بعد از سقف).
- جدول رسمی `disputes` برای استرداد/اختلاف (به‌جای پیام دستی).
- Sanity Check قیمت با هشدار و تأیید صریح نماینده.
- هشدار خودکار به مدیر کل اگر سفارشِ تأییدشده بعد از X ساعت فعال نشود.
- توکن ربات نماینده‌ها رمزنگاری‌شده (Fernet) ذخیره می‌شود.
- **مجوز اپراتور**: `core/permissions_middleware.py` روی روتر اکشن‌های حساس سفارش وصل است؛ فقط صاحب نماینده یا اپراتور فعال (`reseller_operators`) اجازه‌ی تأیید/رد/فعال‌سازی/ثبت‌استرداد دارند.

## فاز ۲ — درآمدزایی و کنترل ریسک تکمیلی
- **💳 روش دریافت وجه از مشتری** (`handlers/reseller/payment_methods.py`, `services/payment_methods_service.py`) — کاملاً جدا از کیف‌پول کمیسیون: نماینده می‌تواند چند کارت شخصی (چند بانک) ثبت کند، هرکدام را جدا روشن/خاموش کند (`/add_card`, `/my_cards`, `/toggle_card`, `/remove_card`)، و اگر زرین‌پال شخصی دارد مرچنت‌کد خودش را ثبت کند (`/set_zarinpal`, `/my_zarinpal`) تا مشتری مستقیم به حساب خودش پرداخت کند. این دقیقاً همان چیزی است که در مرحله‌ی انتخاب بسته به مشتری نشان داده می‌شود.
- شارژ کیف‌پول کمیسیون **نزد پلتفرم** با **زرین‌پال** (مرچنت پلتفرم از env) و **رمزارز** (تنظیم آدرس/نرخ توسط مدیر کل + تأیید دستی هش تراکنش) — این جدا از روش دریافت وجه بالاست.
- **کدهای تخفیف** درصدی با سقف استفاده و انقضا.
- **رفرال**: فعال/غیرفعال به‌ازای هر نماینده، درصد سود قابل‌تنظیم، لینک اختصاصی `?start=ref_<customer_id>`.
- **جوین اجباری کانال**: قبل از نمایش کاتالوگ، عضویت مشتری در کانال(های) نماینده چک می‌شود.
- **لیست سیاه مشترک**: بلاک سراسری یا محلی؛ بعد از ۳ مورد dispute تأییدشده (رسید فیک ثابت‌شده)، مشتری **خودکار** به لیست سیاه مشترک اضافه می‌شود.
- **درخواست فیچر شارژ/VPN**: نماینده درخواست می‌دهد، مدیر کل تأیید/رد می‌کند (`feature_flags`).
- **پرداخت قبوض** به‌صورت فیچر سراسری (فقط مدیر کل روشن/خاموش می‌کند، نه به‌ازای هر نماینده).
- **گزارش سود واقعی** (فروش − قیمت تمام‌شده − کمیسیون) + **خروجی اکسل** برای نماینده و پنل کل پلتفرم برای مدیر کل.
- **لاگ فعالیت** کامل و قابل فیلتر بر اساس نماینده (`activity_logs`).

## فاز ۳ — تکمیلی
- **بک‌آپ/ریستور کامل**: بک‌آپ JSON از تمام جدول‌ها؛ ریستور دوم‌مرحله‌ای (آپلود → اعتبارسنجی ساختاری → تأیید صریح `/confirm_restore`) با گرفتن یک بک‌آپ ایمنی خودکار قبل از overwrite، همه در یک تراکنش اتمیک.
- **آمار پیشرفته مشتری**: برترین مشتریان، نرخ مشتری تکراری، میانگین ارزش سفارش.
- **پرداخت قبوض** برای مشتری نهایی (فلوی مشابه سفارش: شناسه قبض + مبلغ → رسید → تأیید نماینده → پرداخت دستی).

---

## دستورات کلیدی (خلاصه)

**مدیر کل:** `/add_reseller` `/list_resellers` `/suspend <id>` `/activate_reseller <id>` `/pending_topups` `/confirm_topup <id>` `/pending_disputes` `/approve_dispute <id>` `/reject_dispute <id>` `/pending_features` `/approve_feature <id>` `/reject_feature <id>` `/set_crypto COIN ADDR NET PRICE` `/blacklist` `/blacklist_add <id> دلیل` `/broadcast متن` `/bills_on` `/bills_off` `/platform_report` `/backup` `/restore`

**نماینده:** `/wallet` `/topup` `/topup_zarinpal <amount>` `/topup_crypto` `/confirm_crypto COIN HASH AMOUNT` `/add_card شماره‌کارت نام [بانک]` `/my_cards` `/toggle_card <id>` `/remove_card <id>` `/set_zarinpal <merchant_id>` `/my_zarinpal` `/add_discount CODE PERCENT LIMIT` `/referral_on` `/referral_off` `/referral_percent <n>` `/add_channel <id>` `/list_channels` `/request_recharge` `/request_vpn` `/report` `/report_excel` `/top_customers` `/customer_stats` `/pending_bills` `/confirm_bill <id>` `/mark_bill_paid <id>`

**مشتری:** `/start` (با پشتیبانی لینک رفرال) `/discount CODE` (حین ثبت سفارش) `/pay_bill <شناسه> <مبلغ>`

---

## رفع باگ: اتمیک‌نبودن کسر کمیسیون + تغییر وضعیت سفارش
قبلاً اگر کسر کمیسیون به‌خاطر کمبود اعتبار نماینده (`InsufficientCreditError`) شکست می‌خورد، وضعیت سفارش از قبل (در تراکنش جدا) روی `awaiting_receipt_review` کامیت شده بود — یعنی سیستم در وضعیتی متناقض می‌ماند و هیچ پیامی هم واقعاً به کسی ارسال نمی‌شد. الان:
- `services/wallet_service.py`: تابع `deduct_commission_in_tx(conn, ...)` اضافه شده که یک کانکشن/تراکنش از بیرون می‌گیرد.
- `services/order_service.py`: تغییر وضعیت سفارش + کسر کمیسیون در **یک تراکنش اتمیک واحد** انجام می‌شود؛ در صورت کمبود اعتبار، وضعیت روی `failed_insufficient_credit` ثبت می‌شود (نه `awaiting_receipt_review`) و `OrderInsufficientCreditError` بعد از commit بالا می‌رود.
- `services/notifications.py` (فایل جدید): هم به خود نماینده (از طریق بات خودش) و هم به مدیر کل پیام هشدار واقعی ارسال می‌شود.
- `database/migration_add_failed_insufficient_credit_status.sql`: اگر از قبل دیتابیس داری، این migration رو اجرا کن تا مقدار جدید به ENUM ستون `orders.status` اضافه بشه.

## نکات مهم پیش از دیپلوی واقعی
- ترتیب اجرای اسکیما مهم است: ابتدا `schema.sql` سپس `schema_phase3.sql`.
- `ZARINPAL_MERCHANT_ID` باید در Environment Variables تنظیم شود (`services/zarinpal_service.py`).
- تأیید خودکار هش تراکنش رمزارزی روی بلاک‌چین پیاده نشده (فعلاً تأیید دستی مدیر کل)؛ در صورت نیاز به اتصال به بلاک‌اکسپلورر جداگانه توسعه یابد.
- برای مقیاس بیش از ۱۰-۱۵ نماینده، مهاجرت `DynamicBotManager` از polling به webhook مشترک توصیه می‌شود (تغییر ایزوله در `core/bot_manager.py`).
- کد تخفیف فعلاً روی `orders.package_price` مستقیم اعمال می‌شود (یعنی کمیسیون روی قیمت تخفیف‌خورده محاسبه می‌شود)؛ اگر می‌خواهید کمیسیون همیشه روی قیمت اصلی کاتالوگ محاسبه شود، این منطق در `services/order_service.py` باید جدا شود.
