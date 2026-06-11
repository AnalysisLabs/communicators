import os
from pathlib import Path
p = Path(__file__).resolve()
while p.name != 'communicators':
    p = p.parent
project_dir = p
import sys
sys.path.insert(0, str(project_dir / 'env-bootloader'))
import execution_harness
import types

manifest_code, temp_file = execution_harness.load_module('internal', 'state-methods/manifest.py')
manifest = types.ModuleType('manifest')
exec(manifest_code, manifest.__dict__)
Manifest = manifest.manifest

__all__ = ['Manifest']
