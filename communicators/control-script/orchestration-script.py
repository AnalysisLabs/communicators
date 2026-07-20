# home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/control-script/orchestration-script.py

from prelude.standard import*
from prelude.internal_lib import*

def main():
    loops = stage(sys.argv[1])
    while True:
        for loop in loops:
            loop.reconcile()
        ManifestLogger.global_checkpoint()
        sleep_or_wait()  # Abstracted event waiting

if __name__ == '__main__':
    main()
