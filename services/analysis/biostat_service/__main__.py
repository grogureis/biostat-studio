"""PyInstaller entry point for the local BioStat Studio analysis service."""

from __future__ import annotations

import argparse
import os
import sys

from biostat_service.app import create_app, main as serve


def self_test() -> int:
    """Verify bundled scientific dependencies without opening a network listener."""
    os.environ.setdefault("BIOSTAT_SESSION_TOKEN", "packaged-self-test-token")
    import docx  # noqa: F401
    import fastapi  # noqa: F401
    import matplotlib  # noqa: F401
    import numpy  # noqa: F401
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import scipy  # noqa: F401
    import statsmodels  # noqa: F401
    import uvicorn  # noqa: F401

    app = create_app()
    if not any(getattr(route, "path", None) == "/v1/session" for route in app.routes):
        raise RuntimeError("The bundled analysis service is incomplete")
    print("biostat-service self-test ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BioStat Studio local analysis service")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    serve(["--port", str(args.port)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
