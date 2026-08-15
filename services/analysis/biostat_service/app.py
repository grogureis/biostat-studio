"""FastAPI assembly for the local BioStat analysis service."""

import argparse
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI
from uvicorn import Config, Server

from .security import require_loopback, require_session


API_VERSION = 1


class ReadinessServer(Server):
    """Uvicorn server that reports its ephemeral loopback port after binding."""

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            socket = self.servers[0].sockets[0]
            port = socket.getsockname()[1]
            print(json.dumps({"port": port, "api": API_VERSION}), flush=True)


def create_app() -> FastAPI:
    """Create the local-only API without exposing interactive documentation."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health", dependencies=[Depends(require_loopback)])
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "biostat-analysis", "api": API_VERSION}

    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_session)])

    @v1.get("/session")
    def session() -> dict[str, int]:
        return {"api": API_VERSION}

    app.include_router(v1)
    return app


def main(argv: Optional[List[str]] = None) -> None:
    """Run the local service and print its versioned readiness record."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    config = Config(create_app(), host="127.0.0.1", port=args.port, access_log=False)
    ReadinessServer(config).run()


if __name__ == "__main__":
    main()
