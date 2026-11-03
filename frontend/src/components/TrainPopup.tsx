import { useEffect, useState } from "react"
import type { Map as MapLibreMap } from "maplibre-gl"

import type { TrainFeature } from "../types/trains"

interface TrainPopupProps {
  map: MapLibreMap | null
  train: TrainFeature | null
  detailed: boolean
  onClose: () => void
}

const STATUS_LABEL: Record<string, string> = {
  IN_TRANSIT_TO: "En tránsito",
  STOPPED_AT: "Detenido",
  INCOMING_AT: "Llegando",
}

export function TrainPopup({ map, train, detailed, onClose }: TrainPopupProps) {
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
  const placement = placePopup(point.y, detailed)
  const half = Math.min(140, window.innerWidth / 2 - 16)
  const left = Math.min(window.innerWidth - half - 12, Math.max(half + 12, point.x))

  return (
    <div
      className="popup"
      role="dialog"
      aria-label={`Tren ${title}`}
      style={{
        left,
        top: placement.top,
        maxHeight: placement.maxHeight,
        overflow: placement.maxHeight ? "auto" : undefined,
        transform: placement.below ? "translate(-50%, 16px)" : "translate(-50%, calc(-100% - 14px))",
      }}
    >
      <button type="button" className="popup-close" onClick={onClose} aria-label="Cerrar">
        ×
      </button>
      {detailed && train.properties.bucketLabel ? (
        <p
          className="popup-kicker"
          style={{ color: train.properties.nucleusColor ?? train.properties.bucketColor ?? undefined }}
        >
          {train.properties.nucleusLabel
            ? `${train.properties.bucketLabel} · ${train.properties.nucleusLabel}`
            : train.properties.bucketLabel}
        </p>
      ) : null}
      <h2>{title}</h2>
      {detailed ? <Detail properties={train.properties} status={status} /> : null}
    </div>
  )
}

function Detail({ properties, status }: { properties: TrainFeature["properties"]; status: string }) {
  const rows = [
    ["Producto", properties.product && properties.product !== properties.line ? properties.product : null],
    ["Núcleo", nucleusText(properties.nucleus, properties.nucleusLabel)],
    ["Recorrido", cleanText(properties.route)],
    ["Retraso", properties.delayLabel],
    ["Anterior", cleanStopField(properties.previousStop)],
    ["En parada", cleanStopField(properties.currentStop)],
    ["Siguiente", cleanStopField(properties.nextStop)],
    ["Tren", properties.vehicleId],
    ["Andén", properties.platform],
    ["Estado", status === "Sin estado" ? null : status],
    ["Posición", formatTimestamp(properties.timestamp)],
    ["Horarios", properties.predictionsLabel],
  ].filter((row): row is [string, string] => typeof row[1] === "string" && row[1] !== "—")
  if (rows.length === 0) return null
  return (
    <dl>
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function placePopup(y: number, detailed: boolean): { top: number; below: boolean; maxHeight?: number } {
  const narrow = window.innerWidth <= 720
  if (!narrow) return { top: y, below: y < (detailed ? 320 : 160) }
  const mapBottom = window.innerHeight * 0.52
  const top = Math.min(Math.max(y, 24), mapBottom - 16)
  const above = top - 12
  const below = mapBottom - top - 12
  const placeBelow = above < 180 && below > above
  return { top, below: placeBelow, maxHeight: Math.max(96, (placeBelow ? below : above) - 4) }
}

function nucleusText(code: string | null, label: string | null): string | null {
  if (label && code) return `${code} · ${label}`
  return label ?? code
}

function cleanStopField(value: string | null): string | null {
  if (!value) return null
  const text = value.trim()
  if (text.length < 2) return null
  const separator = " · "
  if (!text.includes(separator)) return looksTruncated(text) ? null : text
  const index = text.lastIndexOf(separator)
  const name = text.slice(0, index).trim()
  const clock = text.slice(index + separator.length).trim()
  if (looksTruncated(name)) return null
  if (!/^\d{2}:\d{2}$/.test(clock)) return name.length >= 2 ? name : null
  return `${name}${separator}${clock}`
}

function cleanText(value: string | null): string | null {
  if (!value) return null
  const text = value.trim()
  return text.length >= 2 && !looksTruncated(text) ? text : null
}

function looksTruncated(value: string): boolean {
  if (/\s[A-Za-zÁÉÍÓÚÜáéíóúü]$/.test(value)) return true
  if (/[-\/–]\s*$/.test(value)) return true
  return false
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
