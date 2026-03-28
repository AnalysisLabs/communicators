import inspect
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
        func_name = frame.f_code.co_name
        class_name = frame.f_locals.get('self').__class__.__name__ if 'self' in frame.f_locals else ''
        process_path = f'[{filename}.{class_name}.{func_name}]' if class_name else f'[{filename}.{func_name}]'
        utc_ts = datetime.now(timezone.utc).isoformat()
        if level:
            print(f'{utc_ts} {level} {process_path} {message}')
        else:
            print(f'{utc_ts} {process_path} {message}')

manifest = Manifest()
