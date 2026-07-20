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

transponder_code, _ = execution_harness.load_module('internal', 'edge-methods/connections/transponder_module.py')
transponder = types.ModuleType('transponder')
exec(transponder_code, transponder.__dict__)
transponder.__dict__.update({k:v for k,v in Manifest.__dict__.items() if not k.startswith('__')})

__all__ = ['Manifest', 'transponder']
