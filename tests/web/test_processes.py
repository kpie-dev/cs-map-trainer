import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import psutil
import pytest

from cs_map_trainer.web.processes import parser_slot, terminate_with_parent

SUPERVISOR = """
import os
import sys
from pathlib import Path
import django
django.setup()
from cs_map_trainer.web.processes import parser_slot
from cs_map_trainer.web.tasks import run_bounded
with parser_slot(Path(sys.argv[1])) as lock:
    if lock is None:
        raise RuntimeError("Parser slot is busy")
    run_bounded(
        [sys.executable, "-c", sys.argv[2], str(os.getpid()), sys.argv[3]],
        os.environ.copy(),
        lock_fd=lock.fileno(),
    )
"""

GUARDED_CHILD = """
import os
import sys
import time
from pathlib import Path
from cs_map_trainer.web.processes import terminate_with_parent
terminate_with_parent(int(sys.argv[1]))
Path(sys.argv[2]).write_text(str(os.getpid()))
time.sleep(30)
"""

STALLED_CHILD = """
import os
import sys
import time
from pathlib import Path
Path(sys.argv[2]).write_text(str(os.getpid()))
time.sleep(30)
"""


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while not predicate():
        if time.monotonic() >= deadline:
            pytest.fail("Process lifecycle condition did not become true")
        time.sleep(0.02)


def alive(process):
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


@pytest.mark.parametrize("guarded", [True, False])
def test_parser_slot_survives_supervisor_sigkill(tmp_path, guarded):
    root = tmp_path / "work"
    marker = tmp_path / "child.pid"
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "web_settings"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    child = None
    with subprocess.Popen(
        [
            sys.executable,
            "-c",
            SUPERVISOR,
            str(root),
            GUARDED_CHILD if guarded else STALLED_CHILD,
            str(marker),
        ],
        env=env,
    ) as supervisor:
        try:
            wait_for(lambda: marker.exists() and marker.stat().st_size > 0)
            child = psutil.Process(int(marker.read_text()))
            with parser_slot(root) as occupied:
                assert occupied is None
            supervisor.kill()
            supervisor.wait(timeout=10)
            if guarded:
                wait_for(lambda: not alive(child))
            else:
                assert alive(child)
                with parser_slot(root) as occupied:
                    assert occupied is None
                child.kill()
                wait_for(lambda: not alive(child))
            with parser_slot(root) as available:
                assert available is not None
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait(timeout=10)
            if child is None and marker.exists() and marker.stat().st_size:
                child = psutil.Process(int(marker.read_text()))
            if child is not None and alive(child):
                child.kill()
                wait_for(lambda: not alive(child))


def test_parser_slot_reusable_without_unlinking_lock_file(tmp_path):
    with parser_slot(tmp_path) as first:
        assert first is not None
        inode = os.fstat(first.fileno()).st_ino
        with parser_slot(tmp_path) as busy:
            assert busy is None
    with parser_slot(tmp_path) as second:
        assert second is not None
        assert os.fstat(second.fileno()).st_ino == inode


@pytest.mark.parametrize("parent_alive", [True, False])
def test_linux_parent_death_guard_checks_the_registration_race(parent_alive):
    libc = Mock()
    libc.prctl.return_value = 0
    with (
        patch("cs_map_trainer.web.processes.sys.platform", "linux"),
        patch("cs_map_trainer.web.processes.ctypes.CDLL", return_value=libc),
        patch("cs_map_trainer.web.processes.os.getppid", return_value=123 if parent_alive else 1),
        patch("cs_map_trainer.web.processes.os.kill") as kill,
    ):
        terminate_with_parent(123)
    libc.prctl.assert_called_once_with(1, signal.SIGKILL, 0, 0, 0)
    if parent_alive:
        kill.assert_not_called()
    else:
        kill.assert_called_once_with(os.getpid(), signal.SIGKILL)


def test_linux_parent_death_guard_fails_explicitly_if_registration_fails():
    libc = Mock()
    libc.prctl.return_value = -1
    with (
        patch("cs_map_trainer.web.processes.sys.platform", "linux"),
        patch("cs_map_trainer.web.processes.ctypes.CDLL", return_value=libc),
        patch("cs_map_trainer.web.processes.ctypes.get_errno", return_value=1),
        pytest.raises(OSError, match="Cannot arm parser parent-death signal"),
    ):
        terminate_with_parent(123)
