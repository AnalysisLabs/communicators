# source ~/"Analysis Labs"/"Dev Tools"/Communicators/communicators-venv/bin/activate
# python3 prompt_client_uaa.py

import tracemalloc, threading, asyncio, sys, os, websockets, math, random, numpy
from scipy.stats import norm
sys.path.append('/home/guatamap/Analysis Labs/Dev Tools/Communicators/communicators')
from unix_socket import UnixSocketClientAsync, generate_unique_socket_path, unix_client
from state import manifest, singleton

@unix_client
@singleton
class PromptClient:
    def __init__(self):
        self.config = {
            "negative_path": {"9b8eb862-b700-4bfb-8855-a560b41fa0b3"},
            }
        manifest.info(f'Config set in PromptClient: {self.config}')

    async def run(self):
        manifest.info('prompt_client starting...')
        client = await UnixSocketClientAsync()
        manifest.info('Sending: How is tiger?')
        await client.send_message('How is tiger?')
        response = await client.receive_message()
        manifest.info(f'Received: {response}')
        manifest.info('...prompt_client closing')

if __name__ == '__main__':
    asyncio.run(PromptClient().run())
