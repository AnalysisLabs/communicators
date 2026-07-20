
from prelude.standard import*
from prelude.internal_lib import*

landscape(config)
generate_mermaid()
generate_topology_json()
registry = ProcessRegistry()
loops = [HomeostasisLoop(node, IdealState, registry) for node in ir.nodes] + [HomeostasisLoop(edge, IdealState, registry) for edge in ir.edges]
