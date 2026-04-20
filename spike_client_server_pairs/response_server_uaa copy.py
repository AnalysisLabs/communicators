# source ~/"Analysis Labs"/"Dev Tools"/Communicators/communicators-venv/bin/activate
# python3 response_server_uaa.py

import asyncio, sys, os, time
sys.path.append('/home/guatamap/Analysis Labs/Dev Tools/Communicators/communicators')
from unix_socket import UnixSocketServerAsync, generate_unique_socket_path
from state import manifest

async def handler(message):
    manifest.info(f'Received: {message}')
    await asyncio.sleep(47)
    response = 'Tiger is well.'
    manifest.info(f'Sending: {response}')
    return response

async def main():
    manifest.info("response_server starting...")
    path_file = '/tmp/shared_socket_path.txt'
    counter = 0.0
    while not os.path.exists(path_file) and counter <= 100.0:
        manifest.info("while not os.path.exists")
        mu = 0.0
        sigma = 2.0
        k = 1.0
        x = round(random.uniform(-k, k), 8)
        y = 2*(norm.cdf(numpy.tan(((numpy.pi / (2 * k)) * x)), loc=mu, scale=sigma) - 0.5)
        noise = y
        counter += 0.3 + noise
        wait_time = (1/12) * math.sqrt(counter**2 + 144)
        await asyncio.sleep(wait_time)
    with open(path_file, 'r') as f:
        socket_path = f.read().strip()
    with open(path_file, 'r') as f:
        socket_path = f.read().strip()
    server = UnixSocketServerAsync(socket_path, handler)
    try:
        await server.start_server()
    except Exception as e:
        manifest.error(f'Server error: {e}')
    manifest.info("...response_server closing")

if __name__ == '__main__':
    asyncio.run(main())
