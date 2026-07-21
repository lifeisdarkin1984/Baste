"""
کیبوردهای شیشه‌ای رنگی — بخش ۹ اسپک.
نیازمند Bot API >= 9.4 و aiogram >= 3.20 (فیلد style روی InlineKeyboardButton).
رنگ‌ها: primary (آبی) / success (سبز) / danger (قرمز)
"""
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


# ==========================================================================
# کیبورد پایین صفحه (Reply Keyboard) برای مشتری — به‌جای دکمه‌ی شیشه‌ای توی چت.
# متن دکمه‌ها عیناً به‌عنوان فیلتر F.text تو هندلرها استفاده می‌شه، پس این
# ثابت‌ها رو عوض نکن مگر اینکه هندلر مربوطه رو هم آپدیت کنی.
# ==========================================================================
CUSTOMER_CATALOG_BUTTON_TEXT = "🛒 خرید بسته"
CUSTOMER_SUPPORT_BUTTON_TEXT = "📞 پشتیبانی"
CUSTOMER_WALLET_BUTTON_TEXT = "💰 کیف پول من"
CUSTOMER_BACK_BUTTON_TEXT = "⬅️ بازگشت"
CUSTOMER_BACK_TO_MENU_BUTTON_TEXT = "🏠 بازگشت به منوی اصلی"
CUSTOMER_TOPUP_BUTTON_TEXT = "💳 افزایش موجودی"
CUSTOMER_TOPUP_CARD_BUTTON_TEXT = "💳 کارت‌به‌کارت"
CUSTOMER_TOPUP_ZARINPAL_BUTTON_TEXT = "🌐 زرین‌پال"
CUSTOMER_BUY_BUTTON_TEXT = "🛒 خرید این بسته"
CUSTOMER_CHARGE_BUTTON_TEXT = "🔋 خرید کارت شارژ"
CUSTOMER_BUY_CHARGE_BUTTON_TEXT = "🔋 خرید این شارژ"


