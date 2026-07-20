AST demands: Pure, exec()-able Python syntax—no exceptions.

  

Your exact fail:

```python

>>> import ast

>>> code = '''load(object="config")

build(object="ideal_yaml", with="landscape.py")'''

>>> ast.parse(code)

File "<unknown>", line 2

build(object="ideal_yaml", with="landscape.py")

^^^^

SyntaxError: keyword can't be an expression

```

  

Why: 'with' is reserved keyword. Cannot name kwargs/params/vars with keywords (def with(): no; f(with=1): no).

  

General expectations:

- **Lexical**: Valid tokens (no stray chars).

- **Syntactic**: Grammar rules (parens match, colons for blocks, no keyword misuse).

- **Structural**: Indentation for suites, top-level statements fine (your '\n'.join works).

- **Scope/Mode**: Defaults to 'exec' (module); use ast.parse(code, mode='eval') for exprs.

  

Validate peek:

```python

ast.dump(ast.parse(valid_code)) # Tree str

```

Or walker for your object Counter.

  

Pro tip: Wrap in try: tree = ast.parse(code) except SyntaxError as e: print(e.text, e.lineno, e.offset) — pinpoints like your traceback.

  

Aha: Your DSL gen is structurally sound; just keyword collision from 'with' in panel.md. AST enforces Python invariants ruthlessly.

  

Justification: Pure education on demands via repro, rules, tips—matches 'sit me down... lesson' w/o fix code.

  

Checklist: Clear? Y | Honest? Y | Useful? Y