from aiogram.fsm.state import State, StatesGroup


class CustomerOrderStates(StatesGroup):
    choosing_package = State()
    waiting_receipt = State()


class ResellerPackageStates(StatesGroup):
    entering_name = State()
    entering_price = State()
    confirming_suspicious_price = State()   # هشدار Sanity Check
    entering_cost_price = State()


class ResellerCategoryStates(StatesGroup):
    entering_operator_name = State()        # ساخت پوشه‌ی اصلی اپراتور (مثلاً ایرانسل)
    entering_subcategory_title = State()    # ساخت زیرپوشه داخل اپراتور (مثلاً ماهانه/هفتگی)


class ResellerDisputeStates(StatesGroup):
    entering_reason = State()


class ResellerTopupStates(StatesGroup):
    choosing_method = State()
    entering_amount = State()
    uploading_receipt = State()
    entering_zarinpal_amount = State()


class ResellerCryptoTopupStates(StatesGroup):
    entering_coin = State()
    entering_tx_hash = State()
    entering_amount = State()


class ResellerPaymentMethodStates(StatesGroup):
    entering_card_number = State()
    entering_card_holder = State()
    entering_bank_name = State()
    entering_zarinpal_merchant = State()


class ResellerSettingsStates(StatesGroup):
    entering_channel_id = State()
    entering_referral_percent = State()
    entering_discount_code = State()
    entering_discount_percent = State()
    entering_discount_usage_limit = State()
    entering_support_contact = State()   # ثبت آیدی پشتیبانی که به مشتری نمایش داده می‌شود


# ---------- ناوبری پوشه‌ای کاتالوگ برای مشتری (کیبورد پایین صفحه، نه inline) ----------
class CustomerCatalogStates(StatesGroup):
    browsing_operators = State()      # لیست اپراتورها (پوشه اصلی)
    browsing_subcategories = State()  # لیست زیرپوشه‌ها (ماهانه/هفتگی/...) یک اپراتور خاص
    browsing_packages = State()       # لیست بسته‌های یک زیرپوشه خاص
    package_selected = State()        # یک بسته انتخاب شده، منتظر تأیید دکمه‌ی «خرید»
    entering_phone_number = State()   # منتظر شماره‌خطی که بسته باید رویش فعال شود


# ---------- افزایش موجودی کیف‌پول مشتری ----------
class CustomerWalletStates(StatesGroup):
    choosing_method = State()   # کارت‌به‌کارت یا زرین‌پال
    entering_amount = State()
    uploading_receipt = State()


class SuperAdminResellerStates(StatesGroup):
    entering_bot_token = State()
    entering_telegram_id = State()
    entering_commission_percent = State()
    entering_credit_limit = State()
    entering_order_prefix = State()


class SuperAdminResellerEditStates(StatesGroup):
    entering_new_commission_percent = State()   # ویرایش کمیسیون یک نماینده‌ی موجود


class SuperAdminCryptoStates(StatesGroup):
    entering_coin = State()
    entering_address = State()
    entering_network = State()
    entering_price = State()


class SuperAdminBlacklistStates(StatesGroup):
    entering_telegram_id = State()
    entering_reason = State()


class SuperAdminBroadcastStates(StatesGroup):
    entering_text = State()
