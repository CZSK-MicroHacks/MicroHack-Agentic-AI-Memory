from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("GRAPH_EXPLORER_HOST", "127.0.0.1")
    port = int(os.getenv("GRAPH_EXPLORER_PORT", "8091"))
    uvicorn.run("graph_explorer.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
