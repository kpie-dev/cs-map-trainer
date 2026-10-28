import ctypes
import fcntl
import os
import signal
import sys
import threading
import time
from contextlib import contextmanager

PR_SET_PDEATHSIG = 1


@contextmanager
def parser_slot(root):
    root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(root / ".parser.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
        else:
            # Close only: an inherited descriptor must keep the lock if the worker dies.
            yield lock


def terminate_with_parent(parent_pid):
    if sys.platform == "linux":
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot arm parser parent-death signal")
        if os.getppid() != parent_pid:
            os.kill(os.getpid(), signal.SIGKILL)
    else:

        def watch_parent():
            while os.getppid() == parent_pid:
                time.sleep(0.1)
            os.kill(os.getpid(), signal.SIGKILL)

        threading.Thread(target=watch_parent, daemon=True).start()
