import inspect, json, secrets
from datetime import datetime, timezone

def truncate(limit: int, message) -> str:
    msg = str(message)
    if len(msg) > 2 * limit:
        return msg[:limit] + '...' + msg[-limit:]
    return msg

def manifest(message):
    frame = inspect.currentframe().f_back
    filename = frame.f_code.co_filename.rsplit('/', 1)[-1]
    func_name = frame.f_code.co_name
    class_name = frame.f_locals.get('self').__class__.__name__ if 'self' in frame.f_locals else ''
    process_path = f'[{filename}.{class_name}.{func_name}]' if class_name else f'[{filename}.{func_name}]'
    utc_ts = datetime.now(timezone.utc).isoformat()
    print(f'{utc_ts} {process_path} {message}')

def singleton(cls):
    instances = {}
    original_new = cls.__new__
    def __new__(cls, *args, **kwargs):
        if cls not in instances:
            instances[cls] = original_new(cls, *args, **kwargs)
        return instances[cls]
    cls.__new__ = staticmethod(__new__)
    return cls

class Manifest:
    def debug(self, *args):
        message = ' '.join(str(arg) for arg in args)
        self._log('DEBUG', message)

    def info(self, *args):
        message = ' '.join(str(arg) for arg in args)
        self._log('INFO', message)

    def warning(self, *args):
        message = ' '.join(str(arg) for arg in args)
        self._log('WARNING', message)

    def error(self, *args):
        message = ' '.join(str(arg) for arg in args)
        self._log('ERROR', message)

    def critical(self, *args):
        message = ' '.join(str(arg) for arg in args)
        self._log('CRITICAL', message)

    def printer(self, *args):
        message = ' '.join(str(arg) for arg in args)
        self._log('PRINTER', message)

    def _log(self, level, message):
        frame = inspect.currentframe().f_back.f_back
        filename = frame.f_code.co_filename.rsplit('/', 1)[-1]
        # func_name = frame.f_code.co_name
        class_name = frame.f_locals.get('self').__class__.__name__ if 'self' in frame.f_locals else ''
        func_name = frame.f_code.co_qualname
        if class_name and func_name.startswith(class_name + '.'):
            func_name = func_name[len(class_name) + 1:]
        func_name = func_name.replace('.<locals>', '.')
        class_name = frame.f_locals.get('self').__class__.__name__ if 'self' in frame.f_locals else ''
        process_path = f'[{filename}.{class_name}.{func_name}]' if class_name else f'[{filename}.{func_name}]'
        process_path = process_path.replace('..', '.')
        utc_ts = datetime.now(timezone.utc).isoformat()
        if level:
            print(f'{utc_ts} {level} {process_path} {message}')
        else:
            print(f'{utc_ts} {process_path} {message}')

manifest = Manifest()

class freight(dict):
    """
    I consider Freight a sub-library within the broader communicators library.
    Freight is a dict subclass designed for secure messaging payloads, enforcing data integrity by requiring CSV strings (with commas) for all values except 'communicator_token', which auto-generates when missing. Validation triggers on operations like __setitem__ and update, while dump/load methods enable JSON handling without discarding original safeguards.

    objective function(services freight shall offer):
    1. 1:1 drop in replacement of equivalent json lib calls. Such the json lib calls become unnecessary in any api use cases.
    2. ability to clear the contents of the freight while keeping the communicator_token intact.
    3. ability to easily call, update or pop an entry from a freight object.
    4. ability to be manifested or printed easily (see Manifest module above)

    progress (this is what we are working on broadly):
    1. 1:1 Drop-in for JSON Lib Calls:** 85% complete – to_json and from_json function well; however, loads, load, and dump static methods are incomplete or buggy (e.g., dump does not return data, loads may not validate CSV strings post-deserialization).
    2. Clear Contents While Keeping communicator_token:** Incomplete – No dedicated method; manual operations risk token loss.
    3. Easy Dict Ops (update/pop/get/etc.):** Complete – Inherits dict methods with validation in __setitem__ and update.
    4. JSON Handling without Discarding Originals:** Complete – dump/load methods added alongside existing ones.

    DRY Adherence: Mostly good, but _ensure_token logic is duplicated; could centralize. Overall, freight is ~80% complete and functional but 'scrambled' – use this as your high-level checklist: prioritize refining static methods and adding a clear_contents() method to reach 'well oiled machine' status.
    """

    # Initializes freight dict with optional data and auto-generates communicator_token.
    def __init__(self, data=None):
        super().__init__(data or {})
        self._ensure_token()

    # Returns JSON string representation of the freight object.
    def __str__(self):
        return self.to_json()

    def _central_enforce(self):
        for k, v in self.items():
            if k != 'communicator_token' and (not isinstance(v, str) or ',' not in v):
                raise ValueError(manifest.warning('Freight structure: CSV strings required'))
        if 'communicator_token' not in self:
            self['communicator_token'] = f'{secrets.randbelow(10**29):029d}'

    # Retrieves value only if it's a CSV string; otherwise returns None.
    def get(self, key, default=None):
        val = super().get(key, default)
        if val is not None and not isinstance(val, str):
            return None
        return val

    # Automatically adds a unique communicator_token if missing.
    def _ensure_token(data):
        if 'communicator_token' not in self:
            data['communicator_token'] = f'{secrets.randbelow(10**29):029d}'

    # Sets key-value pair, enforcing CSV string validation except for token.
    def __setitem__(self, key, value):
        if key != 'communicator_token' and (not isinstance(value, str) or ',' not in value):
            raise ValueError(manifest.warning('Values must be CSV strings'))
        super().__setitem__(key, value)

    # Updates the dict and ensures token presence.
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._ensure_token()

    # Creates a token-free copy of the payload for external dumping.
    def dumpPlus(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a dict')
        copied = payload.copy() if hasattr(payload, 'copy') else dict(payload)
        copied.pop('communicator_token', None)
        return copied

    # Class method to deserialize JSON, validating dict and CSV formats.
    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError(manifest.warning('Must be dict'))
        for v in data.values():
            if not isinstance(v, str) or ',' not in v:
                raise ValueError(manifest.warning('CSV required'))
        return cls(data)

    # Serializes the freight dict to a JSON string.
    def to_json(self):
        return json.dumps(dict(self))

    @staticmethod
    def loads(self, message):
        data = json.loads(message)
        self._ensure_token(data)
        return data

    @staticmethod
    def load(self, message):
        data = json.load(message)
        self._ensure_token(data)
        return data

    @staticmethod
    def dump(self, message):
        data = json.dump(message)
        data.pop('communicator_token', None)
        return data

    @staticmethod
    def dump(self, message):
        data = json.dumps(message)
        data.pop('communicator_token', None)
        return data
