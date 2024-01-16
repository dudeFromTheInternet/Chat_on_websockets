from aiohttp import web
import json
import asyncio
import time


class WSChat:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.conns = {}
        self.last_pong_time = {}

    async def main_page(self, request):
        return web.FileResponse('./index.html')

    async def ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        user_id = None

        async def ping():
            while not ws.closed:
                try:
                    await ws.ping()
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    pass

        ping_task = asyncio.create_task(
            ping())

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    mtype = data.get('mtype')

                    if mtype == 'INIT':
                        user_id = data.get('id')
                        self.conns[user_id] = ws
                        await self.send_system_message('USER_ENTER', user_id)
                        for other_conn in self.conns.values():
                            if other_conn != ws:
                                await other_conn.send_json(
                                    {'mtype': 'USER_ENTER', 'id': user_id})
                    elif mtype == 'TEXT':
                        to_user_id = data.get('to', '')
                        await self.send_message(user_id, to_user_id,
                                                data.get('text'))
                    elif mtype == 'DM':
                        to_user_id = data.get('to', '')
                        await self.send_direct_message(user_id, to_user_id,
                                                       data.get('text'))

                elif msg.type == web.WSMsgType.PING:
                    try:
                        await ws.ping()
                    except asyncio.CancelledError:
                        pass

                elif msg.type == web.WSMsgType.PONG:
                    self.last_pong_time[ws] = time.time()

                elif msg.type == web.WSMsgType.ERROR:
                    print('WebSocket connection closed with exception %s' % ws.exception())

        finally:
            ping_task.cancel()

            if user_id in self.conns:
                del self.conns[user_id]
                await self.send_system_message('USER_LEAVE', user_id)

                for other_conn in self.conns.values():
                    if other_conn != ws:
                        await other_conn.send_json(
                            {'mtype': 'USER_LEAVE', 'id': user_id})

        return ws

    async def send_message(self, from_user_id, to_user_id, text):
        message = {'mtype': 'MSG', 'id': from_user_id, 'text': text}

        if to_user_id and to_user_id in self.conns and to_user_id != from_user_id:
            await self.conns[to_user_id].send_json(message)
        else:
            for conn in self.conns.values():
                if conn != self.conns[from_user_id]:
                    await conn.send_json(message)

    async def send_direct_message(self, from_user_id, to_user_id, text):
        message = {'mtype': 'DM', 'id': from_user_id, 'text': text}

        if to_user_id and to_user_id in self.conns:
            await self.conns[to_user_id].send_json(message)
        elif from_user_id in self.conns:
            await self.conns[from_user_id].send_json(message)

    async def send_system_message(self, mtype, user_id):
        message = {'mtype': mtype, 'id': user_id}
        for conn in self.conns.values():
            await conn.send_json(message)

    def run(self):
        app = web.Application()

        app.router.add_get('/', self.main_page)
        app.router.add_get('/ws', self.ws_handler)

        web.run_app(app, host=self.host, port=self.port)


if __name__ == '__main__':
    WSChat().run()
