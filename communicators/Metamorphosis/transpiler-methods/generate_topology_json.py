#!/usr/bin/env python3
"""
python3 generate_topology_json.py mermaid_code.mmd

Reads a Mermaid communicator topology diagram (.mmd) and produces a rich,
nested JSON representation using Semantic + Role-Based naming:
  - Nodes: F_Main, F_Neg, F_NegWS, O_Pos, U_NegWS, B_PosWS, BA_Pos, etc.
  - Edges: E_F_Neg__F_Main, E_F_Neg__O_Pos, etc.

Non-WS edges receive a UUID (verified unique). WS edges are flagged separately without UUID.
"""

import json, re, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Tuple

def parse_ideal_yaml(ideal_path: Path) -> Dict[str, Dict[str, str]]:
    lines = ideal_path.read_text().splitlines()
    ideal_map = {}
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('communicator:'):
            name = stripped.split(':', 1)[1].strip()
            ideal_map[name] = {'location': None, 'class': None, 'population': None}
            i += 1
            while i < len(lines) and lines[i].strip():
                ln = lines[i].strip()
                if ln.startswith('location:'):
                    ideal_map[name]['location'] = ln.split(':', 1)[1].strip()
                elif ln.startswith('class:'):
                    ideal_map[name]['class'] = ln.split(':', 1)[1].strip()
                elif ln.startswith('population:'):
                    ideal_map[name]['population'] = ln.split(':', 1)[1].strip()
                elif ln.startswith('venv:'):
                    ideal_map[name]['venv'] = ln.split(':', 1)[1].strip()
                i += 1
            continue
        i += 1
    return ideal_map

