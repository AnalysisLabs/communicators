base_dir = PathReffs.resolve_path(
    '6436be95-3579-4b62-9c06-49de2dd6c595',
    'Metamorphosis',
    'transpiler-methods',
)

def load(db_ref, file_ref=None, blob=None):
    if file_ref is not None:
        return request(db_ref, file_ref=file_ref)
    if blob is not None:
        return request(db_ref, blob=blob)
    raise TypeError("load requires file_ref or blob")

def build(spec_ref, transformer_ref, dest_ref):
    spec = request(spec_ref)
    blob = execution_harness(
        src=transformer_ref,
        dst="Metamorphosis/generated/build_transformer.py",
        prefix=prefix,
        wait=True,
        launch=True,
        spec=spec_ref,
    )
    return request(dest_ref, blob=blob)

code_block_1 = load(db_ref='Metamorphosis/DB/state_namespace/ideal.yaml', file_ref=PathReffs.FileRef(uuid='5d5c6a36-415d-418b-8cb3-7b2ac303b5c6', file_path='Metamorphosis/transpiler-methods', file_name='ideal.yaml'))
code_block_2 = load(db_ref='Metamorphosis/DB/state_namespace/mermaid_code.mmd', file_ref=PathReffs.FileRef(uuid='ab7be9de-2d1b-41ff-adf3-2f1a87cef893', file_path='Metamorphosis/transpiler-methods', file_name='mermaid_code.mmd'))
code_block_3 = load(db_ref='Metamorphosis/DB/state_namespace/generate_mermaid.py', file_ref=PathReffs.FileRef(uuid='a058fa08-9ec0-4e9e-b6df-8b6b7bffdbb3', file_path='Metamorphosis/transpiler-methods', file_name='generate_mermaid.py'))
code_block_4 = load(db_ref='Metamorphosis/DB/state_namespace/topology.json', file_ref=PathReffs.FileRef(uuid='872dad6b-bb8a-4959-9842-c39cc32c6bd1', file_path='Metamorphosis/transpiler-methods', file_name='topology.json'))
code_block_5 = load(db_ref='Metamorphosis/DB/state_namespace/generate_topology_json.py', file_ref=PathReffs.FileRef(uuid='cfe9990f-c6b7-4990-8d21-1035a91e88d8', file_path='Metamorphosis/transpiler-methods', file_name='generate_topology_json.py'))
code_block_6 = load(db_ref='Metamorphosis/DB/state_namespace/process_registry.json', file_ref=PathReffs.FileRef(uuid='9c28ad51-a05b-4633-8bf9-63f637d574ef', file_path='Metamorphosis/transpiler-methods', file_name='process_registry.json'))
code_block_7 = load(db_ref='Metamorphosis/DB/state_namespace/process_registry.py', file_ref=PathReffs.FileRef(uuid='2bf7de4f-e699-4ac5-a498-b18db1673640', file_path='Metamorphosis/transpiler-methods', file_name='process_registry.py'))
code_block_8 = load(db_ref='Metamorphosis/DB/state_namespace/build_real_nodes.py', file_ref=PathReffs.FileRef(uuid='c4e8a1d0-7b3f-4f2a-9e16-2d5b8c0a14e7', file_path='Metamorphosis/transpiler-methods', file_name='build_real_nodes.py'))
code_block_9 = build(spec_ref='Metamorphosis/DB/state_namespace/build_real_nodes.py', transformer_ref='Metamorphosis/DB/state_namespace/generate_mermaid.py', dest_ref='Metamorphosis/DB/state_namespace/mermaid_code.mmd')
code_block_10 = build(spec_ref='Metamorphosis/DB/state_namespace/mermaid_code.mmd', transformer_ref='Metamorphosis/DB/state_namespace/generate_topology_json.py', dest_ref='Metamorphosis/DB/state_namespace/topology.json')
code_block_11 = build(spec_ref='Metamorphosis/DB/state_namespace/topology.json', transformer_ref='Metamorphosis/DB/state_namespace/process_registry.py', dest_ref='Metamorphosis/DB/state_namespace/process_registry.json')
