Four programs, no execution nodes. Harness helpers show up only as edge labels between these files.

```mermaid
flowchart TD
  mboot["metamorphosis_bootloader.py"]
  mdb["metamorphosis_db.py"]
  writer["metamorphosis_writer.py"]
  structs["metamorphosis_structures.py"]

  %% boot path
  mboot -->|"load_module()"| mdb
  mboot -->|"from_code_import init_metamorphosis_db"| mdb
  mboot -->|"init_metamorphosis_db()"| mdb

  mdb -->|"load_module()"| structs
  mdb -->|"from_code_import create_core_structures"| structs
  mdb -->|"create_core_structures(conn)"| structs

  writer -->|"load_module()"| structs
  writer -->|"from_code_import create_*"| structs
  writer -->|"create_core_structures / create_vfs_tables / …"| structs

  %% writer __main__ only
  writer -.->|"load_module()"| mdb
  writer -.->|"init_metamorphosis_db()"| mdb
```

**11 edges** among **4 nodes**: 9 live, 2 dotted self-test.

What this collapses: `from_path_import load_module` is not an extra node now. It is the same `load_module()` edges. `prefix.py` / launcher / `inject_process_paths` are outside this box.

What is still true inside the box:

- `metamorphosis_structures.py` is only a callee.
- `metamorphosis_bootloader.py` never talks to writer or structures directly.
- Writer and db both assemble structures independently. They do not call each other on the boot path.
- The repeating triple on each solid pair is one real hop told three times: assemble via borrowed `load_module`, extract a symbol, call it.