def customer_main_reply_keyboard(has_support_contact: bool = True) -> ReplyKeyboardMarkup:
    """کیبورد ثابت پایین صفحه‌ی مشتری. resize_keyboard کوچیکش می‌کنه که کل صفحه رو نگیره."""
    rows = [
        [KeyboardButton(text=CUSTOMER_CATALOG_BUTTON_TEXT, style="primary")],
        [KeyboardButton(text=CUSTOMER_CHARGE_BUTTON_TEXT, style="primary")],
        [KeyboardButton(text=CUSTOMER_WALLET_BUTTON_TEXT, style="success")],
    ]
    if has_support_contact:
        rows.append([KeyboardButton(text=CUSTOMER_SUPPORT_BUTTON_TEXT, style="primary")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def customer_folder_reply_keyboard(item_names: list[str], back_text: str = CUSTOMER_BACK_TO_MENU_BUTTON_TEXT) -> ReplyKeyboardMarkup:
    """کیبورد پایین صفحه برای نمایش لیست پوشه/زیرپوشه/بسته به‌صورت دکمه‌ی متنی، یکی در هر ردیف."""
    rows = [[KeyboardButton(text=name, style="primary")] for name in item_names]
    rows.append([KeyboardButton(text=back_text, style="danger")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def customer_package_detail_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد پایین صفحه بعد از انتخاب یک بسته‌ی مشخص: دکمه‌ی متنی «خرید» + بازگشت."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CUSTOMER_BUY_BUTTON_TEXT, style="success")],
            [KeyboardButton(text=CUSTOMER_BACK_BUTTON_TEXT, style="danger")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def customer_charge_detail_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد پایین صفحه بعد از انتخاب یک شارژ سطح مشخص: دکمه‌ی متنی «خرید» + بازگشت."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CUSTOMER_BUY_CHARGE_BUTTON_TEXT, style="success")],
            [KeyboardButton(text=CUSTOMER_BACK_BUTTON_TEXT, style="danger")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def customer_charge_quantity_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد پایین صفحه موقع تایپ تعداد در خرید عمده‌ی شارژ: فقط دکمه‌ی بازگشت (خودِ عدد با کیبورد سیستم تایپ می‌شود)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CUSTOMER_BACK_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


CUSTOMER_SHARE_PHONE_BUTTON_TEXT = "📱 ارسال شماره تلفنم"


def customer_phone_number_keyboard() -> ReplyKeyboardMarkup:
    """
    کیبورد مرحله‌ی وارد کردن شماره‌خط برای فعال‌سازی بسته: یا دکمه‌ی اشتراک
    مخاطب تلگرام (request_contact) یا تایپ دستی شماره (چون ممکنه شماره‌ی
    موردنظر برای شارژ، با شماره‌ی اکانت تلگرام مشتری فرق داشته باشه)، + بازگشت.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CUSTOMER_SHARE_PHONE_BUTTON_TEXT, request_contact=True, style="primary")],
            [KeyboardButton(text=CUSTOMER_BACK_BUTTON_TEXT, style="danger")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def customer_wallet_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CUSTOMER_TOPUP_BUTTON_TEXT, style="success")],
            [KeyboardButton(text=CUSTOMER_BACK_TO_MENU_BUTTON_TEXT, style="danger")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def customer_topup_method_keyboard(has_card: bool, has_zarinpal: bool) -> ReplyKeyboardMarkup:
    rows = []
    if has_card:
        rows.append([KeyboardButton(text=CUSTOMER_TOPUP_CARD_BUTTON_TEXT, style="primary")])
    if has_zarinpal:
        rows.append([KeyboardButton(text=CUSTOMER_TOPUP_ZARINPAL_BUTTON_TEXT, style="primary")])
    rows.append([KeyboardButton(text=CUSTOMER_BACK_BUTTON_TEXT, style="danger")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def catalog_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 مشاهده کاتالوگ", callback_data="show_catalog", style="primary")],
    ])


def topup_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 افزایش موجودی", callback_data="topup", style="primary")],
    ])


def package_purchase_button(package_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 خرید بسته", callback_data=f"buy:{package_id}", style="success")],
    ])


def order_review_buttons(order_id: int) -> InlineKeyboardMarkup:
    """دکمه‌های تأیید/رد رسید برای نماینده یا اپراتور."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید رسید", callback_data=f"approve_receipt:{order_id}", style="success"),
            InlineKeyboardButton(text="❌ رد رسید (فیک)", callback_data=f"reject_receipt:{order_id}", style="danger"),
        ],
    ])


def activate_order_button(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 فعال شد", callback_data=f"activate_order:{order_id}", style="success")],
    ])


def sanity_check_confirm_buttons(pending_token: str) -> InlineKeyboardMarkup:
    """تأیید صریح نماینده بعد از هشدار قیمت غیرمنطقی."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ بله، قیمت درست است", callback_data=f"price_confirm:{pending_token}", style="success"),
            InlineKeyboardButton(text="✏️ اصلاح قیمت", callback_data=f"price_edit:{pending_token}", style="danger"),
        ],
    ])


def wallet_topup_review_buttons(topup_id: int) -> InlineKeyboardMarkup:
    """دکمه‌های تأیید/رد رسید افزایش موجودی کیف‌پول مشتری، برای نماینده/اپراتور."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید و شارژ کیف‌پول", callback_data=f"wallet_topup_confirm:{topup_id}", style="success"),
            InlineKeyboardButton(text="❌ رد رسید", callback_data=f"wallet_topup_reject:{topup_id}", style="danger"),
        ],
    ])


def dispute_button(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 ثبت درخواست استرداد", callback_data=f"open_dispute:{order_id}", style="danger")],
    ])


# ==========================================================================
# فاز ۲ — منوهای پنل مدیریت کل (بخش ۷ و ۹ اسپک)
# ==========================================================================

def admin_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 مدیریت نماینده‌ها", callback_data="amenu:resellers", style="primary")],
        [InlineKeyboardButton(text="💰 کیف‌پول و استرداد", callback_data="amenu:wallet", style="primary")],
        [InlineKeyboardButton(text="⚙️ فیچرها و تنظیمات", callback_data="amenu:features", style="primary")],
        [InlineKeyboardButton(text="📊 گزارش پلتفرم", callback_data="amenu:report", style="primary")],
        [InlineKeyboardButton(text="🗄 بک‌آپ و ریستور", callback_data="amenu:backup", style="primary")],
    ])


def back_to_admin_menu_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به منوی اصلی", callback_data="amenu:home", style="primary")],
    ])


def admin_resellers_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن نماینده جدید", callback_data="amenu:resellers:add", style="success")],
        [InlineKeyboardButton(text="📋 لیست نماینده‌ها", callback_data="amenu:resellers:list", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="amenu:home", style="primary")],
    ])


def reseller_row_buttons(reseller_id: int, status: str) -> InlineKeyboardMarkup:
    if status == "active":
        toggle = InlineKeyboardButton(text="⏸ تعلیق", callback_data=f"reseller_toggle:{reseller_id}:suspended", style="danger")
    else:
        toggle = InlineKeyboardButton(text="▶️ فعال‌سازی", callback_data=f"reseller_toggle:{reseller_id}:active", style="success")
    edit_commission = InlineKeyboardButton(
        text="✏️ تغییر کمیسیون", callback_data=f"reseller_edit_commission:{reseller_id}", style="primary"
    )
    return InlineKeyboardMarkup(inline_keyboard=[[toggle], [edit_commission]])


