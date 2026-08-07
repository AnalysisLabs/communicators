localhost = "localhost"

def load(object_program: str = None, with_program: str = None, in_namespace: dict = None, from_namespace: dict = None, to_namespace: dict = None):
    if os.path.exists(str(object_program)):
        contents = open(object_program).read()
    else:
        contents = object_program
    if with_program:
        contents = subprocess.run(['python3', with_program, object_program], capture_output=True, text=True).stdout
    r = transponder.request_response(localhost, 8765, {(in_namespace or to_namespace): contents})
    # wait for simple 200 response as green light (detailed pseudocode placeholder)
    return

def build(object_program: str, with_program: str, in_namespace: dict, from_namespace: dict = None, to_namespace: dict = None):
    contents = transponder.request_response(localhost, 8765, (in_namespace or from_namespace))
    result = subprocess.run(['python3', with_program, object_program], capture_output=True, text=True).stdout
    transponder.send_and_close(localhost, 8765, {(in_namespace or to_namespace): result})

def final_byte_cleanup(dirty_line: str) -> str:
    """Final byte literal pass: remove all " (only ' matter for f-strings)."""
    b = dirty_line.encode('utf-8')
    b = b.replace(b'"', b'')
    return b.decode('utf-8')

# Validity check
def parse_line(line):
    # Strip numbered prefix
    line = line.strip()
    words = line.split()
    if len(words) < 3 or not words[0].rstrip('.').isdigit() or words[1] not in ['load', 'build']:
        return None
    num_str = words[0].rstrip('.')
    verb, obj = words[1], words[2]
    path = f"f'{{base_dir}}/{obj}'".encode()
    kwargs = {'object_program': path.replace(b'"', b'').decode()}
    for i in range(3, len(words)):
        if words[i] == 'with' and i + 1 < len(words):
            kwargs['with_program'] = f"f'{{base_dir}}/{words[i + 1]}'"
        if words[i] == 'in' and i + 1 < len(words):
            kwargs['in_namespace'] = f"f'{{base_dir}}/{words[i + 1]}'"
        if words[i] == 'from' and i + 1 < len(words):
            kwargs['from_namespace'] = f"f'{{base_dir}}/{words[i + 1]}'"
        if words[i] == 'to' and i + 1 < len(words):
            kwargs['to_namespace'] = f"f'{{base_dir}}/{words[i + 1]}'"
    kw_str = ', '.join(f'{k}="{v}"' for k, v in kwargs.items())
    dirty_line = f'code_block_{num_str} = {verb}({kw_str})'
    return final_byte_cleanup(dirty_line)

def transpile(md_file):
    code = []
    ordered_objects = []
    has_invalid = False
    invalid_lines = []
    with open(md_file, 'r') as f:
        for num, line in enumerate(f, 1):
            parsed = parse_line(line)
            if parsed:
                code.append(parsed)
            else:
                has_invalid = True
                invalid_lines.append(f'Line {num}: {line.rstrip()!r}')
    if has_invalid:
        # raise ValueError('This is not valid assembly line script')
        raise ValueError(f'Invalid lines in {md_file}:\n' + '\n'.join(invalid_lines))

    # return '\n'.join(code)

    generated_code = '\n'.join(code)
    imports_str = "base_dir = f'{COMMUNICATORS_ROOT}/state-methods'\n\n"
    # Copy load/build verbatim dynamically
    load_src = inspect.getsource(load)
    build_src = inspect.getsource(build)
    generated_code = imports_str + "\n" + load_src + '\n' + build_src + '\n' + generated_code
    # Minimal addition: process code to check object_program='to' uniqueness
    tree = ast.parse(generated_code)
    objects = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and
            isinstance(node.func, ast.Name) and
            node.func.id in ('load', 'build')):
            for kw in node.keywords:
                if kw.arg == 'object_program':
                    if isinstance(kw.value, ast.Constant):
                        objects.append(ast.literal_eval(kw.value))
                    else:
                        objects.append(ast.unparse(kw.value).strip("'\""))
                    break
    counts = Counter(objects)
    shared = {k: v for k, v in counts.items() if v > 1}
    print(f"All 'to' (object_program=) values {'unique' if not shared else f'shared: {shared}'}. Ready for _to_ handling if needed (What's next.md).")
    return generated_code

if __name__ == '__main__':
    md_file = f'{COMMUNICATORS_ROOT}/state-methods/panel.md'
    cat = transpile(md_file)
    caterpillar_path = Path(COMMUNICATORS_ROOT) / 'transpiler' / 'caterpillar_transpiler.py'
    with open(caterpillar_path, 'w') as f:
        f.write(cat)
    load(object_program=cat, in_namespace='Metamorphosis')
    os.execvp('python3', ['python3', 'caterpillar_transpiler.py'])
