
from prelude.standard import*
from prelude.internal_lib import*

landscape(config)
generate_mermaid()
generate_topology_json()
registry = ProcessRegistry()
loops = [HomeostasisLoop(node, IdealState, registry, ManifestLogger(node.id)) for node in ir.nodes] + [HomeostasisLoop(edge, IdealState, registry, ManifestLogger(edge.id)) for edge in ir.edges]