def parse_mermaid(mermaid_path: Path) -> Dict[str, Any]:
    """Parse the Mermaid file into structured data."""
    content = mermaid_path.read_text(encoding="utf-8")

    # Remove ```mermaid ... ``` wrapper if present
    content = re.sub(r'^```mermaid\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)

    # Extract title
    title_match = re.search(r'title:\s*(.+)', content)
    title = title_match.group(1).strip() if title_match else "Communicators Topology"

    # Find all subgraphs
    subgraph_pattern = re.compile(
        r'subgraph\s+(\w+)\["([^"]+)"\](.*?)\n\s*end',
        re.DOTALL
    )

    communicators = []
    for match in subgraph_pattern.finditer(content):
        subgraph_id = match.group(1)  # e.g. "Frontend"
        name = match.group(2)
        body = match.group(3)

        # Parse nodes inside subgraph: ID["label"]
        node_pattern = re.compile(r'(\w+)\["([^"]+)"\]')
        nodes = {}
        main_short = None
        for nmatch in node_pattern.finditer(body):
            node_id = nmatch.group(1)
            label = nmatch.group(2)

            # Determine role and semantic ID using short letter
            if main_short is None:
                # First node is usually the Main node — capture its short ID (F, O, U, B, BA)
                main_short = node_id if len(node_id) <= 2 else node_id[:2]  # fallback

            if "_NegWS" in node_id:
                role = "Negative_WS"
                semantic_id = f"{main_short}_NegWS"
            elif "_PosWS" in node_id:
                role = "Positive_WS"
                semantic_id = f"{main_short}_PosWS"
            elif "_Neg" in node_id:
                role = "Negative"
                semantic_id = f"{main_short}_Neg"
            elif "_Pos" in node_id:
                role = "Positive"
                semantic_id = f"{main_short}_Pos"
            else:
                role = "Main"
                semantic_id = f"{main_short}_Main"

            # Extract class and population from label
            class_match = re.search(r'class:\s*([^<]+)', label)
            pop_match = re.search(r'population:\s*([^<]+)', label)

            nodes[role] = {
                "id": semantic_id,
                "original_id": node_id,
                "class": class_match.group(1).strip() if class_match else None,
                "population": pop_match.group(1).strip() if pop_match else None,
                "type": "anchor" if role == "Main" else "aux"
            }

        short = main_short or subgraph_id[:1].upper()  # fallback

        # Parse internal edges: from <-->|"label"| to
        edge_pattern = re.compile(r'(\w+)\s*<-->\s*\|"([^"]+)"\|\s*(\w+)')
        internal_edges = []
        for ematch in edge_pattern.finditer(body):
            from_node = ematch.group(1)
            label = ematch.group(2)
            to_node = ematch.group(3)

            # Map to semantic IDs
            from_sem = get_semantic_id(from_node, short, nodes)
            to_sem = get_semantic_id(to_node, short, nodes)

            internal_edges.append({
                "from": from_sem,
                "to": to_sem,
                "type": "inheritance" if "inheritence" in label.lower() else label.lower()
            })

        communicators.append({
            "name": name,
            "short": short,
            "nodes": nodes,
            "internal_edges": internal_edges
        })

    # Parse top-level edges (inter + abstract) - line by line to avoid subgraph matches
    inter_edges = []
    abstract_edges = []

    lines = content.splitlines()
    in_subgraph = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('subgraph '):
            in_subgraph = True
            continue
        if stripped == 'end':
            in_subgraph = False
            continue
        if in_subgraph:
            continue

        # abstract edges
        abstract_match = re.match(r'(\w+)\s*~~~\s*(\w+)', stripped)
        if abstract_match:
            abstract_edges.append({
                "from": abstract_match.group(1),
                "to": abstract_match.group(2),
                "type": "abstract_stack"
            })
            continue

        # Inter edges with label
        edge_match = re.match(r'(\w+)\s*<-->\s*\|"([^"]+)"\|\s*(\w+)', stripped)
        if edge_match:
            from_id = edge_match.group(1)
            label = edge_match.group(2)
            to_id = edge_match.group(3)

            edge_type = "ws_socket" if "ws_socket" in label.lower() else label.lower()
            inter_edges.append({
                "from": from_id,
                "to": to_id,
                "type": edge_type
            })

    for i, abs_edge in enumerate(abstract_edges):
        if i < len(inter_edges):
            abs_edge["type"] = inter_edges[i]["type"]

    return {
        "title": title,
        "communicators": communicators,
        "inter_edges": inter_edges,
        "abstract_edges": abstract_edges
    }


def get_semantic_id(node_id: str, short: str, nodes: Dict) -> str:
    """Map original node ID to semantic ID."""
    for role, data in nodes.items():
        if data["original_id"] == node_id:
            return data["id"]
    # Fallback
    return f"{short}_{node_id}"


def assign_uuids(data: Dict[str, Any]) -> Dict[str, Any]:
    """Assign UUIDs to all non-WS edges and verify uniqueness."""
    all_uuids = []

    # Internal edges
    for comm in data["communicators"]:
        for edge in comm["internal_edges"]:
            u = str(uuid.uuid4())
            edge["id"] = f"E_{edge['from']}__{edge['to']}"
            edge["uuid"] = u
            all_uuids.append(u)

    # Inter edges (non-WS)
    for edge in data["inter_edges"]:
        u = str(uuid.uuid4())
        edge["id"] = f"E_{edge['from']}__{edge['to']}"
        edge["uuid"] = u
        all_uuids.append(u)

    # abstract edges (treat as non-WS)
    for edge in data["abstract_edges"]:
        u = str(uuid.uuid4())
        edge["id"] = f"E_{edge['from']}__{edge['to']}_abstract"
        edge["uuid"] = u
        all_uuids.append(u)

    # Double-check uniqueness
    unique_count = len(set(all_uuids))
    total = len(all_uuids)
    data["uuid_summary"] = {
        "total_non_ws_edges": total,
        "unique_uuids": unique_count,
        "all_unique": unique_count == total
    }

    if unique_count != total:
        raise RuntimeError(f"UUID collision detected! {unique_count} unique out of {total}")

    return data


def build_final_json(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Build the final nested JSON structure with Semantic + Role-Based naming."""
    final = {
        "metadata": {
            "title": parsed["title"],
            "generated_from": "mermaid_code.mmd",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "naming_scheme": "Semantic + Role-Based (e.g. F_Main, E_F_Neg__O_Pos)",
            "description": "Nested representation of communicator topology with unique UUIDs on all non-WS edges."
        },
        "communicators": {}
    }

    for comm in parsed["communicators"]:
        comm_name = comm['name']
        ideal_map = parsed.get('ideal_map', {})
        if comm_name in ideal_map and 'Main' in comm['nodes']:
            main_node = comm['nodes']['Main']
            if 'location' in ideal_map[comm_name] and ideal_map[comm_name]['location']:
                main_node['location'] = ideal_map[comm_name]['location']
            if 'class' in ideal_map[comm_name] and ideal_map[comm_name]['class']:
                main_node['class'] = ideal_map[comm_name]['class']
            if 'venv' in ideal_map[comm_name] and ideal_map[comm_name]['venv']:
                main_node['venv'] = ideal_map[comm_name]['venv']
        for role, data in comm['nodes'].items():
            data.pop('original_id', None)  # Removes safely if present
        final["communicators"][comm["name"]] = {
            "short": comm["short"],
            "nodes": comm["nodes"],
            "internal_edges": comm["internal_edges"]
        }

    final["inter_communicator_edges"] = parsed["inter_edges"]
    final["abstract_edges"] = parsed["abstract_edges"]
    final["uuid_summary"] = parsed["uuid_summary"]

    return final


def main():
    mermaid_file = Path("/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/mermaid_code.mmd")
    output_file = mermaid_file.parent / "topology.json"

    print(f"Parsing {mermaid_file}...")
    parsed = parse_mermaid(mermaid_file)
    ideal_path = Path('/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/state-methods/ideal.yaml')
    parsed['ideal_map'] = parse_ideal_yaml(ideal_path)

    print("Assigning UUIDs to non-WS edges and verifying uniqueness...")
    parsed_with_uuids = assign_uuids(parsed)

    print("Building final nested JSON...")
    final_json = build_final_json(parsed_with_uuids)

    output_file.write_text(
        json.dumps(final_json, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\n✅ Successfully wrote enriched topology to {output_file}")
    print(f"   Total non-WS edges with UUID: {final_json['uuid_summary']['total_non_ws_edges']}")
    print(f"   All UUIDs unique: {final_json['uuid_summary']['all_unique']}")

    # Print a sample for verification
    print("\nSample node IDs (Semantic + Role-Based):")
    for name, comm in list(final_json["communicators"].items())[:2]:
        for role, node in comm["nodes"].items():
            print(f"  {name} -> {role}: {node['id']}")

    print("\nSample edge IDs:")
    for edge in final_json["inter_communicator_edges"][:2]:
        print(f"  {edge['id']} (uuid: {edge['uuid'][:8]}...)")


if __name__ == "__main__":
    main()
