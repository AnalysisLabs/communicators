import inspect, json, secrets, os, threading
_shared_lock = threading.Lock()
from datetime import datetime, timezone
from weakref import WeakValueDictionary
from pathlib import Path

# -----------------------------
# Generic state functions that don't require full classes
# -----------------------------

def truncate(limit: int, message) -> str:
    msg = str(message)
    if len(msg) > 2 * limit:
        return msg[:limit] + '...' + msg[-limit:]
    return msg

def singleton(cls):
    instances = {}
    original_new = cls.__new__
    def __new__(cls, *args, **kwargs):
        if cls not in instances:
            instances[cls] = original_new(cls, *args, **kwargs)
        return instances[cls]
    cls.__new__ = staticmethod(__new__)
    return cls

def anchor_multiton(cls):
    instances = WeakValueDictionary()
    original_new = cls.__new__
    def __new__(cls, *args, **kwargs):
        with _shared_lock:
            if cls not in instances:
                instances[cls] = original_new(cls, *args, **kwargs)
        return instances[cls]
    cls.__new__ = staticmethod(__new__)
    return cls

def aux_multiton(anchor_cls):
    instances = WeakValueDictionary()
    def decorator(cls):
        original_new = cls.__new__
        def __new__(cls, *args, **kwargs):
            with _shared_lock:
                chain_key = frozenset([anchor_cls, cls])
                if chain_key not in instances:
                    instances[chain_key] = original_new(cls, *args, **kwargs)
            return instances[chain_key]
        cls.__new__ = staticmethod(__new__)
        return cls
    return decorator

class freight(dict):

    # Initializes freight dict with optional data and auto-generates communicator_token.
    def __init__(self, data=None):
        super().__init__(data or {})
        self._central_enforce()

    def _central_enforce(self):
        if 'communicator_token' not in self:
            self['communicator_token'] = f'{secrets.randbelow(10**29):029d}'

    @staticmethod
    def get(freight_obj=None, key=None, default=None):
        val = freight_obj.get(key, default)
        if val is not None and (not isinstance(val, str) or ',' not in val):
            return default
        return val

    @staticmethod
    def add(freight_obj=None, key=None, value=None):
        if key == 'communicator_token':
            raise ValueError('Cannot add communicator_token manually')
        if key in freight_obj:
            raise KeyError('Key already exists; use update instead')
        if not isinstance(value, str) or ',' not in value:
            raise ValueError('Value must be a CSV string (containing a comma)')
        freight_obj[key] = value

    @staticmethod
    def pop(freight_obj=None, key=None, default=None):
        if key == 'communicator_token':
            raise ValueError('Popping communicator_token is forbidden. You must use dump(s) to remove communicator_token')
        else:
            return freight_obj.pop(key, default)

    @staticmethod
    def update(freight_obj=None, *args, **kwargs):
        data = {}
        if args:
            data.update(args[0])
        data.update(kwargs)
        for key in data:
            if key not in freight_obj:
                raise KeyError(f"Cannot change keys by adding '{key}'.")
        super(freight, freight_obj).update(data)

    @staticmethod
    def wipe(freight_obj=None):
        for key in list(freight_obj.keys()):
            if key != 'communicator_token':
                freight_obj.pop(key)
        return freight_obj

    @staticmethod
    def loads(freight_obj=None, message=None):
        if freight_obj is None:
            freight_obj = cls()
        data = message if isinstance(message, dict) else json.loads(message)
        freight_obj.__init__(data)
        return freight_obj

    @staticmethod
    def upgrades(message):
        if message is None:
            return freight()
        if isinstance(message, dict):
            return freight(message)
        return freight(json.loads(message))

    @staticmethod
    def load(freight_obj=None, fp=None):
        if freight_obj is None:
            freight_obj = cls()
        data = json.load(fp)
        freight_obj.__init__(data)
        return freight_obj

    @staticmethod
    def dump(freight_obj=None, file_destination=None):
        freight_obj.pop('communicator_token', None)
        data = dict(freight_obj) if freight_obj else {}
        json.dump(data, file_destination)

    @staticmethod
    def dumps(freight_obj=None):
        freight_obj.pop('communicator_token', None)
        data = json.dumps(freight_obj)
        return data
