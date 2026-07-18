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
