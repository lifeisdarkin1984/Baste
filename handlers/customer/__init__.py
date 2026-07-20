from aiogram import Dispatcher
from handlers.customer.orders import router as orders_router
from handlers.customer.charge import router as charge_router
from handlers.customer.wallet import router as wallet_router


def register_customer_handlers(dp: Dispatcher) -> None:
    dp.include_router(orders_router)
    dp.include_router(charge_router)
    dp.include_router(wallet_router)
