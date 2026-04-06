import inspect, json, secrets
from datetime import datetime, timezone

def singleton(cls):
    instances = {}
    original_new = cls.__new__
    def __new__(cls, *args, **kwargs):
        if cls not in instances:
            instances[cls] = original_new(cls, *args, **kwargs)
        return instances[cls]
    cls.__new__ = staticmethod(__new__)
    return cls

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

class Manifest:
    def _try_log(self, level, *args):
        try:
            self._log(level, ' '.join(str(arg) for arg in args))
        except Exception as e:
            self._log('ERROR', f'Log attempt failed for {level} with args {args}: {e}')

     def debug(self, *args):
        self._try_log('DEBUG', *args)

     def info(self, *args):
        self._try_log('INFO', *args)

     def warning(self, *args):
        self._try_log('WARNING', *args)

     def error(self, *args):
        self._try_log('ERROR', *args)

     def critical(self, *args):
        self._try_log('CRITICAL', *args)

     def printer(self, *args):
        self._try_log('PRINTER', *args)

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
    def __init__(self, data=None):
        super().__init__(data or {})
        self._ensure_token()

    def __str__(self):
        return self.to_json()

    def get(self, key, default=None):
        val = super().get(key, default)
        if val is not None and not isinstance(val, str):
            return None
        return val

    def _ensure_token(self):
        if 'communicator_token' not in self:
            self['communicator_token'] = f'{secrets.randbelow(10**29):029d}'

    def __setitem__(self, key, value):
        if key != 'communicator_token' and (not isinstance(value, str) or ',' not in value):
            raise ValueError(manifest.warning('Values must be CSV strings'))
        super().__setitem__(key, value)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._ensure_token()

    def dump(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Payload must be a dict')
        copied = payload.copy() if hasattr(payload, 'copy') else dict(payload)
        copied.pop('communicator_token', None)
        return copied

    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError(manifest.warning('Must be dict'))
        for v in data.values():
            if not isinstance(v, str) or ',' not in v:
                raise ValueError(manifest.warning('CSV required'))
        return cls(data)

    def to_json(self):
        return json.dumps(dict(self))
