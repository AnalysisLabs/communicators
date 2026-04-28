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
        parent_dir = Path(__file__).parent
        files = set()
        if parent_dir.exists():
            for f in parent_dir.iterdir():
                files.add(f.name)
        return files

    def _find_external_caller(self, internal_files):
        frame = inspect.currentframe()
        while frame:
            caller_file = frame.f_code.co_filename.split('/')[-1]
            if caller_file not in internal_files and "/usr/lib/python" not in frame.f_code.co_filename:
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
