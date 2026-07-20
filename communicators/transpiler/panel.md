1. load ideal.yaml in state_namespace
2. build mermaid_code.mmd with generate_mermaid.py in state_namespace
3. build topology.json with generate_topology_json.py in state_namespace
4. build process_registry.json with process_registry.py from state_namespace to ideal_state_namespace
5. load codebase to process_registry.json with build_real_nodes.py in ideal_state_namespace