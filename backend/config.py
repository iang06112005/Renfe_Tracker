import os
from pathlib import Path

CERCANIAS_URL = "https://gtfsrt.renfe.com/vehicle_positions.json"
LD_URL = "https://gtfsrt.renfe.com/vehicle_positions_LD.json"
CERCANIAS_GTFS_URL = "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip"
LD_GTFS_URL = "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip"
CACHE_TTL_SECONDS = 15
GTFS_CACHE_SECONDS = 24 * 60 * 60
HTTP_TIMEOUT_SECONDS = 10.0
USER_AGENT = "RenfeTracker/1.0 (+https://github.com/iang06112005/Renfe_Tracker)"
PASSWORD_ENV = "RENFE_TRACKER_PASSWORD"
COOKIE_NAME = "renfe_session"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
SESSION_MESSAGE = b"renfe-tracker-v1"
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "frontend" / "dist"
GTFS_CACHE_DIR = ROOT_DIR / "data" / "gtfs"
PUBLIC_API_PATHS = frozenset({"/api/health", "/api/login", "/api/session", "/api/logout"})


def load_dotenv_file() -> None:
    path = ROOT_DIR / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_password() -> str:
    load_dotenv_file()
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        raise RuntimeError("Falta la variable de entorno RENFE_TRACKER_PASSWORD.")
    return password


load_dotenv_file()
