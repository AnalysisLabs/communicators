# Genesis/execution — Place in the grand scheme

This area is the **process ignition path**: general bootloader, execution
harness, and child-side launcher.

It ensures the runtime store and prefix exist, resolves tracked program
identities, assembles combined sources into the store, and starts child
processes that compile and exec under controlled conditions.

It is the bridge from “substrate is ready” (Genesis_DB) to “a particular
program is running.” Namespace connection and metamorphosis workloads are
*launched from here* but *defined* under Metamorphosis.
