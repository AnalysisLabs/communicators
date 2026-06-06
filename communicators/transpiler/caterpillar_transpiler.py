import os, subprocess, argparse, re, ast, inspect
from collections import Counter
base_dir = os.path.dirname(os.path.abspath("/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/panel.md"))

def activate(with_program):
    threading.Thread(target=subprocess.run, args=(['python3', with_program],), daemon=True).start()

def load(object_program: str = None, with_program: str = None, in_namespace: dict = None, from_namespace: dict = None, to_namespace: dict = None):
    if in_namespace is not None: to_namespace = in_namespace
    if with_program:
        subprocess.run(['python3', with_program, object_program, in_namespace, from_namespace, to_namespace], check=True)
    else:
        with open(object_program, 'r') as f:
            namespace[object_program, to_namespace] = f.read()
    populated = (object_program in to_namespace and namespace[object_program, to_namespace]) or \
                (os.path.exists(object_program) and os.path.getsize(object_program) > 0)
    if not populated:
        raise ValueError(f'{object_program} still empty after load')

def build(object_program: str, with_program: str, in_namespace: dict, from_namespace: dict = None, to_namespace: dict = None):
    if in_namespace is not None: to_namespace = in_namespace
    subprocess.run(['python3', with_program, object_program, in_namespace, from_namespace, to_namespace], check=True)
    populated = False
    if object_program in namespace[object_program, to_namespace] and len([object_program, to_namespace]) > 0:
        populated = True
    elif os.path.exists(object_program) and os.path.getsize(object_program) > 0:
        populated = True
    if not populated:
        raise ValueError(f'{object_program} still empty after running {with_program}')

activate(with_program=f'{base_dir}/namespace.py')
code_block_1 = load(object_program=f'{base_dir}/ideal.yaml', in_namespace=f'{base_dir}/state_namespace')
code_block_2 = build(object_program=f'{base_dir}/mermaid_code.mmd', with_program=f'{base_dir}/generate_mermaid.py', in_namespace=f'{base_dir}/state_namespace')
code_block_3 = build(object_program=f'{base_dir}/topology.json', with_program=f'{base_dir}/generate_topology_json.py', in_namespace=f'{base_dir}/state_namespace')
code_block_4 = build(object_program=f'{base_dir}/process_registry.json', with_program=f'{base_dir}/process_registry.py', from_namespace=f'{base_dir}/state_namespace', to_namespace=f'{base_dir}/ideal_state_namespace')
code_block_5 = load(object_program=f'{base_dir}/codebase', with_program=f'{base_dir}/build_real_nodes.py', from_namespace=f'{base_dir}/ideal_state_namespace', to_namespace=f'{base_dir}/process_registry.json')
