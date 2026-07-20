## Protocol

1. Dissect the yaml based config from the terminal argument.
2. Initialize the ConfigState, IdealState, RealState, and TempState namespaces, inheriting namespace.py as a module.
3. Populate the ConfigState from the sys arg from 1 above.
4. Populate the IdealState from ConfigState.ideal_path.