def admin_wallet_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 شارژهای در انتظار تأیید", callback_data="amenu:wallet:topups", style="primary")],
        [InlineKeyboardButton(text="🚨 درخواست‌های استرداد", callback_data="amenu:wallet:disputes", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="amenu:home", style="primary")],
    ])


def topup_confirm_button(transaction_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأیید شارژ", callback_data=f"topup_confirm:{transaction_id}", style="success")],
    ])


def dispute_decision_buttons(dispute_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید استرداد", callback_data=f"dispute_approve:{dispute_id}", style="success"),
            InlineKeyboardButton(text="❌ رد استرداد", callback_data=f"dispute_reject:{dispute_id}", style="danger"),
        ],
    ])


def admin_features_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 تنظیم رمزارز", callback_data="amenu:features:crypto", style="primary")],
        [InlineKeyboardButton(text="🚫 لیست سیاه", callback_data="amenu:features:blacklist", style="primary")],
        [InlineKeyboardButton(text="📢 ارسال اطلاعیه همگانی", callback_data="amenu:features:broadcast", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="amenu:home", style="primary")],
    ])


def blacklist_add_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن به لیست سیاه", callback_data="blacklist_add_start", style="danger")],
    ])


def admin_backup_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗄 گرفتن بک‌آپ الان", callback_data="backup_take", style="success")],
        [InlineKeyboardButton(text="♻️ شروع ریستور", callback_data="backup_restore_start", style="danger")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="amenu:home", style="primary")],
    ])


def restore_confirm_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید نهایی ریستور", callback_data="restore_confirm", style="danger"),
            InlineKeyboardButton(text="❌ لغو", callback_data="restore_cancel", style="primary"),
        ],
    ])


# ==========================================================================
# فاز ۳ — منوهای پنل نماینده (بخش ۵ و ۷ اسپک)
# ==========================================================================

def reseller_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 کاتالوگ", callback_data="rmenu:catalog", style="primary"),
            InlineKeyboardButton(text="🧾 سفارش‌ها", callback_data="rmenu:orders", style="primary"),
        ],
        [
            InlineKeyboardButton(text="💰 کیف‌پول کمیسیون", callback_data="rmenu:wallet", style="primary"),
            InlineKeyboardButton(text="💳 روش دریافت وجه", callback_data="rmenu:payment_methods", style="primary"),
        ],
        [
            InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="rmenu:settings", style="primary"),
            InlineKeyboardButton(text="📊 گزارش فروش", callback_data="rmenu:reports", style="primary"),
        ],
        [
            InlineKeyboardButton(text="👥 آمار مشتریان", callback_data="rmenu:stats", style="primary"),
            InlineKeyboardButton(text="🎫 مدیریت شارژ", callback_data="rmenu:charge_stock", style="primary"),
        ],
    ])


def back_to_reseller_menu_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به منوی اصلی", callback_data="rmenu:home", style="primary")],
    ])


