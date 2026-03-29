import json
import secrets
from .state import manifest, truncate

class Freight(dict):
    def __init__(self, data=None):
        super().__init__(data or {})
        self._ensure_token()

    def __str__(self):
        return self.to_json()

    def _ensure_token(self):
        if 'communicator_token' not in self:
            self['communicator_token'] = f'{secrets.randbelow(10**29):029d}'

    def __setitem__(self, key, value):
        if key != 'communicator_token' and (not isinstance(value, str) or ',' not in value):
            raise ValueError(manifest.warning('Values must be CSV strings'))
        super().__setitem__(key, value)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._ensure_token()

    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError(manifest.warning('Must be dict'))
        for v in data.values():
            if not isinstance(v, str) or ',' not in v:
                raise ValueError(manifest.warning('CSV required'))
        return cls(data)

    def to_json(self):
        return json.dumps(dict(self))
