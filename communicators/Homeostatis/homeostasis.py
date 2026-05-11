#!/usr/bin/env python3
import sys, subprocess
comm, node, inst_id = sys.argv[1:]
if subprocess.call(['python3', 'health_check.py', comm, node, inst_id]):
    subprocess.call(['python3', 'healing.py', comm, node, inst_id])
    subprocess.call(['python3', 'feedback.py', comm, node, inst_id])
