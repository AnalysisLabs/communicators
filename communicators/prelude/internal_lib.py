import os
from pathlib import Path
p = Path(__file__).resolve()
while p.name != 'communicators':
    p = p.parent
project_dir = p
import sys
sys.path.insert(0, str(project_dir / 'state-methods'))
from namespace import BaseNamespace, populate_namespace

__all__ = ['BaseNamespace', 'populate_namespace']
