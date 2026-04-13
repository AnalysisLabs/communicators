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

    def json(self, *args):
        messages = []
        for arg in args:
            try:
                if isinstance(arg, str):
                    json.loads(arg)
                messages.append(json.dumps(arg))
            except:
                messages.append('{invalid json}')
        self._log('JSON', ' '.join(messages))

    def freight(self, *args):
        messages = []
        for arg in args:
            if isinstance(arg, freight) and hasattr(arg):
                messages.append(arg)
            else:
                try:
                    f = freight.dumps(arg)
                    messages.append(f)
                except:
                    messages.append('{invalid freight}')
        self._log('FREIGHT', ' '.join(messages))


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

    # Initializes freight dict with optional data and auto-generates communicator_token.
    def __init__(self, data=None):
        super().__init__(data or {})
        self._central_enforce()

    def _central_enforce(self):
        for k, v in self.items():
            if k != 'communicator_token' and (not isinstance(v, str) or ',' not in v):
                raise ValueError(manifest.warning('Freight structure: CSV strings required'))
        if 'communicator_token' not in self:
            self['communicator_token'] = f'{secrets.randbelow(10**29):029d}'

    @staticmethod
    def get(freight_obj, key, default=None):
        val = freight_obj.get(key, default)
        if val is not None and (not isinstance(val, str) or ',' not in val):
            return default
        return val

    @staticmethod
    def add(freight_obj, key, value):
        if key == 'communicator_token':
            raise ValueError('Cannot add communicator_token manually')
        if key in freight_obj:
            raise KeyError('Key already exists; use update instead')
        if not isinstance(value, str) or ',' not in value:
            raise ValueError('Value must be a CSV string (containing a comma)')
        freight_obj[key] = value

    @staticmethod
    def update(freight_obj, *args, **kwargs):
        data = {}
        if args:
            data.update(args[0])
        data.update(kwargs)
        for key in data:
            if key not in freight_obj:
                raise KeyError(f"Cannot change keys by adding '{key}'.")
        super(freight, freight_obj).update(data)

    @staticmethod
    def wipe(freight_obj):
        for key in list(freight_obj.keys()):
            if key != 'communicator_token':
                freight_obj.pop(key)
        return freight_obj

    @staticmethod
    def loads(message):
        data = json.loads(message)
        instance = cls(data)
        return instance

    @staticmethod
    def load(fp):
        data = json.load(fp)
        instance = cls(data)
        return instance

    @staticmethod
    def dump(self, message):
        data = json.dump(message)
        data.pop('communicator_token', None)
        return data

    @staticmethod
    def dumps(self, message):
        data = json.dumps(message)
        data.pop('communicator_token', None)
        return data
