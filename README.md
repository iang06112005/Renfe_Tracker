# RenfeTracker

Mapa en vivo de los trenes de Renfe (Cercanías, y AVE / Media Distancia / Larga Distancia) y, en otro modo, la red de Metro de Madrid. Un solo proceso FastAPI sirve la API y el frontend ya compilado. El navegador no llama a `gtfsrt.renfe.com` ni al GTFS del metro.

La contraseña es de grupo, no hay cuentas. Se lee de `RENFE_TRACKER_PASSWORD` (no la subas al repositorio). Sin esa variable el proceso no arranca. `/api/health` queda abierto para que Fly pueda comprobar el servicio; `/api/trains` y el mapa piden la cookie de sesión.

El feed de Cercanías incluye también Rodalies. Esos trenes se agrupan por el prefijo de dos cifras del `route_id` y el mapa los nombra por ciudad (10 Madrid, 30 Sevilla, 51 Barcelona, 60 Bilbao…). Rodalies va en naranja y el resto de Cercanías en rojo, salvo Madrid, donde cada línea usa su color público (C4 azul, C5 amarillo y el resto según `route_color`). AVE, AVLO y AVE INT son alta velocidad, en morado. MD, Regional, Avant e Intercity son media distancia. Alvia, Euromed y Tren Celta son larga distancia. Un MD no lleva etiqueta de AVE. Iryo y Ouigo no están en esos ficheros y no se dibujan.

El proceso escucha aunque el GTFS estático tarde o falle; sin ese fichero el mapa sigue en vivo y `GET /api/lines` responde una colección vacía. La ficha del tren puede mostrar línea, recorrido, parada anterior, siguiente, el grupo, el retraso y las horas previstas del feed GTFS-RT de trip updates de Renfe (`trip_updates.json` / `trip_updates_LD.json`, CC BY 4.0, caché 15 s, unidos por `tripId`). Si Renfe no manda previsión para una parada, se omite o se deja el dato estático del GTFS. El interruptor «Detalle del tren» deja solo el número. No hay serie (Civia, 465…) en los datos públicos, así que no se muestra. Debajo de los trenes hay dos capas de vía, finas y en segundo plano. OpenRailwayMap (teselas, directamente en el navegador) dibuja la infraestructura apagada, sin el contraste del estilo original. Las líneas de color salen del GTFS estático de Cercanías (`shapes.txt` en `https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip`): el backend lo convierte a GeoJSON una vez y lo cachea 24 h. Van más finas y más transparentes que los símbolos de los trenes. El zip de larga distancia (`https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip`) no trae `shapes.txt`, así que esas relaciones no se dibujan como corredor de color; siguen viéndose, muy tenues, las vías de OpenRailwayMap. El fondo es el estilo claro Positron de CARTO. Las líneas del GTFS y las estaciones se leen encima; los trenes quedan por encima de todo.

El selector **Metro Madrid** usa el GTFS público del CRTM (líneas, colores y estaciones) y estima la posición de cada tren a partir de los teleindicadores públicos de Metro de Madrid (`serviciosapp.metromadrid.es`): el punto se coloca en el tramo anterior a la estación de llegada según los minutos anunciados. No es GPS. La atribución es «Powered by MITRAMS».

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
