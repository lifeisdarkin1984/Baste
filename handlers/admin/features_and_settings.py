"""
پنل مدیریت کل — فاز ۲ (بخش ۷ اسپک):
فعال/رد درخواست فیچر، تنظیمات رمزارز، لیست سیاه مشترک، اطلاعیه همگانی،
فعال/غیرفعال‌سازی سراسری پرداخت قبوض، گزارش سود واقعی کل سیستم.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message

from database.db import fetch_all
from services.feature_flag_service import (
    list_pending_features,
    decide_feature,
    set_bills_payment_enabled,
)
from services.crypto_service import upsert_crypto_setting
from services.blacklist_service import list_blacklist, add_to_blacklist
from services.report_service import platform_wide_summary

router = Router(name="admin_features_and_settings")


# ---------- فیچر شارژ/VPN ----------
@router.message(Command("pending_features"))
async def pending_features(message: Message):
    rows = await list_pending_features()
    if not rows:
        await message.answer("درخواست فیچر در انتظاری وجود ندارد.")
        return
    for r in rows:
        await message.answer(
            f"#{r['id']} | نماینده {r['reseller_id']} | فیچر: {r['feature']}\n"
            f"تأیید: /approve_feature {r['id']}\nرد: /reject_feature {r['id']}"
        )


@router.message(F.text.startswith("/approve_feature "))
async def approve_feature(message: Message):
    flag_id = int(message.text.split()[1])
    await decide_feature(flag_id, approve=True)
    await message.answer(f"فیچر #{flag_id} تأیید شد ✅")


@router.message(F.text.startswith("/reject_feature "))
async def reject_feature(message: Message):
    flag_id = int(message.text.split()[1])
    await decide_feature(flag_id, approve=False)
    await message.answer(f"فیچر #{flag_id} رد شد.")


# ---------- تنظیمات رمزارز ----------
@router.message(F.text.startswith("/set_crypto "))
async def set_crypto(message: Message):
    """فرمت: /set_crypto COIN ADDRESS NETWORK PRICE"""
    parts = message.text.split()
    if len(parts) != 5:
        await message.answer("فرمت درست: /set_crypto USDT TXxxxx TRC20 60000")
        return
    _, coin, address, network, price = parts
    try:
        price_d = Decimal(price)
    except InvalidOperation:
        await message.answer("نرخ باید عدد باشد.")
        return
    await upsert_crypto_setting(coin, address, network, price_d)
    await message.answer(f"تنظیمات {coin} ذخیره شد ✅")


# ---------- لیست سیاه مشترک ----------
@router.message(Command("blacklist"))
async def show_blacklist(message: Message):
    rows = await list_blacklist()
    if not rows:
        await message.answer("لیست سیاه خالی است.")
        return
    lines = [f"{r['telegram_user_id']} | {'سراسری' if r['is_global'] else 'محلی'} | {r['reason']}" for r in rows]
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/blacklist_add "))
async def blacklist_add(message: Message):
    """فرمت: /blacklist_add TELEGRAM_ID دلیل..."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("فرمت درست: /blacklist_add 123456789 دلیل")
        return
    telegram_id = int(parts[1])
    reason = parts[2] if len(parts) > 2 else "بدون دلیل ثبت‌شده"
    await add_to_blacklist(telegram_id, reason, reseller_id=None, is_global=True)
    await message.answer(f"کاربر {telegram_id} به لیست سیاه مشترک اضافه شد ✅")


# ---------- اطلاعیه همگانی ----------
@router.message(F.text.startswith("/broadcast "))
async def broadcast_message(message: Message, bot: Bot):
    text = message.text.split(maxsplit=1)[1]
    resellers = await fetch_all("SELECT telegram_numeric_id FROM resellers WHERE status = 'active'")
    sent = 0
    for r in resellers:
        try:
            await bot.send_message(r["telegram_numeric_id"], f"📢 اطلاعیه از مدیریت:\n\n{text}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"اطلاعیه برای {sent} نماینده ارسال شد.")


# ---------- پرداخت قبوض (سراسری) ----------
@router.message(Command("bills_on"))
async def bills_on(message: Message):
    await set_bills_payment_enabled(True)
    await message.answer("قابلیت پرداخت قبوض برای کل پلتفرم فعال شد ✅")


@router.message(Command("bills_off"))
async def bills_off(message: Message):
    await set_bills_payment_enabled(False)
    await message.answer("قابلیت پرداخت قبوض برای کل پلتفرم غیرفعال شد.")


# ---------- گزارش سود واقعی کل سیستم ----------
@router.message(Command("platform_report"))
async def platform_report(message: Message):
    summary = await platform_wide_summary(days=30)
    await message.answer(
        f"📊 گزارش کل پلتفرم (۳۰ روز اخیر)\n\n"
        f"تعداد سفارش فعال‌شده: {summary['order_count']}\n"
        f"فروش کل همه‌ی نماینده‌ها: {summary['total_sales']:,.0f} تومان\n"
        f"کارمزد جمع‌شده مدیریت: {summary['total_commission_collected']:,.0f} تومان\n"
        f"سود کل نماینده‌ها: {summary['total_reseller_profit']:,.0f} تومان"
    )
