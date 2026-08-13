# Genesis — Place in the grand scheme

Genesis is the **ignition and substrate** stage of a Communicators run.

It is responsible for:

- Establishing how tracked real files are named and resolved (identity).
- Creating the ephemeral runtime store for generated program text.
- Assembling the ordered prefix (tiers) that user programs will see.
- Launching programs under a harness that combines prefix + user source and
  executes them in a controlled child context.

Genesis does not own long-running product servers or ongoing healing policy;
those belong to Metamorphosis and Imago. Without Genesis, nothing else has a
coherent runtime context (see Philosophy: Runtime Context).
