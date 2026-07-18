"""
💳 روش دریافت وجه از مشتری (بخش جدا از کیف‌پول کمیسیون پلتفرم!)

کیف‌پول کمیسیون (handlers/reseller/wallet.py و services/wallet_service.py)
یک اعتبار پیش‌شارژشده‌ی داخلی است که پلتفرم از آن کمیسیون کسر می‌کند.

این بخش کاملاً چیز دیگری است: حساب/کارت شخصی خود نماینده که مشتری مستقیماً
پول بسته را به آن واریز می‌کند. نماینده می‌تواند چند کارت (چند بانک) ثبت کند
و هرکدام را جدا روشن/خاموش کند، و اگر زرین‌پال شخصی دارد، مرچنت‌کد آن را هم
همینجا تنظیم می‌کند تا مستقیماً به حساب خودش واریز شود.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from services.payment_methods_service import (
    add_card,
    list_cards,
    toggle_card,
    remove_card,
    set_zarinpal_merchant,
    get_zarinpal_merchant,
    format_card_number,
)

router = Router(name="reseller_payment_methods")


@router.message(F.text.startswith("/add_card "))
async def add_payment_card(message: Message, reseller_id: int):
    """
    فرمت: /add_card شماره‌کارت نام‌صاحب‌کارت [نام‌بانک]
    مثال: /add_card 6037991234567890 علی رضایی بانک ملی
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "فرمت درست:\n/add_card شماره‌کارت نام‌صاحب‌کارت [نام‌بانک]\n"
            "مثال:\n/add_card 6037991234567890 علی رضایی بانک ملی"
        )
        return

    rest = parts[1].split(maxsplit=1)
    if len(rest) < 2:
        await message.answer("نام صاحب کارت را هم وارد کنید.")
        return

    card_number = rest[0].replace("-", "").replace(" ", "").strip()
    remainder = rest[1].strip()

    if not (card_number.isdigit() and len(card_number) == 16):
        await message.answer("شماره کارت باید دقیقاً ۱۶ رقم باشد (بدون فاصله یا خط تیره).")
        return

    # اگر کلمه‌ی «بانک» توی باقی متن باشه، از اونجا به بعد نام بانک در نظر
    # گرفته می‌شه؛ در غیر این صورت کل باقی متن نام صاحب کارت است.
    card_holder_name = remainder
    bank_name = None
    if "بانک" in remainder:
        idx = remainder.find("بانک")
        card_holder_name = remainder[:idx].strip()
        bank_name = remainder[idx:].strip()

    card_id = await add_card(reseller_id, card_number, card_holder_name, bank_name)
    formatted = format_card_number(card_number)
    await message.answer(
        f"کارت جدید ثبت شد ✅ (شناسه #{card_id})\n💳 {formatted}\n👤 به‌نام: {card_holder_name}"
        + (f"\n🏦 {bank_name}" if bank_name else "")
        + "\n\nاین کارت از حالا (به‌صورت فعال) موقع خرید به مشتری نشان داده می‌شود."
    )


@router.message(Command("my_cards"))
async def my_cards(message: Message, reseller_id: int):
    cards = await list_cards(reseller_id)
    if not cards:
        await message.answer(
            "هنوز کارتی ثبت نکرده‌اید.\nبرای ثبت: /add_card شماره‌کارت نام‌صاحب‌کارت [نام‌بانک]"
        )
        return

    lines = []
    for c in cards:
        status = "✅ فعال" if c["is_active"] else "⛔️ غیرفعال"
        lines.append(
            f"#{c['id']} | {format_card_number(c['card_number'])} | {c['card_holder_name']}"
            + (f" | {c['bank_name']}" if c["bank_name"] else "")
            + f" | {status}"
        )
    lines.append(
        "\nروشن/خاموش کردن: /toggle_card <شناسه>\n"
        "حذف: /remove_card <شناسه>"
    )
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/toggle_card "))
async def toggle_payment_card(message: Message, reseller_id: int):
    try:
        card_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("فرمت درست: /toggle_card <شناسه کارت>")
        return

    new_status = await toggle_card(card_id, reseller_id)
    if new_status is None:
        await message.answer("این کارت پیدا نشد (یا متعلق به شما نیست).")
        return
    await message.answer(f"کارت #{card_id} حالا {'✅ فعال' if new_status else '⛔️ غیرفعال'} است.")


@router.message(F.text.startswith("/remove_card "))
async def remove_payment_card(message: Message, reseller_id: int):
    try:
        card_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("فرمت درست: /remove_card <شناسه کارت>")
        return

    removed = await remove_card(card_id, reseller_id)
    await message.answer(f"کارت #{card_id} حذف شد ✅" if removed else "این کارت پیدا نشد.")


# ---------- زرین‌پال شخصی نماینده (برای دریافت مستقیم وجه از مشتری) ----------
@router.message(F.text.startswith("/set_zarinpal "))
async def set_own_zarinpal(message: Message, reseller_id: int):
    """فرمت: /set_zarinpal مرچنت‌کد"""
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("فرمت درست: /set_zarinpal <مرچنت‌کد زرین‌پال شما>")
        return
    await set_zarinpal_merchant(reseller_id, parts[1].strip())
    await message.answer(
        "مرچنت‌کد زرین‌پال شما ثبت شد ✅ و از حالا موقع خرید به مشتری لینک پرداخت آنلاین نشان داده می‌شود."
    )


@router.message(Command("my_zarinpal"))
async def show_own_zarinpal(message: Message, reseller_id: int):
    merchant_id = await get_zarinpal_merchant(reseller_id)
    if not merchant_id:
        await message.answer("هنوز مرچنت‌کد زرین‌پال ثبت نکرده‌اید.\nبرای ثبت: /set_zarinpal <مرچنت‌کد>")
        return
    await message.answer(f"مرچنت‌کد فعلی: {merchant_id}")
