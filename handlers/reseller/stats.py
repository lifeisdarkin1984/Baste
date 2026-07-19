"""
آمار پیشرفته مشتری برای نماینده (فاز ۳ اسپک).
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.customer_stats_service import top_customers, repeat_customer_rate, average_order_value
from utils.keyboards import back_to_reseller_menu_button

router = Router(name="reseller_stats")


@router.callback_query(F.data == "rmenu:stats")
async def show_stats_cb(callback: CallbackQuery, reseller_id: int):
    repeat = await repeat_customer_rate(reseller_id)
    avg_value = await average_order_value(reseller_id)
    top = await top_customers(reseller_id)

    text = (
        f"👥 تعداد کل مشتریان با سفارش موفق: {repeat['total_customers']}\n"
        f"🔁 مشتریان تکراری: {repeat['repeat_customers']} ({repeat['repeat_rate_percent']:.1f}٪)\n"
        f"💰 میانگین ارزش سفارش: {avg_value:,.0f} تومان"
    )
    if top:
        lines = [f"{i+1}. {r['telegram_user_id']} | {r['order_count']} سفارش | {r['total_spent']:,.0f} تومان" for i, r in enumerate(top)]
        text += "\n\n🏆 برترین مشتریان:\n" + "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=back_to_reseller_menu_button())
    await callback.answer()
