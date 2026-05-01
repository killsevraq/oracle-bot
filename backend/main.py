"""Point d'entree FastAPI : lance le bot et expose l'API + dashboard statique."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import router as api_router
from backend.bot import get_bot
from backend.config import settings
from backend.telegram_bot import TelegramCommandBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("oracle-bot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = get_bot()
    await bot.setup()
    tg_cmd = TelegramCommandBot(bot)
    await tg_cmd.start()
    auto_start = os.getenv("AUTO_START", "false").lower() == "true"
    if auto_start:
        await bot.start()
    try:
        yield
    finally:
        await tg_cmd.stop()
        await bot.stop("arret du serveur")


def create_app() -> FastAPI:
    app = FastAPI(title="Oracle Bot V2", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/")
        async def root() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> FileResponse:
            target = static_dir / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(static_dir / "index.html")
    else:

        @app.get("/")
        async def root_dev() -> dict[str, str]:
            return {
                "status": "ok",
                "api": "/api",
                "events": "/api/events",
                "note": "Build le frontend avec `npm --prefix frontend run build` pour le servir ici.",
            }

    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
