"""Offline-only delivery boundary. This build contains no transport."""
def deliver(*args, **kwargs):
    raise RuntimeError('External delivery is disabled in the paper build')
