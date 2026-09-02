localhost = "localhost"

_harness_ref = PathReffs.FileRef(
    uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
    file_path="Metamorphosis/execution",
    file_name="execution_harness.py",
)

load_module, execution_harness = AtomicImporter.from_path_import(
    PathReffs.resolve_path(
        _harness_ref.uuid,
        _harness_ref.file_path,
        _harness_ref.file_name,
    ),
    "load_module",
    "execution_harness",
)

_namespace_ref = PathReffs.FileRef(
    uuid="253a5376-dfdc-4e07-b4d1-20446bb9211f",
    file_path="Metamorphosis/servers",
    file_name="namespace.py",
)

_namespace_src, _ = load_module(
    src=_namespace_ref,
    dst="Metamorphosis/generated/namespace.py",
    prefix=prefix,
)

request, = AtomicImporter.from_code_import(
    _namespace_src,
    "namespace",
    "request",
)

def load(db_ref, file_ref=None, blob=None):
    if file_ref is not None:
        return request(db_ref, file_ref=file_ref)
    if blob is not None:
        return request(db_ref, blob=blob)
    raise TypeError("load requires file_ref or blob")

def build(spec_ref, transformer_ref, dest_ref):
    spec = request(spec_ref)
    blob = execution_harness(
        src=transformer_ref,
        dst="Metamorphosis/generated/build_transformer.py",
        prefix=prefix,
        wait=True,
        launch=True,
        spec=spec_ref,
    )
    return request(dest_ref, blob=blob)

_METHODS_DIR_REF = PathReffs.FileRef(
    uuid="6436be95-3579-4b62-9c06-49de2dd6c595",
    file_path="Metamorphosis",
    file_name="transpiler-methods",
)

_LOAD_RE = re.compile(
    r'^\s*(\d+)\.\s+load\s+(\S+)\s*->\s*"([^"]+)"\s*$'
)
_BUILD_RE = re.compile(
    r'^\s*(\d+)\.\s+build\s+(\S+)\((\S+)\)\s*->\s*"([^"]+)"\s*$'
)


def _methods_parent_path() -> str:
    return f"{_METHODS_DIR_REF.file_path}/{_METHODS_DIR_REF.file_name}"


def _file_ref_under_methods(name: str) -> "PathReffs.FileRef":
    parent = _methods_parent_path()
    registry = json.loads(
        (COMMUNICATORS_ROOT / "file_registry.json").read_text(encoding="utf-8")
    )
    for entry in registry:
        if entry["file_path"] == parent and entry["file_name"] == name:
            return PathReffs.FileRef(
                uuid=entry["uuid"],
                file_path=entry["file_path"],
                file_name=entry["file_name"],
            )
    raise FileNotFoundError(
        f"{name!r} is not registered under {_methods_parent_path()}"
    )


def _join_vfs(container: str, name: str) -> str:
    container = container.rstrip("/")
    if container.split("/")[-1] == name:
        return container
    return f"{container}/{name}"


def _emit_file_ref(file_ref: "PathReffs.FileRef") -> str:
    return (
        "PathReffs.FileRef("
        f"uuid={file_ref.uuid!r}, "
        f"file_path={file_ref.file_path!r}, "
        f"file_name={file_ref.file_name!r})"
    )


def parse_line(line: str, name_map: dict[str, str]) -> str | None:
    line = line.strip()
    if not line:
        return None

    m = _LOAD_RE.match(line)
    if m:
        num_str, name, dest = m.group(1), m.group(2), m.group(3)
        db_ref = _join_vfs(dest, name)
        name_map[name] = db_ref
        file_ref = _file_ref_under_methods(name)
        return (
            f"code_block_{num_str} = load("
            f"db_ref={db_ref!r}, "
            f"file_ref={_emit_file_ref(file_ref)})"
        )

    m = _BUILD_RE.match(line)
    if m:
        num_str, transformer, spec, dest = m.group(1), m.group(2), m.group(3), m.group(4)
        if transformer not in name_map:
            raise ValueError(f"bare name {transformer!r} used before its location was specified")
        if spec not in name_map:
            raise ValueError(f"bare name {spec!r} used before its location was specified")
        dest_ref = dest.rstrip("/")
        name_map[dest_ref.split("/")[-1]] = dest_ref
        return (
            f"code_block_{num_str} = build("
            f"spec_ref={name_map[spec]!r}, "
            f"transformer_ref={name_map[transformer]!r}, "
            f"dest_ref={dest_ref!r})"
        )

    raise ValueError(f"unrecognized panel line: {line!r}")


def transpile(md_file) -> str:
    code = []
    name_map: dict[str, str] = {}
    invalid_lines = []
    with open(md_file, "r") as f:
        for num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                code.append(parse_line(line, name_map))
            except Exception as e:
                invalid_lines.append(f"Line {num}: {line.rstrip()!r} ({e})")
    if invalid_lines:
        raise ValueError(f"Invalid lines in {md_file}:\n" + "\n".join(invalid_lines))

    base_dir_src = (
        "base_dir = PathReffs.resolve_path(\n"
        f"    {_METHODS_DIR_REF.uuid!r},\n"
        f"    {_METHODS_DIR_REF.file_path!r},\n"
        f"    {_METHODS_DIR_REF.file_name!r},\n"
        ")\n"
    )
    generated_code = (
        base_dir_src
        + "\n"
        + inspect.getsource(load)
        + "\n"
        + inspect.getsource(build)
        + "\n"
        + "\n".join(code)
        + "\n"
    )

    dests = list(name_map.values())
    counts = Counter(dests)
    shared = {k: v for k, v in counts.items() if v > 1}
    print(
        "All mapped vfs dests "
        + ("unique" if not shared else f"shared: {shared}")
        + f". names: {sorted(name_map)}"
    )
    return generated_code


if __name__ == "__main__":
    md_file = PathReffs.resolve_path(
        _METHODS_DIR_REF.uuid,
        _METHODS_DIR_REF.file_path,
        _METHODS_DIR_REF.file_name,
    ) / "panel.md"
    cat = transpile(md_file)
    caterpillar_path = (
        Path(COMMUNICATORS_ROOT) / "Metamorphosis" / "transpiler" / "caterpillar_transpiler.py"
    )
    caterpillar_path.write_text(cat, encoding="utf-8")
    load(db_ref="Metamorphosis/transpiler/caterpillar_transpiler.py", blob=cat)
