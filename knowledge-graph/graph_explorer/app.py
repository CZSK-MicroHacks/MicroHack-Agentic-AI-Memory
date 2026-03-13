from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .service import (
    build_neighborhood_graph,
    close_pool,
    find_path_graph,
    get_examples,
    get_node_details,
    search_nodes,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Knowledge Graph Explorer")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_pool()


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/examples")
async def examples() -> dict:
    try:
        return await get_examples()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/search")
async def search(
    query: str = Query(..., min_length=1),
    limit: int = Query(12, ge=1, le=25),
) -> dict:
    try:
        return {"query": query, "results": await search_nodes(query, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/node")
async def node(
    name: str = Query(..., min_length=1),
    depth: int = Query(1, ge=1, le=3),
    relationship_type: str | None = Query(default=None),
) -> dict:
    try:
        return await build_neighborhood_graph(
            name,
            relationship_type=relationship_type,
            depth=depth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/node-details")
async def node_details(
    name: str = Query(..., min_length=1),
) -> dict:
    try:
        details = await get_node_details(name)
        if details is None:
            raise HTTPException(status_code=404, detail=f"Node '{name}' was not found.")
        return details
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/path")
async def path(
    source: str = Query(..., min_length=1),
    target: str = Query(..., min_length=1),
    max_depth: int = Query(4, ge=1, le=5),
    relationship_type: str | None = Query(default=None),
) -> dict:
    try:
        return await find_path_graph(
            source,
            target,
            relationship_type=relationship_type,
            max_depth=max_depth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
