"""
گزارش‌ها: فروش روز/ماه، سود واقعی، خروجی اکسل (بخش ۷ اسپک، فاز ۲).
"""
import os
import tempfile

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from services.report_service import reseller_sales_summary, build_excel_report

router = Router(name="reseller_reports")


@router.message(Command("report"))
async def show_report(message: Message, reseller_id: int):
    summary = await reseller_sales_summary(reseller_id, days=30)
    await message.answer(
        f"📊 گزارش ۳۰ روز اخیر\n\n"
        f"تعداد سفارش فعال‌شده: {summary['order_count']}\n"
        f"فروش کل: {summary['total_sales']:,.0f} تومان\n"
        f"قیمت تمام‌شده: {summary['total_cost']:,.0f} تومان\n"
        f"کمیسیون پرداختی: {summary['total_commission_paid']:,.0f} تومان\n"
        f"سود واقعی: {summary['real_profit']:,.0f} تومان\n\n"
        f"برای خروجی اکسل: /report_excel"
    )


@router.message(Command("report_excel"))
async def export_excel(message: Message, reseller_id: int):
    summary = await reseller_sales_summary(reseller_id, days=30)
    if not summary["orders"]:
        await message.answer("سفارش فعال‌شده‌ای در ۳۰ روز اخیر برای گزارش وجود ندارد.")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = os.path.join(tmp_dir, f"report_reseller_{reseller_id}.xlsx")
        build_excel_report(summary["orders"], filepath)
        await message.answer_document(FSInputFile(filepath), caption="گزارش فروش ۳۰ روز اخیر")
