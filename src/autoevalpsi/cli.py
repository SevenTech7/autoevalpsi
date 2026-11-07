"""Línea de comandos de AutoEvalPsi."""

import argparse
from importlib.metadata import PackageNotFoundError, version


def _version() -> str:
    try:
        return version("autoevalpsi")
    except PackageNotFoundError:
        return "0.0.0+local"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autoevalpsi")
    parser.add_argument("--version", action="version", version=f"autoevalpsi {_version()}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
