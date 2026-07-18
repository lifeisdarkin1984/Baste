from aiogram import Dispatcher
from handlers.operator.orders import router as operator_orders_router


def register_operator_handlers(dp: Dispatcher) -> None:
    dp.include_router(operator_orders_router)
