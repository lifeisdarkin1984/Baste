"""
تنظیمات نماینده در فاز ۲: کدهای تخفیف، رفرال، جوین اجباری، درخواست فروش
شارژ/VPN، شارژ کیف‌پول با زرین‌پال/رمزارز.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from database.db import execute, fetch_one
from services.discount_service import validate_discount_code  # noqa: F401 (used by customer flow)
from services.referral_service import set_referral_enabled, set_referral_profit_percent, get_referral_settings
from services.forced_join_service import add_forced_channel, get_forced_channels
from services.feature_flag_service import request_feature
from services.zarinpal_service import create_payment_request, PLATFORM_ZARINPAL_MERCHANT_ID
from services.crypto_service import list_crypto_options, request_crypto_topup

router = Router(name="reseller_settings")


# ---------- کدهای تخفیف ----------
@router.message(Command("add_discount"))
async def add_discount_code(message: Message, reseller_id: int):
    """فرمت: /add_discount CODE PERCENT USAGE_LIMIT   مثال: /add_discount EID10 10 100"""
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("فرمت درست: /add_discount CODE PERCENT USAGE_LIMIT")
        return
    _, code, percent, usage_limit = parts
    try:
        percent_d = Decimal(percent)
        usage_limit_i = int(usage_limit)
    except (InvalidOperation, ValueError):
        await message.answer("درصد و سقف استفاده باید عدد باشند.")
        return

    await execute(
        "INSERT INTO discount_codes (reseller_id, code, percent, usage_limit) VALUES (%s, %s, %s, %s)",
        (reseller_id, code.strip().upper(), percent_d, usage_limit_i),
    )
    await message.answer(f"کد تخفیف {code.upper()} با {percent_d}٪ تخفیف ثبت شد ✅")


# ---------- رفرال ----------
@router.message(Command("referral_on"))
async def referral_on(message: Message, reseller_id: int):
    await set_referral_enabled(reseller_id, True)
    await message.answer("رفرال فعال شد ✅. برای تنظیم درصد سود: /referral_percent <عدد>")


@router.message(Command("referral_off"))
async def referral_off(message: Message, reseller_id: int):
    await set_referral_enabled(reseller_id, False)
    await message.answer("رفرال غیرفعال شد.")


@router.message(F.text.startswith("/referral_percent "))
async def referral_percent(message: Message, reseller_id: int):
    try:
        percent = Decimal(message.text.split()[1])
    except (InvalidOperation, IndexError):
        await message.answer("فرمت درست: /referral_percent 5")
        return
    await set_referral_profit_percent(reseller_id, percent)
    await message.answer(f"درصد سود رفرال روی {percent}٪ تنظیم شد ✅")


@router.message(Command("referral_status"))
async def referral_status(message: Message, reseller_id: int):
    settings = await get_referral_settings(reseller_id)
    status = "فعال" if settings["is_enabled"] else "غیرفعال"
    await message.answer(f"وضعیت رفرال: {status}\nدرصد سود: {settings['profit_percent']}٪")


# ---------- جوین اجباری ----------
@router.message(F.text.startswith("/add_channel "))
async def add_channel(message: Message, reseller_id: int):
    channel_id = message.text.split(maxsplit=1)[1].strip()
    await add_forced_channel(reseller_id, channel_id, set_by="reseller")
    await message.answer(f"کانال {channel_id} به لیست جوین اجباری اضافه شد ✅")


@router.message(Command("list_channels"))
async def list_channels(message: Message, reseller_id: int):
    channels = await get_forced_channels(reseller_id)
    if not channels:
        await message.answer("کانال جوین اجباری تنظیم نشده.")
        return
    await message.answer("\n".join(f"- {c['channel_id']}" for c in channels))


# ---------- درخواست فیچر شارژ/VPN ----------
@router.message(Command("request_recharge"))
async def request_recharge_feature(message: Message, reseller_id: int):
    await request_feature(reseller_id, "recharge")
    await message.answer("درخواست فعال‌سازی فروش شارژ برای مدیر کل ارسال شد؛ منتظر تأیید باشید.")


@router.message(Command("request_vpn"))
async def request_vpn_feature(message: Message, reseller_id: int):
    await request_feature(reseller_id, "vpn")
    await message.answer("درخواست فعال‌سازی فروش VPN برای مدیر کل ارسال شد؛ منتظر تأیید باشید.")


# ---------- شارژ کیف‌پول: زرین‌پال ----------
# ---------- شارژ کیف‌پول کمیسیون (نزد پلتفرم) با زرین‌پال ----------
# توجه: این برای شارژ اعتبار کمیسیون خود نماینده نزد پلتفرم است، نه دریافت وجه
# از مشتری. برای دریافت وجه بسته از مشتری به handlers/reseller/payment_methods.py
# مراجعه کن («روش دریافت وجه از مشتری»).
@router.message(F.text.startswith("/topup_zarinpal "))
async def topup_zarinpal(message: Message, reseller_id: int):
    try:
        amount = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("فرمت درست: /topup_zarinpal 100000")
        return
    try:
        link, authority = await create_payment_request(
            PLATFORM_ZARINPAL_MERCHANT_ID,
            amount,
            f"شارژ کیف‌پول نماینده {reseller_id}",
            callback_url="https://example.com/zarinpal/callback",
        )
    except Exception as e:
        await message.answer(f"خطا در اتصال به زرین‌پال: {e}")
        return
    await message.answer(f"برای پرداخت {amount:,.0f} تومان روی لینک زیر بزنید:\n{link}")


# ---------- شارژ کیف‌پول: رمزارز ----------
@router.message(Command("topup_crypto"))
async def topup_crypto_options(message: Message):
    options = await list_crypto_options()
    if not options:
        await message.answer("در حال حاضر روش شارژ رمزارزی توسط مدیر کل تنظیم نشده.")
        return
    lines = [
        f"{o['coin_name']} ({o['network']}) -> آدرس: {o['address']} | نرخ: {o['price']:,.0f} تومان"
        for o in options
    ]
    lines.append(
        "\nبعد از واریز، هش تراکنش را با فرمت زیر ارسال کنید:\n"
        "/confirm_crypto <coin_name> <tx_hash> <مبلغ_تخمینی_تومان>"
    )
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/confirm_crypto "))
async def confirm_crypto(message: Message, reseller_id: int):
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("فرمت درست: /confirm_crypto USDT 0xabc... 500000")
        return
    _, coin_name, tx_hash, amount = parts
    try:
        amount_d = Decimal(amount)
    except InvalidOperation:
        await message.answer("مبلغ باید عدد باشد.")
        return
    await request_crypto_topup(reseller_id, coin_name, tx_hash, amount_d)
    await message.answer("درخواست شارژ رمزارزی ثبت شد و برای تأیید مدیر کل ارسال شد.")
