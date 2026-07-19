"""
نقطه‌ی ورود پنل نماینده (بخش ۷ اسپک) — فاز ۱ از پروژه‌ی «دکمه‌ای کردن همه‌ی پنل‌ها».

این فایل باید تو handlers/reseller/__init__.py قبل از بقیه‌ی روترهای نماینده
(و مهم‌تر، قبل از register_customer_handlers تو core/bot_manager.py) رجیستر
بشه، وگرنه هندلر /start مشتری (handlers/customer/orders.py) این پیام رو
می‌قاپه و صاحب نماینده رو هم به‌عنوان مشتری معمولی می‌بینه.

منطق تشخیص هویت: پیام از طرف telegram_numeric_id ثبت‌شده‌ی همین reseller_id
باشه -> پنل نماینده نشون داده میشه. اگه نبود، این هندلر کاری نمی‌کنه و پیام
به روتر بعدی (مشتری) پاس داده میشه.

نکته برای فازهای بعدی: دکمه‌های زیرمنو فعلاً فقط راهنمای دستور مربوطه رو
نشون می‌دن (چون خود آن هندلرها هنوز دستوری‌ان — فاز ۳ اونا رو کاملاً
دکمه‌ای می‌کند). این فایل فقط مشکل «نبود منوی ورودی» رو حل می‌کند.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.db import fetch_one

router = Router(name="reseller_start")


def reseller_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 بسته‌ها و دسته‌بندی‌ها", callback_data="rmenu:catalog", style="primary"),
            InlineKeyboardButton(text="🧾 سفارش‌ها", callback_data="rmenu:orders", style="primary"),
        ],
        [
            InlineKeyboardButton(text="💰 کیف‌پول", callback_data="rmenu:wallet", style="primary"),
            InlineKeyboardButton(text="💳 روش‌های دریافت وجه", callback_data="rmenu:payment_methods", style="primary"),
        ],
        [
            InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="rmenu:settings", style="primary"),
            InlineKeyboardButton(text="📊 گزارش‌ها و آمار", callback_data="rmenu:reports", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🧾 پرداخت قبوض", callback_data="rmenu:bills", style="primary"),
        ],
    ])


async def _is_reseller_owner(reseller_id: int, telegram_user_id: int) -> bool:
    row = await fetch_one(
        "SELECT id FROM resellers WHERE id = %s AND telegram_numeric_id = %s",
        (reseller_id, telegram_user_id),
    )
    return row is not None


@router.message(F.text.startswith("/start"))
async def reseller_start(message: Message, reseller_id: int):
    if not await _is_reseller_owner(reseller_id, message.from_user.id):
        return  # مشتری معمولی — بگذار روتر مشتری این پیام را بگیرد

    await message.answer(
        "👋 به پنل نماینده خوش آمدید.\n\n"
        "از دکمه‌های زیر برای مدیریت کسب‌وکارتان استفاده کنید:",
        reply_markup=reseller_main_menu(),
    )


_SECTION_HINTS = {
    "catalog": "برای افزودن/ویرایش بسته و دسته‌بندی از دستورهای مربوطه استفاده کنید (این بخش در فاز بعدی کاملاً دکمه‌ای می‌شود).",
    "orders": "برای دیدن سفارش‌های در انتظار: /pending_orders",
    "wallet": "موجودی کیف‌پول: /wallet\nافزایش موجودی: /topup",
    "payment_methods": "افزودن کارت: /add_card\nروشن/خاموش کردن کارت: /toggle_card\nحذف کارت: /remove_card\nتنظیم زرین‌پال: /set_zarinpal",
    "settings": "درصد رفرال: /referral_percent\nافزودن کانال جوین اجباری: /add_channel\nشارژ زرین‌پال: /topup_zarinpal\nتأیید رمزارز: /confirm_crypto",
    "reports": "گزارش‌ها و آمار مشتریان با دستورهای مربوطه در دسترس است (فاز بعدی: دکمه‌ای می‌شود).",
    "bills": "تأیید قبض: /confirm_bill\nرد قبض: /reject_bill\nثبت پرداخت‌شده: /mark_bill_paid",
}


@router.callback_query(F.data.startswith("rmenu:"))
async def reseller_menu_section(callback: CallbackQuery):
    section = callback.data.split(":", 1)[1]
    hint = _SECTION_HINTS.get(section, "به‌زودی تکمیل می‌شود.")
    await callback.message.answer(hint)
    await callback.answer()
