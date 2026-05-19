"""Cache em memória com TTL simples."""
import time

_store: dict = {}
TTL = 300  # 5 minutos


def get(key: str):
    entry = _store.get(key)
    if entry and time.time() - entry["ts"] < TTL:
        return entry["val"]
    return None


def set(key: str, value):
    _store[key] = {"val": value, "ts": time.time()}


def delete_prefix(prefix: str) -> int:
    keys = [k for k in _store if k.startswith(prefix)]
    for k in keys:
        del _store[k]
    return len(keys)


def clear_all():
    _store.clear()
