# decorators.py

import os, asyncio, signal, shutil, subprocess, time, threading
from .core import NegativeCom, PositiveCom
from aiohttp import web

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
            app = web.Application()
            app.router.add_get('/proxy/ws', self.positive.accept)
            positive_addr = self.config.get('positive_address', {})
            host = positive_addr.get('host')
            port = int(positive_addr.get('port'))
            web.run_app(app, host=host, port=port)
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
            app = web.Application()
            app.router.add_get('/proxy/ws', self.positive.accept)
            positive_addr = self.config.get('positive_address', {})
            host = positive_addr.get('host')
            port = int(positive_addr.get('port'))
            web.run_app(app, host=host, port=port)
    return Wrapped
