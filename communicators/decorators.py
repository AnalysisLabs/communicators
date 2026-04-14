# decorators.py

import os, signal, shutil, subprocess, time, threading
from websockets.sync.server import serve
from .core import NegativeCom, PositiveCom

def singleton(cls):
    instances = {}
    original_new = cls.__new__
    def __new__(cls, *args, **kwargs):
        if cls not in instances:
            instances[cls] = original_new(cls, *args, **kwargs)
        return instances[cls]
    cls.__new__ = staticmethod(__new__)
    return cls

def server(cls):
    class Wrapped(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            negative_config = {'negative_address': self.config.get('negative_address', {})}
            self.negative = NegativeCom(negative_config)
            positive_config = {'positive_address': self.config.get('positive_address', {})}
            self.positive = PositiveCom(positive_config)
            self.to_N = self.negative.to_N
            self.to_P = self.positive.to_P

        def run_server(self):
            positive_addr = self.config.get('positive_address', {})
            host = positive_addr.get('host')
            port = int(positive_addr.get('port'))
            with serve(self.positive.receiver, host, port) as server:
                server.serve_forever()
    return Wrapped

# This tank is vestigial for now but may have value later.
def tank(cls):
    original_new = cls.__new__
    def __new__(cls, config=None, *args, **kwargs):
        config = config
        instance = original_new(cls, *args, **kwargs)
        instance.config = config
        return instance
    cls.__new__ = staticmethod(__new__)
    cls.alias = cls.__name__  # Add alias for generic access
    return cls

def NegativeCommunicator(cls):
    if isinstance(cls, type):
        class Wrapped(cls):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.negative = NegativeCom(self.config)
                self.to_N = self.negative.to_N
        return Wrapped

def PositiveCommunicator(cls):
    class Wrapped(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.positive = PositiveCom(self.config)
            self.to_P = self.positive.to_P

        def run_server(self):
            positive_addr = self.config.get('positive_address', {})
            host = positive_addr.get('host')
            port = int(positive_addr.get('port'))
            with serve(self.positive.receiver, host, port) as server:
                server.serve_forever()
    return Wrapped
