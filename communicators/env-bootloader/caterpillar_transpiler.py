base_dir = f'{COMMUNICATORS_ROOT}/state-methods'


def load(object_program: str = None, with_program: str = None, in_namespace: dict = None, from_namespace: dict = None, to_namespace: dict = None):
    if os.path.exists(str(object_program)):
        contents = open(object_program).read()
    else:
        contents = object_program
    if with_program:
        contents = subprocess.run(['python3', with_program, object_program], capture_output=True, text=True).stdout
    r = transponder.request_response(localhost, 8765, {(in_namespace or to_namespace): contents})
    # wait for simple 200 response as green light (detailed pseudocode placeholder)
    return

def build(object_program: str, with_program: str, in_namespace: dict, from_namespace: dict = None, to_namespace: dict = None):
    contents = transponder.request_response(localhost, 8765, (in_namespace or from_namespace))
    result = subprocess.run(['python3', with_program, object_program], capture_output=True, text=True).stdout
    transponder.send_and_close(localhost, 8765, {(in_namespace or to_namespace): result})

code_block_1 = load(object_program=f'{base_dir}/ideal.yaml', in_namespace=f'{base_dir}/state_namespace')
code_block_2 = build(object_program=f'{base_dir}/mermaid_code.mmd', with_program=f'{base_dir}/generate_mermaid.py', in_namespace=f'{base_dir}/state_namespace')
code_block_3 = build(object_program=f'{base_dir}/topology.json', with_program=f'{base_dir}/generate_topology_json.py', in_namespace=f'{base_dir}/state_namespace')
code_block_4 = build(object_program=f'{base_dir}/process_registry.json', with_program=f'{base_dir}/process_registry.py', from_namespace=f'{base_dir}/state_namespace', to_namespace=f'{base_dir}/ideal_state_namespace')
code_block_5 = load(object_program=f'{base_dir}/codebase', with_program=f'{base_dir}/build_real_nodes.py', from_namespace=f'{base_dir}/ideal_state_namespace', to_namespace=f'{base_dir}/process_registry.json')