# ---------- کاتالوگ (دو بخش: بسته‌ی اینترنتی / شارژ، هرکدام پوشه‌ای دو سطحی) ----------
def catalog_type_menu() -> InlineKeyboardMarkup:
    """انتخاب اینکه کدوم کاتالوگ رو مدیریت می‌کنیم: بسته‌های اینترنتی یا شارژ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 بسته‌های اینترنتی", callback_data="catalog:menu:package", style="primary")],
        [InlineKeyboardButton(text="🔋 شارژ", callback_data="catalog:menu:charge", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


def catalog_submenu(catalog_type: str = "package") -> InlineKeyboardMarkup:
    add_item_text = "➕ افزودن بسته" if catalog_type == "package" else "➕ افزودن محصول شارژ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 مشاهده کاتالوگ", callback_data=f"catalog:view:{catalog_type}", style="primary")],
        [InlineKeyboardButton(text="📁 افزودن اپراتور (پوشه اصلی)", callback_data=f"catalog:add_operator:{catalog_type}", style="success")],
        [InlineKeyboardButton(text="📂 افزودن زیرپوشه (ماهانه/هفتگی/...)", callback_data=f"catalog:add_subcategory:{catalog_type}", style="success")],
        [InlineKeyboardButton(text=add_item_text, callback_data=f"catalog:add_package:{catalog_type}", style="success")],
        [InlineKeyboardButton(text="📋 مدیریت/ویرایش پوشه‌ها", callback_data=f"catalog:manage:{catalog_type}", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:catalog", style="primary")],
    ])


# ---------- مدیریت/ویرایش/حذف اپراتور، زیرپوشه، محصول ----------
def catalog_manage_operator_list_buttons(operators: list, catalog_type: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📁 {op['operator_name']}", callback_data=f"catalog:manage_op:{catalog_type}:{op['id']}", style="primary")]
        for op in operators
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"catalog:menu:{catalog_type}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_manage_operator_detail_buttons(catalog_type: str, operator_id: int, subcategories: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"catalog:edit_op_name:{catalog_type}:{operator_id}", style="primary"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"catalog:del_op:{catalog_type}:{operator_id}", style="danger"),
        ],
    ]
    for sub in subcategories:
        rows.append([InlineKeyboardButton(text=f"📂 {sub['title']}", callback_data=f"catalog:manage_sub:{catalog_type}:{sub['id']}", style="primary")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"catalog:manage:{catalog_type}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_manage_subcategory_detail_buttons(catalog_type: str, operator_id: int, subcategory_id: int, products: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✏️ ویرایش عنوان", callback_data=f"catalog:edit_sub_title:{catalog_type}:{subcategory_id}", style="primary"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"catalog:del_sub:{catalog_type}:{subcategory_id}", style="danger"),
        ],
    ]
    for p in products:
        mark = "✅" if p["is_active"] else "⛔️"
        rows.append([InlineKeyboardButton(text=f"{mark} {p['name']}", callback_data=f"catalog:manage_pkg:{catalog_type}:{p['id']}", style="primary")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"catalog:manage_op:{catalog_type}:{operator_id}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_manage_package_detail_buttons(catalog_type: str, subcategory_id: int, package_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⛔️ غیرفعال کردن" if is_active else "✅ فعال کردن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"catalog:edit_pkg_name:{catalog_type}:{package_id}", style="primary"),
            InlineKeyboardButton(text="✏️ ویرایش قیمت فروش", callback_data=f"catalog:edit_pkg_price:{catalog_type}:{package_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="✏️ ویرایش قیمت خرید", callback_data=f"catalog:edit_pkg_cost:{catalog_type}:{package_id}", style="primary"),
            InlineKeyboardButton(text=toggle_text, callback_data=f"catalog:toggle_pkg:{catalog_type}:{package_id}", style=("danger" if is_active else "success")),
        ],
        [InlineKeyboardButton(text="🗑 حذف", callback_data=f"catalog:del_pkg:{catalog_type}:{package_id}", style="danger")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"catalog:manage_sub:{catalog_type}:{subcategory_id}", style="primary")],
    ])


def catalog_delete_confirm_buttons(catalog_type: str, target: str, target_id: int) -> InlineKeyboardMarkup:
    """target: 'op' / 'sub' / 'pkg'"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ بله، حذف کن", callback_data=f"catalog:del_{target}_yes:{catalog_type}:{target_id}", style="danger"),
            InlineKeyboardButton(text="❌ انصراف", callback_data=f"catalog:del_{target}_no:{catalog_type}:{target_id}", style="primary"),
        ],
    ])


