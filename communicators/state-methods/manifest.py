class Manifest:

    @internalmethod
    def _get_internal_files(self):
        parent_dir = Path(__file__).parent
        files = set()
        if parent_dir.exists():
            for f in parent_dir.iterdir():
                files.add(f.name)
        return files

    @internalmethod
    def _find_external_caller(self, internal_files):
        frame = inspect.currentframe()
        while frame:
            caller_file = frame.f_code.co_filename.split('/')[-1]
            if caller_file not in internal_files and "/usr/lib/python" not in frame.f_code.co_filename:
                return f'{frame.f_code.co_filename}.{frame.f_code.co_qualname}'
            frame = frame.f_back
        return None

    @internalmethod
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

    @externalmethod
    def debug(*args):
        message = ' '.join(str(arg) for arg in args)
        _log('DEBUG', message)

    @externalmethod
    def info(*args):
        message = ' '.join(str(arg) for arg in args)
        _log('INFO', message)

    @externalmethod
    def warning(*args):
        message = ' '.join(str(arg) for arg in args)
        _log('WARNING', message)

    @externalmethod
    def error(*args):
        message = ' '.join(str(arg) for arg in args)
        _log('ERROR', message)

    @externalmethod
    def critical(*args):
        message = ' '.join(str(arg) for arg in args)
        _log('CRITICAL', message)

    @externalmethod
    def printer(*args):
        message = ' '.join(str(arg) for arg in args)
        _log('PRINTER', message)

    @externalmethod
    def json(*args):
        messages = []
        for arg in args:
            try:
                if isinstance(arg, str):
                    json.loads(arg)
                messages.append(json.dumps(arg))
            except:
                messages.append('{invalid json}')
        _log('JSON', ' '.join(messages))

    @externalmethod
    def freight(*args):
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
        _log('FREIGHT', ' '.join(messages))
