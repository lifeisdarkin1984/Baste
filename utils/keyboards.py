"""
کیبوردهای شیشه‌ای رنگی — بخش ۹ اسپک.
نیازمند Bot API >= 9.4 و aiogram >= 3.20 (فیلد style روی InlineKeyboardButton).
رنگ‌ها: primary (آبی) / success (سبز) / danger (قرمز)
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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
    return InlineKeyboardMarkup(inline_keyboard=[[toggle]])


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
        [InlineKeyboardButton(text="🧩 درخواست‌های فیچر شارژ/VPN", callback_data="amenu:features:pending", style="primary")],
        [InlineKeyboardButton(text="💎 تنظیم رمزارز", callback_data="amenu:features:crypto", style="primary")],
        [InlineKeyboardButton(text="🚫 لیست سیاه", callback_data="amenu:features:blacklist", style="primary")],
        [InlineKeyboardButton(text="📢 ارسال اطلاعیه همگانی", callback_data="amenu:features:broadcast", style="primary")],
        [InlineKeyboardButton(text="🧾 پرداخت قبوض", callback_data="amenu:features:bills", style="primary")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="amenu:home", style="primary")],
    ])


def feature_decision_buttons(flag_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید", callback_data=f"feature_approve:{flag_id}", style="success"),
            InlineKeyboardButton(text="❌ رد", callback_data=f"feature_reject:{flag_id}", style="danger"),
        ],
    ])


def blacklist_add_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن به لیست سیاه", callback_data="blacklist_add_start", style="danger")],
    ])


def bills_toggle_buttons(currently_enabled: bool) -> InlineKeyboardMarkup:
    if currently_enabled:
        btn = InlineKeyboardButton(text="🔴 غیرفعال‌سازی پرداخت قبوض", callback_data="bills_set:off", style="danger")
    else:
        btn = InlineKeyboardButton(text="🟢 فعال‌سازی پرداخت قبوض", callback_data="bills_set:on", style="success")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


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
