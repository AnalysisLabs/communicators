# home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/control-script/orchestration-script.py

from prelude.standard import*
from prelude.internal_lib import*

def main():
    landscape(sys.argv[1])
    ir = build_ir()
    registry = ProcessRegistry()
    loops = [HomeostasisLoop(node, IdealState, registry, ManifestLogger(node.id)) for node in ir.nodes] + [HomeostasisLoop(edge, IdealState, registry, ManifestLogger(edge.id)) for edge in ir.edges]
    while True:
        for loop in loops:
            loop.reconcile()
        ManifestLogger.global_checkpoint()
        sleep_or_wait()  # Abstracted event waiting

if __name__ == '__main__':
    main()
