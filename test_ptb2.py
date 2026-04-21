import asyncio
from telegram import Update, Message, Chat
from telegram.ext import Application, MessageHandler, TypeHandler, filters, ApplicationHandlerStop

async def enforce(update, context):
    print("enforce executed")
    raise ApplicationHandlerStop

async def handler1(update, context):
    print("handler1 executed")

async def handler2(update, context):
    print("handler2 executed")

async def main():
    app = Application.builder().token("12345:ABC").build()
    app.add_handler(TypeHandler(Update, enforce), group=-1)
    
    # We will simulate a message
    async def process():
        msg = Message(message_id=1, date=None, chat=Chat(id=1, type="private"), text="test")
        update = Update(update_id=1, message=msg)
        print("Dispatching update...")
        await app.process_update(update)
    
    await process()

if __name__ == "__main__":
    asyncio.run(main())
