"""
آمار پیشرفته مشتری برای نماینده (فاز ۳ اسپک).
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.customer_stats_service import top_customers, repeat_customer_rate, average_order_value

router = Router(name="reseller_stats")


@router.message(Command("top_customers"))
async def show_top_customers(message: Message, reseller_id: int):
    rows = await top_customers(reseller_id)
    if not rows:
        await message.answer("هنوز داده‌ای برای گزارش وجود ندارد.")
        return
    lines = [
        f"{i+1}. {r['telegram_user_id']} | {r['order_count']} سفارش | {r['total_spent']:,.0f} تومان"
        for i, r in enumerate(rows)
    ]
    await message.answer("🏆 برترین مشتریان:\n" + "\n".join(lines))


@router.message(Command("customer_stats"))
async def show_customer_stats(message: Message, reseller_id: int):
    repeat = await repeat_customer_rate(reseller_id)
    avg_value = await average_order_value(reseller_id)
    await message.answer(
        f"👥 تعداد کل مشتریان با سفارش موفق: {repeat['total_customers']}\n"
        f"🔁 مشتریان تکراری: {repeat['repeat_customers']} ({repeat['repeat_rate_percent']:.1f}٪)\n"
        f"💰 میانگین ارزش سفارش: {avg_value:,.0f} تومان"
    )
