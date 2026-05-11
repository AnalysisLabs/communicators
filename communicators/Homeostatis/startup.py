#!/home/guatamap/'Analysis Labs'/chat-venv/bin/python3

"""
startup.py: Called by reconcile() as startup.py <venv> <script> <comm> <node> <inst_id>
Daemon-starts node, sets pid/requested/working in process_registry.json atomically.
"""
import sys
import os
import json
import subprocess

if len(sys.argv) != 6:
    sys.stderr.write('Usage: startup.py <venv> <script> <comm> <node> <inst_id>\n')
    sys.exit(1)

venv_path, script_path, comm, node, inst_id_str = sys.argv[1:]
inst_id = str(int(inst_id_str))
REG_PATH = '/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/process_registry.json'

# Load & validate
with open(REG_PATH, 'r') as f:
    registry = json.load(f)
try:
    inst = registry['communicators'][comm]['nodes'][node]['instances'][inst_id]
except KeyError:
    sys.exit(f'Instance {comm}/{node}/{inst_id} not found')
if inst['pid'] is not None:
    sys.exit(f'Instance already PID {inst["pid"]}')

# Daemonize
python_exe = os.path.join(os.path.normpath(venv_path), 'bin', 'python')
cmd = [python_exe, script_path]
proc = subprocess.Popen(cmd, start_new_session=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)

# Update
inst['pid'] = proc.pid
inst['requested'] = True
inst['working'] = True

# Atomic write
tmp_path = REG_PATH + '.tmp'
with open(tmp_path, 'w') as f:
    json.dump(registry, f, indent=2)
os.replace(tmp_path, REG_PATH)

print(f'{inst_id} PID: {proc.pid}')
