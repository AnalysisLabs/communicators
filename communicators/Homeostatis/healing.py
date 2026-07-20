#!/usr/bin/env python3
import sys, json, os, subprocess

REG_PATH = '/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/process_registry.json'

def atomic_load():
    with open(REG_PATH) as f: return json.load(f)

def atomic_save(reg):
    tmp = REG_PATH + '.tmp'
    with open(tmp, 'w') as f: json.dump(reg, f, indent=2)
    os.replace(tmp, REG_PATH)

comm, node, inst_id = sys.argv[1:]
reg = atomic_load()
node_info = reg['communicators'][comm]['nodes'][node]
inst = node_info['instances'][inst_id]
inst['pid'] = None
inst['working'] = False
atomic_save(reg)
python_exe = os.path.join(node_info['venv'], 'bin/python')
subprocess.Popen([python_exe, 'startup.py', node_info['venv'], node_info['location'], comm, node, inst_id])
