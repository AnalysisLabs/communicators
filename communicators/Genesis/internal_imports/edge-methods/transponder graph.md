High-level map of `transponder_stack`. Solid arrows are imports. Dashed arrows are the live session the two terminals share.

```mermaid
flowchart TB
  subgraph terminals["two terminals"]
    C["chat_client.py"]
    B["chat_bot.py"]
  end

  subgraph faces["transponder faces"]
    TM["transponder_module.py<br/>NegativeCom / PositiveCom"]
    SH["shims.py<br/>freight, manifest, decorators"]
  end

  subgraph attach["session boot"]
    BW["boot_wire.py"]
    W["wire.py"]
  end

  subgraph slots["duplex slots — Wire picks one"]
    TCP["tcp_socket_slot.py"]
    UNIX["unix_socket_slot.py"]
    WS["websocket_slot.py"]
    SHM["shm_slot.py"]
  end

  subgraph t1["T1 helpers"]
    LOC["locators.py"]
    COD["codec.py"]
    DEM["demo.py"]
  end

  C -->|"subclass ChatClient / to_N / from_N"| TM
  B -->|"subclass ChatBot / to_P / from_P"| TM
  C --> BW
  B --> BW
  BW -->|"Wire.attach + on_message → receiver"| W
  TM -->|"standalone import fallback"| SH
  TM -->|"sender → wire.send"| W
  W -->|"on_payload → face.receiver"| TM

  W -->|"favored attach"| TCP
  W -->|"fallback attach"| UNIX
  W -->|"explicit attach"| WS
  W -->|"last-resort attach"| SHM

  TCP --> COD
  UNIX --> COD
  WS --> COD
  SHM --> COD
  TCP --> LOC
  UNIX --> LOC
  WS --> LOC
  SHM --> LOC
  TCP --> DEM
  UNIX --> DEM
  WS --> DEM
  SHM --> DEM
  W --> COD
  W --> LOC

  C -.->|"tcp 127.0.0.1:19401<br/>or unix path / shm bin"| B

  subgraph leftover["present but not on the chatbot path"]
    TF["test_faces.py"]
    PB["pair_boot.py"]
    WP["wire_prototype.py"]
    HTTP["slot_http.py"]
    MBX["http_mailbox_slot.py"]
    ST["station_tuner_slot.py"]
  end

  TF --> TM
  TF --> W
  PB --> TM
  PB --> W
  WP --> COD
  HTTP --> COD
  HTTP --> LOC
  HTTP --> DEM
  MBX --> COD
  MBX --> LOC
  MBX --> DEM
  ST --> COD
  ST --> LOC
  ST --> DEM
```

Read it top to bottom as the product path: two short programs, one face module, one Wire, one live slot. The leftover box is real files in the directory that the chatbot terminals do not need to start.