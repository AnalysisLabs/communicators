import communicators_core as core   # <-- your pybind11 module (you implement this in C++)

# --- Instance management (delegate to C++ registry) ---
singleton        = core.singleton
anchor_multiton  = core.anchor_multiton
aux_multiton     = core.aux_multiton

# --- Logging / freight / truncate (delegate or keep thin Python if you prefer) ---
manifest = core.manifest
truncate = core.truncate
freight  = core.freight

# --- Unix socket decorators (delegate) ---
unix_client = core.unix_client
unix_server = core.unix_server

# --- Tank (vestigial but kept for API compatibility) ---
tank = core.tank

# --- Communicator decorators (minimal Python wrappers around C++ objects) ---
def server(cls):
    class Wrapped(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.negative = core.NegativeCom(self.config)
            self.positive = core.PositiveCom(self.config)
            self.to_N = self.negative.to_N
            self.to_P = self.positive.to_P

        def run_server(self):
            core.run_positive_server(self.positive, self.config.get("positive_address", {}))
    return Wrapped

NegativeCommunicator = core.NegativeCommunicator
PositiveCommunicator = core.PositiveCommunicator
