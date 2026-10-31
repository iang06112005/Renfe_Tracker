# [AGENTS.md](http://AGENTS.md) — Directrices del Proyecto RenfeTracker

## 1. Descripción del Proyecto

Aplicación web full-stack para consultar en tiempo real la posición GPS de los trenes de Renfe (Cercanías, Media Distancia, Larga Distancia y AVE) consumiendo sus feeds abiertos GTFS-RT y visualizándolos sobre un mapa interactivo de alto rendimiento.

## 2. Entorno de Desarrollo y Ejecución (CRÍTICO)

- **Sistema Operativo:** Windows 11 (PowerShell).

- **Entorno Python (Backend):** Gestionado mediante **Miniforge / Conda**.

  - Nombre del entorno: `renfe_tracker`

  - Ruta del ejecutable: `C:\Users\ian.gallo\AppData\Local\miniforge3\envs\renfe_tracker\python.exe`

  - **Regla para el Agente:** Antes de ejecutar cualquier comando de Python, test o servidor en terminal, asegúrate de usar `conda run -n renfe_tracker <comando>` o verifica que el entorno `(renfe_tracker)` esté activo. NUNCA crees un `.venv` local ni instales paquetes en el Python global del sistema.

- **Entorno Frontend:** Node.js + Vite + TypeScript en el directorio `/frontend`.

## 3. Principios de Ingeniería y Programación Modular

1. **Separación de Responsabilidades (SoC):**

   - Prohibido escribir archivos monolíticos. Cada módulo debe tener una única responsabilidad clara.

   - En el **Backend `/backend`)**:

     - `config.py`: Constantes, URLs de Renfe, tiempos de TTL de caché y configuración CORS.

     - `schemas.py`: Modelos Pydantic estrictos para validar la entrada GTFS-RT y la salida GeoJSON.

     - `renfe_client.py`: Cliente asíncrono `httpx`) con gestión de errores de red y caché en memoria (TTL = 15s).

     - `parser.py`: Lógica pura de transformación de entidades GTFS-RT a GeoJSON `FeatureCollection` y extracción mediante expresiones regulares (línea comercial y andén).

     - `main.py`: Únicamente definición de la instancia FastAPI, middlewares y rutas `GET /api/trains`, `GET /api/health`).

   - En el **Frontend `/frontend/src`)**:

     - `types/`: Interfaces TypeScript estrictas (prohibido usar `any`).

     - `services/`: Lógica de fetching hacia el backend local.

     - `hooks/`: Custom hooks para polling `useTrainsData`) e interpolación cinemática de posiciones `useTrainInterpolation`).

     - `components/`: Componentes de UI desacoplados del motor del mapa `MapView`, `TrainPopup`, `FilterSidebar`).

2. **Calidad y Robustez:**

   - Tipado estricto `type hints` en Python y TypeScript estricto).

   - Manejo defensivo de datos: los feeds GTFS-RT de Renfe a veces omiten campos como `stopId`, `position` o `label` en ciertos trenes; el parser debe ignorar o gestionar con `Optional` las entidades incompletas sin tirar el servidor abajo.

   - Verificar cada fase ejecutando pruebas reales antes de dar por cerrada una tarea.

## 4. Especificación Técnica de los Datos de Renfe (GTFS-RT)

Renfe publica JSONs abiertos sin API Key (se actualizan cada 15-30 segundos):

- **Cercanías:** `https://gtfsrt.renfe.com/vehicle_positions.json`

- **AVE / Larga y Media Distancia:** `https://gtfsrt.renfe.com/vehicle_positions_LD.json`

Estructura real de un elemento en `entity[]`:

```json

{

  "id": "VP_C1_23514",

  "vehicle": {

    "trip": { "tripId": "23514..." },

    "position": { "latitude": 40.4067, "longitude": -3.6908 },

    "currentStatus": "IN_TRANSIT_TO",

    "timestamp": 1730372000,

    "stopId": "18000",

    "vehicle": { "id": "23514", "label": "C1-23514-PLATF.(2)" }

  }

}

---
description: Reglas de arquitectura y datos para el visualizador GPS de Renfe
globs: ["**/*"]
alwaysApply: true
---

# Contexto del Proyecto: Renfe Live GPS Tracker

## 1. Fuente de Datos (Renfe Open Data GTFS-RT)
Renfe expone JSONs públicos sin autenticación:
- Cercanías: `https://gtfsrt.renfe.com/vehicle_positions.json`
- AVE / Larga / Media Distancia: `https://gtfsrt.renfe.com/vehicle_positions_LD.json`

Estructura de cada elemento dentro de `entity[]` en el JSON de Renfe:
`json
{
  "id": "VP_C1_23514",
  "vehicle": {
    "trip": { "tripId": "23514..." },
    "position": { "latitude": 40.4067, "longitude": -3.6908 },
    "currentStatus": "IN_TRANSIT_TO",
    "timestamp": 1730372000,
    "stopId": "18000",
    "vehicle": { "id": "23514", "label": "C1-23514-PLATF.(2)" }
  }
}
`

## 2. Reglas de Arquitectura
- **PROHIBIDO hacer fetch a `gtfsrt.renfe.com` desde el frontend** (falla por CORS y expone al cliente).
- **Backend (FastAPI en `/backend`):**
  - Debe unificar o servir por parámetro (`?type=cercanias|ld|all`) los datos transformados a formato **GeoJSON (`FeatureCollection`)** para pintarlos directamente en el mapa.
  - **Caché obligatoria:** Guardar en memoria la respuesta durante 15 segundos. Aunque el frontend haga polling cada 5s, el backend solo consulta a Renfe máximo 1 vez cada 15s.
  - Extraer la línea comercial (ej. `C1`, `C5`, `AVE`) y el andén parseando `vehicle.vehicle.label` con regex (`r"PLATF\.\((\w+)\)"`).
- **Frontend (Vite + React + TypeScript + MapLibre GL JS en `/frontend`):**
  - Usar un `GeoJSONSource` en MapLibre para actualizar las posiciones de golpe sin recrear marcadores DOM individuales (rendimiento fluido con +300 trenes simultáneos).
  - Mapa base oscuro (`https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`).

## 3. Estilo de Código
- Tipado estricto en Python (Pydantic) y TypeScript (interfaces claras, nada de `any`).
- Código modular: separar cliente HTTP/caché (`renfe_client.py`) de las rutas (`main.py`).