def package_edit_price_confirm_buttons(token: str) -> InlineKeyboardMarkup:
    """تأیید صریح نماینده بعد از هشدار قیمت غیرمنطقی، مخصوص فلوی ویرایش قیمت."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ بله، قیمت درست است", callback_data=f"pkgedit_price_confirm:{token}", style="success"),
            InlineKeyboardButton(text="✏️ اصلاح قیمت", callback_data=f"pkgedit_price_edit:{token}", style="danger"),
        ],
    ])


def operator_pick_buttons(operators: list, purpose: str, catalog_type: str = "package") -> InlineKeyboardMarkup:
    """purpose: 'sub' برای انتخاب اپراتور موقع ساخت زیرپوشه، 'pkg' برای انتخاب اپراتور موقع افزودن بسته/محصول."""
    prefix = "catalog:pick_operator_for_sub" if purpose == "sub" else "catalog:pick_operator_for_pkg"
    rows = [
        [InlineKeyboardButton(text=f"📁 {op['operator_name']}", callback_data=f"{prefix}:{catalog_type}:{op['id']}", style="primary")]
        for op in operators
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"catalog:menu:{catalog_type}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_pick_buttons(categories: list, catalog_type: str = "package") -> InlineKeyboardMarkup:
    """انتخاب زیرپوشه (مثلاً ماهانه/هفتگی) برای افزودن بسته/محصول داخلش."""
    rows = [
        [InlineKeyboardButton(text=f"📂 {c['title']}", callback_data=f"catalog:pick_category:{catalog_type}:{c['id']}", style="primary")]
        for c in categories
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"catalog:add_package:{catalog_type}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- سفارش‌ها ----------
def orders_refresh_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی لیست", callback_data="rmenu:orders", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


# ---------- کیف‌پول کمیسیون ----------
def wallet_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 افزایش با کارت‌به‌کارت", callback_data="wallet:topup_card", style="success")],
        [InlineKeyboardButton(text="🌐 افزایش با زرین‌پال", callback_data="wallet:topup_zarinpal", style="success")],
        [InlineKeyboardButton(text="💎 افزایش با رمزارز", callback_data="wallet:topup_crypto", style="success")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


# ---------- روش دریافت وجه (کارت‌های خود نماینده) ----------
def payment_methods_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 کارت‌های من", callback_data="pm:list_cards", style="primary")],
        [InlineKeyboardButton(text="➕ افزودن کارت", callback_data="pm:add_card", style="success")],
        [InlineKeyboardButton(text="🌐 تنظیم زرین‌پال شخصی", callback_data="pm:set_zarinpal", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


def card_row_buttons(card_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle = InlineKeyboardButton(
        text=("⛔️ غیرفعال کردن" if is_active else "✅ فعال کردن"),
        callback_data=f"pm:toggle_card:{card_id}", style=("danger" if is_active else "success"),
    )
    remove = InlineKeyboardButton(text="🗑 حذف", callback_data=f"pm:remove_card:{card_id}", style="danger")
    return InlineKeyboardMarkup(inline_keyboard=[[toggle, remove]])


# ---------- تنظیمات ----------
def settings_submenu(referral_enabled: bool) -> InlineKeyboardMarkup:
    referral_toggle = InlineKeyboardButton(
        text=("🔴 غیرفعال کردن رفرال" if referral_enabled else "🟢 فعال کردن رفرال"),
        callback_data=f"settings:referral_set:{'off' if referral_enabled else 'on'}", style="primary",
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [referral_toggle],
        [InlineKeyboardButton(text="🔢 تنظیم درصد سود رفرال", callback_data="settings:referral_percent", style="primary")],
        [InlineKeyboardButton(text="📢 افزودن کانال جوین اجباری", callback_data="settings:add_channel", style="primary")],
        [InlineKeyboardButton(text="🏷 افزودن کد تخفیف", callback_data="settings:add_discount", style="success")],
        [InlineKeyboardButton(text="📞 ثبت آیدی پشتیبانی", callback_data="settings:set_support_contact", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


# ---------- گزارش‌ها ----------
def reports_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 خروجی اکسل ۳۰ روز اخیر", callback_data="reports:excel", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


# ==========================================================================
# مدیریت موجودی کد شارژ (بخش جدید طبق درخواست): افزودن کد / نمایش موجودی /
# حذف موجودی / کدهای فروخته‌شده. همه از یک مسیر مشترک انتخاب اپراتور ->
# زیرپوشه -> محصول شارژ رد می‌شوند (action در callback_data حفظ می‌شود).
# ==========================================================================
def charge_stock_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن کد", callback_data="cstock:pick:add", style="success")],
        [InlineKeyboardButton(text="📋 نمایش کدهای موجود", callback_data="cstock:pick:list", style="primary")],
        [InlineKeyboardButton(text="🗑 حذف موجودی", callback_data="cstock:pick:remove", style="danger")],
        [InlineKeyboardButton(text="🧾 کدهای فروخته‌شده", callback_data="cstock:pick:sold", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:home", style="primary")],
    ])


def charge_operator_pick_buttons(operators: list, action: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📁 {op['operator_name']}", callback_data=f"cstock:op:{action}:{op['id']}", style="primary")]
        for op in operators
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:charge_stock", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def charge_category_pick_buttons(categories: list, action: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📂 {c['title']}", callback_data=f"cstock:cat:{action}:{c['id']}", style="primary")]
        for c in categories
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="cstock:pick:" + action, style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def charge_product_pick_buttons(products: list, action: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"🔋 {p['name']} — {p['sale_price']:,.0f} تومان ({p.get('available_count', 0)} موجود)",
            callback_data=f"cstock:prod:{action}:{p['id']}", style="primary",
        )]
        for p in products
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:charge_stock", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def charge_code_remove_buttons(codes: list, package_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🗑 {c['code']}", callback_data=f"cstock:delcode:{c['id']}:{package_id}", style="danger")]
        for c in codes
    ]
    rows.append([InlineKeyboardButton(text="🗑 حذف همه‌ی موجودی این محصول", callback_data=f"cstock:clearall:{package_id}", style="danger")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rmenu:charge_stock", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
