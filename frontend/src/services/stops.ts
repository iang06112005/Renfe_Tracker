import type { StationCollection, StationFeature } from "../types/stops"
import { AuthError } from "./trains"

export async function fetchStations(feed: string, signal?: AbortSignal): Promise<StationCollection> {
  const response = await fetch(`/api/stops?type=${encodeURIComponent(feed)}`, {
    signal,
    credentials: "same-origin",
  })
  if (response.status === 401) throw new AuthError()
  if (!response.ok) throw new Error("No se han podido cargar las estaciones")
  const body: unknown = await response.json()
  const collection = parseStations(body)
  if (!collection) throw new Error("Respuesta de estaciones no válida")
  return collection
}

function parseStations(value: unknown): StationCollection | null {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) return null
  const features = value.features.flatMap((item) => {
    const feature = parseStation(item)
    return feature ? [feature] : []
  })
  return { type: "FeatureCollection", features }
}

function parseStation(value: unknown): StationFeature | null {
  if (!isRecord(value) || value.type !== "Feature" || !isRecord(value.geometry) || !isRecord(value.properties)) {
    return null
  }
  const coordinates = value.geometry.coordinates
  if (value.geometry.type !== "Point" || !Array.isArray(coordinates) || coordinates.length < 2) return null
  const [lon, lat] = coordinates
  if (typeof lon !== "number" || typeof lat !== "number") return null
  const name = value.properties.name
  const stopId = value.properties.stopId
  const service = value.properties.service
  if (typeof name !== "string" || !name || typeof stopId !== "string" || typeof service !== "string") return null
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { name, service, stopId },
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object"
}
