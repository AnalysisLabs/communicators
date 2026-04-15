import inspect, json, secrets, os
from datetime import datetime, timezone
from pathlib import Path

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
                    f = freight.upgrades(arg)
                    messages.append(f)
                except:
                    messages.append('{invalid freight}')
        self._log('FREIGHT', ' '.join(messages))

    def _get_internal_files(self):
        gitignore_path = Path(__file__).parent.parent / 'Communicators/.gitignore'
        ignored = set()
        if gitignore_path.exists():
            with open(gitignore_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        ignored.add(line)
        dirs = [Path(__file__).parent.parent / 'Communicators/communicators/', Path(__file__).parent.parent / 'Communicators/']
        print("gitignore_path", gitignore_path)
        files = set()
        for d in dirs:
            if d.exists():
                for f in d.rglob('*'):
                    if f.is_file() and f.name not in ignored:
                        files.add(f.name)
        print("files: ", files)
        return files

    def _find_external_caller(self, internal_files):
        frame = inspect.currentframe()
        print("Frame: ", frame)
        while frame:
            caller_file = frame.f_code.co_filename.split('/')[-1]
            if caller_file not in internal_files:
                return f'{frame.f_code.co_filename}.{frame.f_code.co_qualname}'
            frame = frame.f_back
        return None

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
        internal_files = self._get_internal_files()
        if filename in internal_files:
            external_caller = self._find_external_caller(internal_files)
            if external_caller:
                process_path = f'[{process_path[1:-1]} from {external_caller}]'
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
        data = json.loads(message)
        freight_obj.__init__(data)
        return freight_obj

    @staticmethod
    def upgrades(message):
        if message is None:
            message = cls()
        data = json.loads(message)
        message.__init__(data)
        return message

    @staticmethod
    def load(freight_obj=None, fp=None):
        if freight_obj is None:
            freight_obj = cls()
        data = json.load(fp)
        freight_obj.__init__(data)
        return freight_obj

    @staticmethod
    def dump(freight_obj=None, file_destination=None):
        data = dict(freight_obj) if freight_obj else {}
        data.pop('communicator_token', None)
        json.dump(data, file_destination)

    @staticmethod
    def dumps(freight_obj=None):
        data = json.dumps(freight_obj)
        data.pop('communicator_token', None)
        return data
