"""FastAPI application setup for the local CrateBox API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .collection import collection_mcp, router as collection_router
from .playlists import router as playlists_router
from .artwork import router as artwork_router
from .streaming import router as streaming_router
from .rekordbox_playlists import router as rekordbox_playlists_router

@asynccontextmanager
async def lifespan(_app):
    try:
        yield
    finally:
        await collection_mcp.close()

app = FastAPI(title="CrateBox playlist API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.include_router(collection_router)
app.include_router(playlists_router)
app.include_router(artwork_router)
app.include_router(streaming_router)
app.include_router(rekordbox_playlists_router)
