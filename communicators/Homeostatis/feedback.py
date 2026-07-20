#!/usr/bin/env python3
import sys, json, socket

REG_PATH = '/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/process_registry.json'
comm, node, inst_id = sys.argv[1:]
with open(REG_PATH) as f:
    inst = json.load(f)['communicators'][comm]['nodes'][node]['instances'][inst_id]
try:
    with socket.socket(socket.AF_UNIX) as s:
        s.connect(inst['self_address'])
        s.send(b'informant')
        if s.recv(1024).decode().strip() != 'OK': raise OSError
except OSError:
    print(f'instance {inst["self_address"]} is dead and unrecoverable')
