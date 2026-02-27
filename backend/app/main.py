import os
import sys
from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes.health import router as health_router
from app.api.routes.chat import router as chat_router

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(chat_router)

    return app

app = create_app()