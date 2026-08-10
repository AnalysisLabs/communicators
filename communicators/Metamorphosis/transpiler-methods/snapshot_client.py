# snapshot_client.py (transient import)
import socket, json

def send_snapshot(path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    data = json.dumps({'snapshot': path}).encode()
    sock.sendto(data, '/tmp/ns_snapshot.sock')
    sock.close()
