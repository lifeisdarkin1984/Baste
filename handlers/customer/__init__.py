from aiogram import Dispatcher
from handlers.customer.orders import router as orders_router
from handlers.customer.bill_payment import router as bill_payment_router


def register_customer_handlers(dp: Dispatcher) -> None:
    dp.include_router(orders_router)
    dp.include_router(bill_payment_router)
