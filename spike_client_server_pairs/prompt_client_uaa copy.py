# source ~/"Analysis Labs"/"Dev Tools"/Communicators/communicators-venv/bin/activate
# python3 prompt_client_uaa.py

import tracemalloc, threading, asyncio, sys, os, websockets, math, random, numpy
from scipy.stats import norm
sys.path.append('/home/guatamap/Analysis Labs/Dev Tools/Communicators/communicators')
from unix_socket import UnixSocketClientAsync, generate_unique_socket_path
from state import manifest

async def main():
    manifest.info("prompt_client starting...")
    socket_path = generate_unique_socket_path()
    path_file = '/tmp/shared_socket_path.txt'
    with open(path_file, 'w') as f:
        f.write(socket_path)
    with open(path_file, 'r') as g: socket_path2 = g.read().strip()
    manifest.info("socket value: ", socket_path2)
    client = await UnixSocketClientAsync(socket_path)
    counter = 0.0
    while counter <= 100.0:
        try:
            await client.connect()
        except Exception as e:
            manifest.error(f'Connection failed: {e}')
            mu = 0.0
            sigma = 2.0
            k = 1.0
            x = round(random.uniform(-k, k), 8)
            y = 2*(norm.cdf(numpy.tan(((numpy.pi / (2 * k)) * x)), loc=mu, scale=sigma) - 0.5)
            noise = y
            counter += 0.3 + noise
            wait_time = (1/12) * math.sqrt(counter**2 + 144)
            await asyncio.sleep(wait_time)
    manifest.info('Sending: How is tiger?')
    await client.send_message('How is tiger?')
    response = await client.receive_message()
    manifest.info(f'Received: {response}')
    manifest.info("...prompt_client closing")

if __name__ == '__main__':
    asyncio.run(main())
