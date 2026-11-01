# RenfeTracker

Mapa en vivo de los trenes de Renfe (Cercanías, y AVE / Media Distancia / Larga Distancia) a partir de los feeds públicos GTFS-RT. Un solo proceso FastAPI sirve la API y el frontend ya compilado. El navegador no llama a `gtfsrt.renfe.com`.

La contraseña es de grupo, no hay cuentas. Se lee de `RENFE_TRACKER_PASSWORD` (no la subas al repositorio). Sin esa variable el proceso no arranca. `/api/health` queda abierto para que Fly pueda comprobar el servicio; `/api/trains` y el mapa piden la cookie de sesión.

El feed de Cercanías incluye también Rodalies. AVE, Media Distancia y Larga Distancia llegan juntos en el feed de larga distancia: Renfe no separa ahí el producto comercial, así que el mapa tampoco lo inventa.

Debajo de los trenes hay dos capas de vía, finas y en segundo plano. OpenRailwayMap (teselas, directamente en el navegador) dibuja la infraestructura apagada, sin el contraste del estilo original. Las líneas de color salen del GTFS estático de Cercanías (`shapes.txt` en `https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip`): el backend lo convierte a GeoJSON una vez y lo cachea 24 h. Van más finas y más transparentes que los símbolos de los trenes. El zip de larga distancia (`https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip`) no trae `shapes.txt`, así que esas relaciones no se dibujan como corredor de color; siguen viéndose, muy tenues, las vías de OpenRailwayMap.

## Arranque en local (Windows + conda)

Entorno: Miniforge, conda `renfe_tracker`. No instales las dependencias en el Python del sistema.

```powershell
copy .env.example .env
# Edita .env y define RENFE_TRACKER_PASSWORD. El proceso la carga al arrancar.

conda run -n renfe_tracker python -m pip install -r requirements.txt -r requirements-dev.txt
conda run -n renfe_tracker python -m pytest
# pytest llama a los feeds reales de Renfe: hace falta red.

cd frontend
npm install
npm run build
cd ..

conda run -n renfe_tracker --no-capture-output python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000 e introduce la contraseña del grupo.

Para iterar la interfaz, deja uvicorn en marcha y en otra terminal:

```powershell
cd frontend
npm run dev
```

Vite (http://localhost:5173) proxifica `/api` al backend.

Comprobar la API:

```powershell
curl.exe http://127.0.0.1:8000/api/health
curl.exe -c cookies.txt -H "Content-Type: application/json" -d "{\"password\":\"tu-contraseña\"}" http://127.0.0.1:8000/api/login
curl.exe -b cookies.txt "http://127.0.0.1:8000/api/trains?type=all"
```

`type` admite `cercanias`, `ld` o `all`. El backend guarda cada feed 15 segundos. El mapa pide datos cada 5 segundos.

## Despliegue en Fly.io

La URL pública es `https://<app>.fly.dev` (HTTPS de Fly, sin dominio propio). La región es `cdg` (París): Madrid ya no admite máquinas nuevas. Una sola máquina de 256 MB; la caché vive en memoria, así que no escales a más de una. Si no hay visitas, la máquina puede dormirse y la primera petición la despierta.

Hace falta [flyctl](https://fly.io/docs/flyctl/install/). Desde la raíz del repo:

```powershell
fly auth login
fly apps create renfe-tracker
fly secrets set RENFE_TRACKER_PASSWORD="tu-contraseña-de-grupo" --app renfe-tracker
fly deploy --ha=false
fly open
```

Si `renfe-tracker` ya existe, cambia `app` en `fly.toml` por otro nombre, créalo con `fly apps create <nombre>` y usa ese nombre en `fly secrets` y en la URL `https://<nombre>.fly.dev`.

La comprobación de salud de Fly llama a `GET /api/health` y no necesita contraseña.
