import asyncio
import json
import logging
import os
import socket
import time

class PortResolver:
    def __init__(self):
        self.port = None
        self.expires = 0
        self.retry_after = 0
        self.failed = False
        self.lock = asyncio.Lock()

    async def discover(self):
        env = dict(os.environ, PATH='/opt/openhands:' + os.environ['PATH'])
        process = await asyncio.create_subprocess_exec(
            '/opt/openhands/dcx', 'ports', '--json', cwd='/opt/openhands',
            env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 10)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise ConnectionError('Docker port discovery failed')
        port = int(json.loads(output)['canvas']['8000'])
        if not 0 < port < 65536:
            raise ValueError('Invalid Docker port')
        return port

    async def get(self, failed_port=None):
        async with self.lock:
            now = time.monotonic()
            if self.failed and now < self.retry_after:
                raise ConnectionError('Docker port discovery cooling down')
            if self.port is None or now >= self.expires or (failed_port == self.port and now >= self.retry_after):
                self.retry_after = now + 2
                try:
                    self.port = await self.discover()
                except (OSError, TimeoutError, ValueError, KeyError):
                    self.failed = True
                    raise
                self.failed = False
                self.expires = time.monotonic() + 60
            return self.port

async def copy_stream(reader, writer, activity):
    while data := await reader.read(65536):
        activity[0] = time.monotonic()
        writer.write(data)
        await asyncio.wait_for(writer.drain(), 30)
    if writer.can_write_eof():
        writer.write_eof()
        await asyncio.wait_for(writer.drain(), 30)

async def watch_activity(activity, timeout):
    while True:
        remaining = timeout - (time.monotonic() - activity[0])
        if remaining <= 0:
            raise TimeoutError('Idle connection')
        await asyncio.sleep(min(remaining, 30))

async def relay(reader, writer, resolver, idle_timeout=600):
    upstream = None
    tasks = []
    try:
        port = await resolver.get()
        try:
            other_reader, upstream = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port), 5)
        except (OSError, TimeoutError):
            port = await resolver.get(failed_port=port)
            other_reader, upstream = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port), 5)
        for connection in [writer, upstream]:
            connection.get_extra_info('socket').setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        activity = [time.monotonic()]
        transfer = asyncio.gather(copy_stream(reader, upstream, activity), copy_stream(other_reader, writer, activity))
        watcher = asyncio.create_task(watch_activity(activity, idle_timeout))
        tasks = [transfer, watcher]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except (OSError, TimeoutError, ValueError, KeyError) as error:
        logging.warning('OpenHands proxy connection failed: %s', type(error).__name__)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for connection in [writer, upstream]:
            if connection is not None:
                connection.close()
                try:
                    await asyncio.wait_for(connection.wait_closed(), 2)
                except (OSError, TimeoutError):
                    connection.transport.abort()

async def main():
    resolver = PortResolver()
    capacity = asyncio.Semaphore(1024)
    async def handle(reader, writer):
        if capacity.locked():
            writer.transport.abort()
            return
        async with capacity:
            await relay(reader, writer, resolver)
    server = await asyncio.start_server(handle, '127.0.0.1', 18080, limit=65536, backlog=1024)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
