# Genesis_DB — Place in the grand scheme

This area is the **ephemeral runtime store and prefix factory** for a single boot.

It:

- Initializes the empty store and its structural root.
- Writes and reads generated program text (content-addressed payloads + tree names).
- Builds tiered prefixes and stores the results inside the store for later load.

It is not the system of record for durable source layout; durable sources live
elsewhere and are tracked by file identity. See Philosophy: Ephemeral Runtime
Store and Prefix Tier Principle.
