import subprocess
import sys


def test_version():
    r = subprocess.run(
        [sys.executable, "-m", "autoevalpsi.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout.startswith("autoevalpsi ")


def test_abrir_esta_en_la_ayuda():
    r = subprocess.run(
        [sys.executable, "-m", "autoevalpsi.cli", "abrir", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "--puerto" in r.stdout
