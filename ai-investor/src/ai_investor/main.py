"""Point d'entrée de l'application web (localhost uniquement par défaut)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

from ai_investor import DISCLAIMER, __version__
from ai_investor.config import AppConfig, load_config

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
}


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    app = FastAPI(title="AI Investor", version=__version__, description=DISCLAIMER)
    app.state.config = cfg

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "simulation_only": cfg.settings.SIMULATION_ONLY,
            "base_currency": cfg.settings.BASE_CURRENCY,
            "disclaimer": DISCLAIMER,
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
            "<title>AI Investor</title></head><body>"
            "<h1>AI Investor</h1>"
            f"<p><strong>{escape(DISCLAIMER)}</strong></p>"
            "<p>Étape 1 : architecture en place. Le tableau de bord arrivera à l'étape 13.</p>"
            "</body></html>"
        )

    return app


def run() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.settings.HOST, port=cfg.settings.PORT)


if __name__ == "__main__":
    run()
