import pytest
import subprocess
import signal
import time
from os.path import join

from pathlib import Path
cwd = Path(__file__).parents[0]


def test_quick_terminate_on_sigterm():
    ref_time = time.time()
    proc = subprocess.Popen(["python", join(cwd, "blank_env_server.py")])

    proc.send_signal(signal.SIGTERM)

    status = proc.wait()

    assert status == -signal.SIGTERM
    assert time.time() - ref_time < 2.0
