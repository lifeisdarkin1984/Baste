from aiogram import Dispatcher
from handlers.reseller.orders import router as orders_router
from handlers.reseller.catalog import router as catalog_router
from handlers.reseller.wallet import router as wallet_router
from handlers.reseller.settings import router as settings_router
from handlers.reseller.reports import router as reports_router
from handlers.reseller.stats import router as stats_router
from handlers.reseller.bill_payment import router as bill_payment_router
from handlers.reseller.payment_methods import router as payment_methods_router


def register_reseller_handlers(dp: Dispatcher) -> None:
    dp.include_router(orders_router)
    dp.include_router(catalog_router)
    dp.include_router(wallet_router)
    dp.include_router(settings_router)
    dp.include_router(reports_router)
    dp.include_router(stats_router)
    dp.include_router(bill_payment_router)
    dp.include_router(payment_methods_router)
