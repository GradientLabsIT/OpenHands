import asyncio
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('bridge.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class BridgeTest(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_connections_and_half_closed_requests(self):
        async def echo(reader, writer):
            data = await reader.read()
            writer.write(data)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        backend = await asyncio.start_server(echo, '127.0.0.1', 0, backlog=1024)
        class Resolver:
            async def get(self, failed_port=None):
                return backend.sockets[0].getsockname()[1]
        proxy = await asyncio.start_server(lambda r, w: bridge.relay(r, w, Resolver()), '127.0.0.1', 0, backlog=1024)
        capacity = asyncio.Semaphore(80)
        async def client(index):
            async with capacity:
                await exchange(index)
        async def exchange(index):
            reader, writer = await asyncio.open_connection('127.0.0.1', proxy.sockets[0].getsockname()[1])
            data = (str(index) + ':').encode() + b'x' * 65536
            writer.write(data)
            await writer.drain()
            writer.write_eof()
            self.assertEqual(await asyncio.wait_for(reader.read(), 10), data)
            writer.close()
            await writer.wait_closed()
        try:
            await asyncio.gather(*(client(i) for i in range(160)))
        finally:
            proxy.close()
            backend.close()
            await proxy.wait_closed()
            await backend.wait_closed()

    async def test_server_push_keeps_quiet_client_alive(self):
        async def push(reader, writer):
            for _ in range(10):
                writer.write(b'x')
                await writer.drain()
                await asyncio.sleep(0.025)
            writer.close()
            await writer.wait_closed()
        backend = await asyncio.start_server(push, '127.0.0.1', 0)
        class Resolver:
            async def get(self, failed_port=None):
                return backend.sockets[0].getsockname()[1]
        proxy = await asyncio.start_server(lambda r, w: bridge.relay(r, w, Resolver(), idle_timeout=0.1), '127.0.0.1', 0)
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', proxy.sockets[0].getsockname()[1])
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b'x' * 10)
            writer.close()
            await writer.wait_closed()
        finally:
            proxy.close()
            backend.close()
            await proxy.wait_closed()
            await backend.wait_closed()

    async def test_port_refresh_coalesces_and_failures_are_cached(self):
        class Resolver(bridge.PortResolver):
            calls = 0
            fail = False
            async def discover(self):
                self.calls += 1
                await asyncio.sleep(0.01)
                if self.fail:
                    raise ConnectionError('Unavailable')
                return 12345 + self.calls
        resolver = Resolver()
        old = await resolver.get()
        resolver.retry_after = 0
        ports = await asyncio.gather(*(resolver.get(failed_port=old) for _ in range(80)))
        self.assertEqual(resolver.calls, 2)
        self.assertEqual(set(ports), {old + 1})
        resolver.fail = True
        resolver.expires = 0
        results = await asyncio.gather(*(resolver.get() for _ in range(80)), return_exceptions=True)
        self.assertEqual(resolver.calls, 3)
        self.assertTrue(all(isinstance(result, ConnectionError) for result in results))

if __name__ == '__main__':
    unittest.main()
