from typing import Protocol, runtime_checkable, TypeAlias, Literal

NodeID: TypeAlias = str
GraphID: TypeAlias = str
PID: TypeAlias = int
ManifestLine: TypeAlias = str

@runtime_checkable
class NodeLike(Protocol):
    id: NodeID
    def is_alive(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self, graceful: bool = True) -> None: ...

@runtime_checkable
class GraphLike(Protocol):
    id: GraphID
    nodes: dict[NodeID, NodeLike]
    def reconcile(self) -> None: ...
