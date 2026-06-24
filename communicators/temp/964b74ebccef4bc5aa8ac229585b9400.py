import sys, os
from pathlib import Path
COMMUNICATORS_ROOT = "/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators"
sys.path.insert(0, COMMUNICATORS_ROOT)
from prelude import*


# ==================== USER PROGRAM ====================
# Terms:

def is_complete(response):
    """Simple delimiter check for the current placeholder protocol."""
    if isinstance(response, dict): response = json.dumps(response).encode()
    return response.endswith(b'\n') or b'ACK' in response

666
# Utils:

def create_listener(ip, port):
    l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    l.bind((ip, port))
    l.listen(5)
    return l

def accept_connection(listener):
    """
    Accepts an incoming connection on the listening endpoint.
    Returns the new connected endpoint (socket object) that can be used
    for send/recv with the remote side.
    """
    conn, addr = listener.accept()
    return conn

def connect_to(host, port):
    """
    Actively connects to a remote listening endpoint (host, port).
    Returns the connected endpoint that can be used for send/recv.
    """
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.connect((host, port))
    return conn

def sendall(conn, data):
    """
    Send all bytes on the given connected endpoint.
    Blocks until all data is sent or an error occurs.
    """
    conn.sendall(data)

def recv(conn, size):
    """
    Receive up to `size` bytes from the given connected endpoint.
    Returns the bytes received (may be fewer than `size`).
    """
    return conn.recv(size)

def handle_connection(conn):
    """
    Minimal proof-of-concept handler.
    Receives data, prints it, and optionally echoes back a simple ACK.
    Good enough to validate that connections are working and bidirectional.
    """
    Manifest.info("New connection established")

    try:
        while True:
            data = recv(conn, 4096)
            if not data:
                Manifest.error("Connection closed by remote side")
                break

            Manifest.info(f"Received: {data}")

            # Simple response to prove bidirectional flow
            # You can change this to whatever you want for testing
            response = b"ACK\n"
            sendall(conn, response)

    except Exception as e:
        Manifest.error(f"Connection error: {e}")

# High level:

def persistent_server(host, port):
    if host == 'localhost': host = '127.0.0.1'
    listener = create_listener(host, port)
    Manifest.info("Transponder active")

    while True:
        conn = accept_connection(listener)
        # Hand off or handle directly
        handle_connection(conn)

def send_and_close(host, port, data):
    if host == 'localhost': host = '127.0.0.1'
    conn = connect_to(host, port)
    conn.sendall(data)           # fire-and-forget style
    conn.close()

def request_response(host, port, data):
    if host == 'localhost': host = '127.0.0.1'
    conn = connect_to(host, port)
    conn.sendall(data)

    response = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        response += chunk
        if is_complete(response):   # your simple check
            break

    conn.close()
    return response

"""
# We do not need this yet. It is important not is not needed for getting the namespace server working.
def persistent_client(host="127.0.0.1", port=12345):
    if host == 'localhost': host = '127.0.0.1'
    conn = connect_to(host, port)

    while True:
        # send when needed
        data = get_next_message()
        if data:
            conn.sendall(data)

        # receive when available
        response = conn.recv(4096)
        if response:
            handle_connection(response)
"""
