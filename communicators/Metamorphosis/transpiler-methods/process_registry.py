# Process Registry
"""
python3 process_registry.py

Reads topology.json (the ground-truth node definitions) and produces
process_registry.json.

Each node is copied exactly as it appears in topology.json, with one new field:
    "instances": {
        "1": { "instance_id": 1, "self_address": "uuid...", "pid": null },
        "2": { ... },
        ...
    }

Instance allocation rules:
- population "1" or a numeric string → exactly that many instances
- population "as needed", "auto", or "buffer(...)" → up to 50 instances per node
- Global cap of 1000 total instances across the whole registry (as stated in
  the Process Registry design document).
- Instance IDs are globally unique (1-1000).
- Each instance receives a fresh UUID as its self_address.
- PID is left as null (the runtime will fill it in when the process is started).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def load_topology(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def process_unix_socket_edges(edges):
    """Add uuid_pool to unix_socket edges, shallow copy."""
    edges = [dict(edge) for edge in edges]
    for edge in edges:
        if edge.get('type') == 'unix_socket':
            edge['uuid_pool'] = {str(uuid.uuid4()): {'requested': False, 'working': False} for _ in range(100)}
    return edges

def get_instance_count(population: Any, remaining_capacity: int) -> int:
    """Translate the population field into a concrete instance count."""
    if isinstance(population, int):
        return min(population, remaining_capacity)
    if isinstance(population, str):
        pop_lower = population.strip().lower()
        if pop_lower == "1" or pop_lower.isdigit():
            return min(int(pop_lower), remaining_capacity)
        if any(x in pop_lower for x in ("as needed", "auto", "buffer")):
            # "as needed" nodes may grow; we give them a generous but sane default
            return min(50, remaining_capacity)
    return 1  # safe fallback


def build_registry(topology: Dict[str, Any]) -> Dict[str, Any]:
    registry: Dict[str, Any] = {
        "metadata": {
            "title": "Process Registry – Instance Allocation",
            "generated_from": "topology.json",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "naming_scheme": "Semantic + Role-Based (same as topology.json)",
            "description": (
                "Every node from the communicator topology augmented with "
                "pre-allocated instances. Each instance carries a unique "
                "instance_id (1-1000), a self_address UUID, and a pid placeholder."
            ),
            "max_instances": 1000,
        },
        "communicators": {},
        "total_allocated_instances": 0,
    }

    total_instances = 0
    instance_counter = 1
    max_instances = 1000

    for comm_name, comm_data in topology.get('communicators', {}).items():
        comm_entry = {'short': comm_data.get('short'), 'nodes':{}}
        nodes_data = comm_data.get('nodes', {})
        anchor_node = next((nd for nd in nodes_data.values() if nd.get('type')=='anchor'), None)
        pop = anchor_node.get('population', '1') if anchor_node else '1'
        count = get_instance_count(pop, max_instances)
        total_instances += count * len(nodes_data)
        for role, node in nodes_data.items():
            new_node = node.copy()
            new_node['instances'] = {
                str(i): {'instance_id': i, 'self_address': str(uuid.uuid4()), 'pid': None, 'requested': False, 'working': False}
                for i in range(1, count + 1)
            }
            comm_entry['nodes'][role] = new_node



        # Preserve internal edges (we will add inter-communicator edges in a later stage)
        if "internal_edges" in comm_data:
            comm_entry["internal_edges"] = process_unix_socket_edges(comm_data["internal_edges"])

        registry["communicators"][comm_name] = comm_entry

    registry["total_allocated_instances"] = instance_counter - 1

    # Copy top-level topology metadata that is still useful
    for key in ("inter_communicator_edges", "abstract_edges", "uuid_summary"):
        if key is "inter_communicator_edges":
            registry["inter_communicator_edges"] = process_unix_socket_edges(topology["inter_communicator_edges"])
        elif key in topology:
            registry[key] = topology[key]


    return registry


def main() -> None:
    topology_path = Path("/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/topology.json")
    output_path = Path("/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/process_registry.json")

    topology = load_topology(topology_path)
    registry = build_registry(topology)

    output_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"✅ Successfully wrote {output_path}")
    print(f"   Total instances allocated: {registry['total_allocated_instances']}")
    print("   (Nodes copied verbatim + 'instances' field added)")
    print("\nNext step: add edge wiring / reconciliation logic.")


if __name__ == "__main__":
    main()
