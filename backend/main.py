import asyncio
import hashlib
import hmac
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response

from config import (
    COOKIE_MAX_AGE_SECONDS,
    COOKIE_NAME,
    CORS_ORIGINS,
    DIST_DIR,
    PUBLIC_API_PATHS,
    SESSION_MESSAGE,
    require_password,
)
from gtfs_shapes import ShapeLoadError, ShapeStore
from parser import parse_feed
from renfe_client import RenfeClient, RenfeUnavailable
from schemas import (
    FeatureCollection,
    FeedType,
    HealthResponse,
    LoginRequest,
    ServiceKind,
    SessionResponse,
    TrainFeature,
)

logger = logging.getLogger("renfe_tracker")


class GeoJSONResponse(JSONResponse):
    media_type = "application/geo+json"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    require_password()
    client = RenfeClient()
    await client.open()
    shapes = ShapeStore()
    app.state.renfe = client
    app.state.shapes = shapes
    app.state.shapes_task = asyncio.create_task(shapes.ensure_loaded())
    try:
        yield
    finally:
        app.state.shapes_task.cancel()
        await client.aclose()


app = FastAPI(title="RenfeTracker", lifespan=lifespan)


def _session_token(password: str) -> str:
    return hmac.new(password.encode(), SESSION_MESSAGE, hashlib.sha256).hexdigest()


def _password_matches(provided: str) -> bool:
    expected = require_password()
    return hmac.compare_digest(
        hashlib.sha256(provided.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def _authorized(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return False
    return hmac.compare_digest(token, _session_token(require_password()))


def _secure_cookie(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto") or request.headers.get("fly-forwarded-proto")
    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


@app.middleware("http")
async def gate_api(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS and not _authorized(request):
        return JSONResponse(
            {"detail": "No autorizado"},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    response = await call_next(request)
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.get("/api/session", response_model=SessionResponse)
async def session(request: Request) -> SessionResponse:
    return SessionResponse(authenticated=_authorized(request))


@app.post("/api/login", response_model=SessionResponse)
async def login(body: LoginRequest, request: Request) -> JSONResponse:
    if not _password_matches(body.password):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        COOKIE_NAME,
        _session_token(require_password()),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/logout", response_model=SessionResponse)
async def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    return response


@app.get(
    "/api/trains",
    response_model=FeatureCollection,
    response_model_by_alias=True,
    response_class=GeoJSONResponse,
)
async def trains(
    request: Request,
    feed: FeedType = Query(default="all", alias="type"),
) -> FeatureCollection:
    client: RenfeClient = request.app.state.renfe
    return await _load_trains(client, feed)


@app.get("/api/lines", response_class=GeoJSONResponse)
async def lines(
    request: Request,
    feed: FeedType = Query(default="all", alias="type"),
) -> Response:
    await _wait_for_shapes(request)
    store: ShapeStore = request.app.state.shapes
    return Response(content=store.body(feed), media_type="application/geo+json")


async def _wait_for_shapes(request: Request) -> None:
    task: asyncio.Task[None] = request.app.state.shapes_task
    if task.done() and not task.cancelled() and task.exception() is not None:
        task = asyncio.create_task(request.app.state.shapes.ensure_loaded())
        request.app.state.shapes_task = task
    try:
        await task
    except (ShapeLoadError, OSError) as exc:
        raise HTTPException(status_code=502, detail="No se han podido cargar los trazados") from exc


async def _load_trains(client: RenfeClient, feed: FeedType) -> FeatureCollection:
    kinds: tuple[ServiceKind, ...] = ("cercanias", "ld") if feed == "all" else (feed,)
    parts = await asyncio.gather(*(_features(client, kind) for kind in kinds))
    if all(part is None for part in parts):
        raise HTTPException(status_code=502, detail="Renfe no responde")
    features = [feature for part in parts if part is not None for feature in part]
    return FeatureCollection(features=features)


async def _features(client: RenfeClient, kind: ServiceKind) -> list[TrainFeature] | None:
    try:
        payload = await client.fetch_feed(kind)
    except RenfeUnavailable:
        logger.warning("Sin datos de Renfe para %s", kind)
        return None
    return parse_feed(payload, kind).features


def _safe_asset(full_path: str) -> Path | None:
    root = DIST_DIR.resolve()
    candidate = (root / full_path).resolve()
    if not candidate.is_file() or root not in candidate.parents:
        return None
    return candidate


def register_frontend() -> None:
    index = DIST_DIR / "index.html"
    if not index.is_file():
        logger.info("Frontend sin compilar en %s; solo se sirve la API", DIST_DIR)
        return

    @app.get("/", include_in_schema=False)
    async def index_page() -> FileResponse:
        response = FileResponse(index)
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str) -> FileResponse:
        asset = _safe_asset(full_path)
        target = asset or index
        response = FileResponse(target)
        hashed = asset is not None and "assets" in asset.parts
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if hashed else "no-cache"
        return response


register_frontend()
