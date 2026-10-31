import { useEffect, useState } from "react"
import type { Map as MapLibreMap } from "maplibre-gl"

import { SERVICE_LABEL, type TrainFeature } from "../types/trains"

interface TrainPopupProps {
  map: MapLibreMap | null
  train: TrainFeature | null
  onClose: () => void
}

const STATUS_LABEL: Record<string, string> = {
  IN_TRANSIT_TO: "En tránsito",
  STOPPED_AT: "Detenido",
  INCOMING_AT: "Llegando",
}

export function TrainPopup({ map, train, onClose }: TrainPopupProps) {
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null)
  const lng = train?.geometry.coordinates[0]
  const lat = train?.geometry.coordinates[1]

  useEffect(() => {
    if (!map || lng === undefined || lat === undefined) return
    const update = () => {
      const projected = map.project([lng, lat])
      setPoint({ x: projected.x, y: projected.y })
    }
    update()
    map.on("move", update)
    map.on("resize", update)
    return () => {
      map.off("move", update)
      map.off("resize", update)
    }
  }, [map, lng, lat])

  useEffect(() => {
    if (!train) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [train, onClose])

  if (!train || !point) return null

  const title = train.properties.line ?? train.properties.vehicleId ?? train.properties.id
  const status = train.properties.status ? (STATUS_LABEL[train.properties.status] ?? train.properties.status) : "Sin estado"
  const flip = point.y < 180
  const half = Math.min(120, window.innerWidth / 2 - 16)
  const left = Math.min(window.innerWidth - half - 12, Math.max(half + 12, point.x))

  return (
    <div
      className="popup"
      role="dialog"
      aria-label={`Tren ${title}`}
      style={{
        left,
        top: point.y,
        transform: flip ? "translate(-50%, 16px)" : "translate(-50%, calc(-100% - 14px))",
      }}
    >
      <button type="button" className="popup-close" onClick={onClose} aria-label="Cerrar">
        ×
      </button>
      <p className={`popup-kicker ${train.properties.service}`}>{SERVICE_LABEL[train.properties.service]}</p>
      <h2>{title}</h2>
      <dl>
        <div>
          <dt>Tren</dt>
          <dd>{train.properties.vehicleId ?? "—"}</dd>
        </div>
        <div>
          <dt>Andén</dt>
          <dd>{train.properties.platform ?? "—"}</dd>
        </div>
        <div>
          <dt>Estado</dt>
          <dd>{status}</dd>
        </div>
        <div>
          <dt>Parada</dt>
          <dd>{train.properties.stopId ?? "—"}</dd>
        </div>
        <div>
          <dt>Hora</dt>
          <dd>{formatTimestamp(train.properties.timestamp)}</dd>
        </div>
      </dl>
    </div>
  )
}

function formatTimestamp(timestamp: number | null): string {
  if (timestamp === null) return "—"
  return new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Europe/Madrid",
  }).format(new Date(timestamp * 1000))
}
