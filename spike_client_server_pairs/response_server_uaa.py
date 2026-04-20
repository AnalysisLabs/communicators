# source ~/"Analysis Labs"/"Dev Tools"/Communicators/communicators-venv/bin/activate
# python3 response_server_uaa.py

import asyncio, sys, os, time
sys.path.append('/home/guatamap/Analysis Labs/Dev Tools/Communicators/communicators')
from unix_socket import UnixSocketServerAsync, generate_unique_socket_path, unix_server
from state import manifest, singleton

@unix_server
@singleton
class ResponseServer:
    def __init__(self):
        self.config = {
            "positive_path": {"9b8eb862-b700-4bfb-8855-a560b41fa0b3"}
            }

    async def handler(self, message):
        manifest.info(f'Received: {message}')
        await asyncio.sleep(47)
        response = 'Tiger is well.'
        manifest.info(f'Sending: {response}')
        return response

    async def run(self):
        manifest.info('response_server starting...')
        server = UnixSocketServerAsync(self.handler)
        await server.start_server()
        manifest.info('...response_server closing')

if __name__ == '__main__':
    asyncio.run(ResponseServer().run())
