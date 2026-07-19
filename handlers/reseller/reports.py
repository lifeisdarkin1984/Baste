"""
گزارش‌ها: فروش روز/ماه، سود واقعی، خروجی اکسل (بخش ۷ اسپک).
"""
import os
import tempfile

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile

from services.report_service import reseller_sales_summary, build_excel_report
from utils.keyboards import reports_submenu, back_to_reseller_menu_button

router = Router(name="reseller_reports")


@router.callback_query(F.data == "rmenu:reports")
async def show_report_cb(callback: CallbackQuery, reseller_id: int):
    summary = await reseller_sales_summary(reseller_id, days=30)
    await callback.message.edit_text(
        f"📊 گزارش ۳۰ روز اخیر\n\n"
        f"تعداد سفارش فعال‌شده: {summary['order_count']}\n"
        f"فروش کل: {summary['total_sales']:,.0f} تومان\n"
        f"قیمت تمام‌شده: {summary['total_cost']:,.0f} تومان\n"
        f"کمیسیون پرداختی: {summary['total_commission_paid']:,.0f} تومان\n"
        f"سود واقعی: {summary['real_profit']:,.0f} تومان",
        reply_markup=reports_submenu(),
    )
    await callback.answer()


@router.callback_query(F.data == "reports:excel")
async def export_excel_cb(callback: CallbackQuery, reseller_id: int):
    summary = await reseller_sales_summary(reseller_id, days=30)
    if not summary["orders"]:
        await callback.message.answer("سفارش فعال‌شده‌ای در ۳۰ روز اخیر برای گزارش وجود ندارد.", reply_markup=back_to_reseller_menu_button())
        await callback.answer()
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = os.path.join(tmp_dir, f"report_reseller_{reseller_id}.xlsx")
        build_excel_report(summary["orders"], filepath)
        await callback.message.answer_document(
            FSInputFile(filepath), caption="گزارش فروش ۳۰ روز اخیر", reply_markup=back_to_reseller_menu_button()
        )
    await callback.answer()
