import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, TypeHandler, filters, ApplicationHandlerStop

async def enforce(update, context):
    print("enforce")
    raise ApplicationHandlerStop

async def handler1(update, context):
    print("handler1")

async def handler2(update, context):
    print("handler2")

async def main():
    app = Application.builder().token("123").build()
    app.add_handler(TypeHandler(Update, enforce), group=-1)
    app.add_handler(MessageHandler(filters.ALL, handler1), group=0)
    app.add_handler(MessageHandler(filters.ALL, handler2), group=99)
    
    # simulate update
    class DummyUpdate:
        pass
    update = DummyUpdate()
    await app.process_update(update)

asyncio.run(main())
