import asyncio
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        while True:
            message = await ws.recv()
            print(message)

asyncio.run(main())
