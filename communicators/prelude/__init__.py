# Pull the actual names into this namespace (what "from prelude import *" expects)
from .standard import *
from .internal_lib import *

# Make * predictable for both humans and IDEs
__all__ = [
    *getattr(standard, "__all__", []),
    *getattr(internal_lib, "__all__", []),
]
