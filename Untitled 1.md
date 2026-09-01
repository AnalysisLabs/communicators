Control flow is only among the execution harness and the four Metamorphosis_DB modules. The graph below is those programs and the actual calls/execs between them — not namespace or egg.

```mermaid
flowchart LR
  subgraph EXEC["Metamorphosis/execution"]
    boot["bootloader.py"]
    harness["execution_harness.py"]
    launcher["execution_launcher.py"]
    vfs["vfs_process_path.py"]
    prefix[["prefix.py\n(dump, not a program)"]]
  end

  subgraph DB["Metamorphosis/Metamorphosis_DB"]
    mboot["metamorphosis_bootloader.py"]
    mdb["metamorphosis_db.py"]
    writer["metamorphosis_writer.py"]
    structs["metamorphosis_structures.py"]
  end

  %% stage entry
  boot -->|"execution_harness(src=metamorphosis_bootloader)"| harness
  boot -->|"writes dump"| prefix

  %% harness assembly / launch
  harness -->|"load_module()"| harness
  harness -->|"inject_process_paths()"| vfs
  harness -->|"save_combined() / flush_pending_artifacts()"| writer
  harness -->|"_get_write_file() → from_code_import write_file"| writer
  harness -->|"Popen execution_launcher.py"| launcher
  launcher -->|"exec(combined source)"| mboot

  %% dump readers (assembly token, not domain API)
  mboot -->|"Path.read_text()"| prefix
  mdb -->|"Path.read_text()"| prefix
  writer -->|"Path.read_text()"| prefix

  %% DB boot chain (in-process after exec)
  mboot -->|"from_path_import load_module"| harness
  mboot -->|"load_module(src=metamorphosis_db)"| harness
  mboot -->|"from_code_import init_metamorphosis_db"| mdb
  mboot -->|"init_metamorphosis_db()"| mdb

  mdb -->|"from_path_import load_module"| harness
  mdb -->|"load_module(src=metamorphosis_structures)"| harness
  mdb -->|"from_code_import create_core_structures"| structs
  mdb -->|"create_core_structures(conn)"| structs

  %% writer is both a harness dependency and a structures consumer
  writer -->|"from_path_import load_module"| harness
  writer -->|"load_module(src=metamorphosis_structures)"| harness
  writer -->|"from_code_import create_*"| structs
  writer -->|"create_core_structures / create_vfs_tables / …"| structs

  %% writer self-test only (__main__, not boot)
  writer -.->|"load_module(src=metamorphosis_db)\nthen init_metamorphosis_db()"| mdb
```

24 edges

How to read it:

- **Solid edges** are the live boot path. **Dotted** is writer `__main__` self-test only.
- `bootloader.py` is the only program that *receives* the prefix as an argument. Everyone else either gets it prepended into source (`exec`) or re-reads the dump to pass into `load_module`.
- `execution_harness.py` sits in the middle of almost every edge. Domain modules do not import each other as files; they ask the harness to assemble a child, then `from_code_import` a symbol and call it.
- `metamorphosis_structures.py` is a leaf: it is only assembled and called. It never reads `prefix.py` and never calls back into execution.
- `vfs_process_path.py` is only used by the harness during assembly, not by the DB modules.
- The harness → writer edge is the persistence side-path (`save_combined` / flush). It is also why writer load is re-entrancy-guarded: writer top-level itself calls `load_module(structures)`.

The repeating triangle on the DB side is the surface a `prefix=` kwarg would have to cover: **mboot → harness → mdb → harness → structs**, and independently **harness → writer → harness → structs**.