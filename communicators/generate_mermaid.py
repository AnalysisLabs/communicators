#!/usr/bin/env python3
"""
generate_mermaid.py

A Python module that takes an ideal.yaml (custom communicator definition format)
and outputs the final pruned Mermaid diagram representing the Communicators Topology
with internal Positive/Negative/WS structure, matching the ground-truth style.

Usage:
    python generate_mermaid.py /path/to/ideal.yaml
    # or import and call generate_mermaid(yaml_path)
"""

import os, sys
from typing import List, Dict, Any, Optional, Union


def parse_ideal_yaml(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse the custom YAML-like format for communicators.
    Handles remote connections specified with host/port indented under Negative/Positive.
    Fixes common typo 'BusinessEnd' -> 'BusinessEdge'.
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()

    comms: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if stripped.startswith('communicator:'):
            name = stripped.split(':', 1)[1].strip()
            comm: Dict[str, Any] = {
                "name": name,
                "location": None,
                "class": None,
                "negative": None,
                "positive": None,
                "population": None
            }
            i += 1
            while i < len(lines):
                next_line = lines[i].rstrip()
                next_stripped = next_line.strip()
                if not next_stripped or next_stripped.startswith('communicator:'):
                    break
                if ':' in next_stripped:
                    key, val = [x.strip() for x in next_stripped.split(':', 1)]
                    if key == 'location':
                        comm['location'] = val
                    elif key == 'class':
                        comm['class'] = val
                    elif key == 'population':
                        comm['population'] = val
                    elif key in ('Negative', 'Positive'):
                        if val and val.lower() != 'none':
                            peer = val
                            if peer == "BusinessEnd":
                                peer = "BusinessEdge"  # fix typo in example
                            is_remote = False
                            host: Optional[str] = None
                            port: Optional[str] = None
                            j = i + 1
                            while j < len(lines):
                                peek = lines[j].rstrip()
                                peek_stripped = peek.strip()
                                if peek_stripped.startswith('host:'):
                                    host = peek_stripped.split(':', 1)[1].strip()
                                    is_remote = True
                                elif peek_stripped.startswith('port:'):
                                    port = peek_stripped.split(':', 1)[1].strip()
                                elif peek_stripped:
                                    break
                                else:
                                    break
                                j += 1
                            if is_remote and host and port:
                                comm[key.lower()] = {"name": peer, "host": host, "port": port}
                            else:
                                comm[key.lower()] = peer
                            i = j - 1
                        else:
                            comm[key.lower()] = None
                i += 1
            comms.append(comm)
        else:
            i += 1
    return comms


def generate_mermaid(yaml_path: str) -> str:
    """
    Generate the final pruned Mermaid diagram from the ideal.yaml.
    Produces the 'Full Ground Truth (with Internal Structure)' pruned version.
    """
    comms = parse_ideal_yaml(yaml_path)

    # Assign short names for clean Mermaid ids (customize as needed for new communicators)
    short_map: Dict[str, str] = {}
    used: set[str] = set()
    names = [c['name'] for c in comms]
    for name in names:
        n = name.upper()
        for length in range(1, len(n) + 1):
            prefix = n[:length]
            if prefix not in used:
                short_map[name] = prefix
                used.add(prefix)
                break
        else:
            # Extremely rare fallback: use full uppercase name
            short_map[name] = n

    lines: List[str] = []
    lines.append("```mermaid")
    lines.append("---")
    lines.append("title: Communicators Topology – Full Ground Truth (with Internal Structure)")
    lines.append("---")
    lines.append("")
    lines.append("flowchart TB")

    # Build each subgraph
    for c in comms:
        name = c['name']
        short = short_map[name]
        class_name = c.get('class', 'Unknown')
        pop = c.get('population', '1')
        neg = c.get('negative')
        pos = c.get('positive')

        has_neg = neg is not None
        has_pos = pos is not None
        has_neg_ws = isinstance(neg, dict)
        has_pos_ws = isinstance(pos, dict)

        neg_pop = "buffer(100)"
        pos_pop = "100"
        neg_ws_pop = "max"
        pos_ws_pop = "1"

        lines.append(f'    subgraph {name}["{name}"]')

        # Main node
        lines.append(f'        {short}["<b>{name}</b><br/>class: {class_name}<br/>population: {pop}"]')

        if has_neg:
            lines.append(f'        {short}_Neg["<b>Negative</b><br/>class: NegativeCom<br/>population: {neg_pop}"]')
            if has_neg_ws:
                lines.append(f'        {short}_NegWS["<b>Negative_WS</b><br/>class: negative_sequence<br/>population: {neg_ws_pop}"]')

        if has_pos:
            lines.append(f'        {short}_Pos["<b>Positive</b><br/>class: PositiveCom<br/>population: {pos_pop}"]')
            if has_pos_ws:
                lines.append(f'        {short}_PosWS["<b>Positive_WS</b><br/>class: positive_sequence<br/>population: {pos_ws_pop}"]')

        # Internal inheritance + unix_socket edges
        if has_neg:
            lines.append(f'        {short} <-->|"inheritence"| {short}_Neg')
            if has_neg_ws:
                lines.append(f'        {short}_Neg <-->|"unix_socket"| {short}_NegWS')
        if has_pos:
            lines.append(f'        {short} <-->|"inheritence"| {short}_Pos')
            if has_pos_ws:
                lines.append(f'        {short}_Pos <-->|"unix_socket"| {short}_PosWS')

        lines.append('    end')
        lines.append('')

    # Vertical layout forcing (top-to-bottom stack of main communicators)
    shorts_list = [short_map[c['name']] for c in comms]
    for ii in range(len(shorts_list) - 1):
        lines.append(f'    {shorts_list[ii]} ~~~ {shorts_list[ii + 1]}')
    lines.append('')

    # Inter-communicator connections (via Negative declarations -> Positive of peer)
    for c in comms:
        neg = c.get('negative')
        if neg is None:
            continue
        a_name = c['name']
        a_short = short_map[a_name]
        if isinstance(neg, dict):
            b_name = neg['name']
            label = f"{neg['host']}:{neg['port']}<br/>ws_socket"
            is_remote = True
        else:
            b_name = neg
            label = "unix_socket"
            is_remote = False

        b_short = short_map.get(b_name, b_name[:3].upper())
        left = f"{a_short}_Neg" + ("WS" if is_remote else "")
        # Check if peer's Positive side has WS (remote)
        b_comm = next((x for x in comms if x['name'] == b_name), None)
        b_pos = b_comm.get('positive') if b_comm else None
        b_has_pos_ws = isinstance(b_pos, dict)
        right = f"{b_short}_Pos" + ("WS" if b_has_pos_ws else "")
        lines.append(f'    {left} <-->|"{label}"| {right}')

    lines.append('')
    # Styling (matches the ground-truth example)
    lines.append('    %% Optional styling')
    lines.append('    classDef main fill:#e8f4fd,stroke:#1a5276,stroke-width:4px,rx:14,ry:14;')
    subgraph_names = ",".join(c['name'] for c in comms)
    lines.append(f'    class {subgraph_names} main')
    lines.append('```')

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        # print("Usage: python3 generate_mermaid.py "/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/ideal.yaml"", file=sys.stderr)
        sys.exit(1)
    yaml_path = sys.argv[1]
    mermaid_code = generate_mermaid(yaml_path)
    out_path = os.path.join(os.path.dirname(yaml_path), 'mermaid_code.mmd')
    print(out_path)
    with open(out_path, 'w') as f:
        f.write(mermaid_code)


if __name__ == "__main__":
    main()
