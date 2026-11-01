import type { RouteLineCollection, RouteLineFeature } from "../types/lines"
import type { FeedType } from "../types/trains"
import { AuthError } from "./trains"

export async function fetchRouteLines(feed: FeedType, signal?: AbortSignal): Promise<RouteLineCollection> {
  const response = await fetch(`/api/lines?type=${encodeURIComponent(feed)}`, {
    signal,
    credentials: "same-origin",
  })
  if (response.status === 401) throw new AuthError()
  if (!response.ok) throw new Error("No se han podido cargar los trazados")
  const body: unknown = await response.json()
  const collection = parseLines(body)
  if (!collection) throw new Error("Respuesta de trazados no válida")
  return collection
}

function parseLines(value: unknown): RouteLineCollection | null {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) return null
  const features = value.features.flatMap((item) => {
    const feature = parseFeature(item)
    return feature ? [feature] : []
  })
  return { type: "FeatureCollection", features }
}

function parseFeature(value: unknown): RouteLineFeature | null {
  if (!isRecord(value) || value.type !== "Feature" || !isRecord(value.geometry) || !isRecord(value.properties)) {
    return null
  }
  if (value.geometry.type !== "LineString" || !Array.isArray(value.geometry.coordinates)) return null
  const coordinates = value.geometry.coordinates.flatMap(readPoint)
  if (coordinates.length < 2 || coordinates.length !== value.geometry.coordinates.length) return null
  const service = value.properties.service
  if (service !== "cercanias" && service !== "ld") return null
  if (typeof value.properties.shapeId !== "string" || typeof value.properties.color !== "string") return null
  const line = value.properties.line
  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates },
    properties: {
      line: typeof line === "string" && line ? line : null,
      color: value.properties.color,
      service,
      shapeId: value.properties.shapeId,
    },
  }
}

function readPoint(value: unknown): [number, number][] {
  if (!Array.isArray(value) || value.length < 2) return []
  const [lon, lat] = value
  if (typeof lon !== "number" || typeof lat !== "number") return []
  return [[lon, lat]]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object"
}
