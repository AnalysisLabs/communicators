# Metamorphosis — Place in the grand scheme

Metamorphosis is the **transformation and orchestration** stage: servers,
transpilers, control scripts, and graph/process machinery that operate once
Genesis has provided a runtime context.

Typical concerns:

- Long-lived or quasi-independent server processes (e.g. namespace-style services).
- Transpilation and IR/graph views of desired topology.
- Control scripts and layer methods that drive change.

It assumes Genesis has already assembled prefix and launch machinery. It does
not replace Imago’s ongoing health/feedback role.
