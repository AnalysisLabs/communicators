#!/usr/bin/env python3
import sys, json, socket, os

REG_PATH = '/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/process_registry.json'

def atomic_load():
    with open(REG_PATH) as f: return json.load(f)

def check_informant(uuid):
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(uuid)
            s.send(b'informant')
            return s.recv(1024).decode().strip() == 'OK'
    except: return False

comm, node, inst_id = sys.argv[1:]
reg = atomic_load()
inst = reg['communicators'][comm]['nodes'][node]['instances'][inst_id]
sys.exit(0 if check_informant(inst['self_address']) else 1)
