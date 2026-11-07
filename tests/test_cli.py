import subprocess
import sys


def test_version():
    r = subprocess.run(
        [sys.executable, "-m", "autoevalpsi.cli", "--version"], capture_output=True, text=True, check=False
    )
    assert r.returncode == 0
    assert r.stdout.startswith("autoevalpsi ")
