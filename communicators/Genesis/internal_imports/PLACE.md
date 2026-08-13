# Genesis/internal_imports — Place in the grand scheme

This area holds **capability sources that are folded into the prefix** (and
related internal helpers), not free-standing user entrypoints.

Pieces here are ordered by the Prefix Tier Principle: base vocabulary first,
then core public objects, then objects that depend on those. Only chosen public
names should remain visible to user programs (Internal Import Principle).

Edge, node, and connection material here supports those public objects; it is
not the place for product orchestration loops (that is Metamorphosis).
