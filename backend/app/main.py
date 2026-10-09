from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .api import router
from .database import Base, build_engine, build_session_factory
from .errors import BusinessError
from .seed import seed_demo_data


def default_database_url() -> str:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'demo.db').as_posix()}"


def create_app(database_url: str | None = None, *, seed: bool = True) -> FastAPI:
    app = FastAPI(
        title="午点通 · 资阳校园集运 Demo API",
        version="0.1.0",
        description=(
            "仅供本地业务演示。X-Demo-Role 不是正式认证；所有商家、订单、金额、交付点和退款均为虚构测试数据。"
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    url = database_url or os.getenv("DATABASE_URL") or default_database_url()
    engine = build_engine(url)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    Base.metadata.create_all(engine)
    if seed:
        with app.state.session_factory.begin() as db:
            seed_demo_data(db)

    @app.exception_handler(BusinessError)
    async def business_error_handler(_request: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/", include_in_schema=False)
    async def docs_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    app.include_router(router)
    return app


app = create_app()
