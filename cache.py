import time

class SimpleCache:
    def __init__(self, ttl=60):
        self.ttl = ttl
        self.store = {}

    def get(self, key):
        if key in self.store:
            value, timestamp = self.store[key]
            if time.time() - timestamp < self.ttl:
                return value
        return None

    def set(self, key, value):
        self.store[key] = (value, time.time())
