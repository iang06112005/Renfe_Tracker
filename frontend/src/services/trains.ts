import type { FeatureCollection, FeedType, ServiceKind, TrainFeature, TrainProperties } from "../types/trains"

export class AuthError extends Error {
  constructor() {
    super("No autorizado")
    this.name = "AuthError"
  }
}

export async function fetchTrains(feed: FeedType, signal?: AbortSignal): Promise<FeatureCollection> {
  const response = await fetch(`/api/trains?type=${encodeURIComponent(feed)}`, {
    signal,
    credentials: "same-origin",
  })
  if (response.status === 401) throw new AuthError()
  if (!response.ok) throw new Error(await readDetail(response))
  const body: unknown = await response.json()
  const collection = parseCollection(body)
  if (!collection) throw new Error("Respuesta de trenes no válida")
  return collection
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (isRecord(body) && typeof body.detail === "string") return body.detail
  } catch {
    return "No se han podido cargar los trenes"
  }
  return "No se han podido cargar los trenes"
}

function parseCollection(value: unknown): FeatureCollection | null {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) return null
  const features: TrainFeature[] = []
  for (const item of value.features) {
    const feature = parseFeature(item)
    if (!feature) return null
    features.push(feature)
  }
  return { type: "FeatureCollection", features }
}

function parseFeature(value: unknown): TrainFeature | null {
  if (!isRecord(value) || value.type !== "Feature" || !isRecord(value.geometry) || !isRecord(value.properties)) {
    return null
  }
  const coordinates = value.geometry.coordinates
  if (value.geometry.type !== "Point" || !Array.isArray(coordinates) || coordinates.length < 2) return null
  const [lon, lat] = coordinates
  if (typeof lon !== "number" || typeof lat !== "number") return null
  const service = value.properties.service
  if (service !== "cercanias" && service !== "ld" && service !== "metro") return null
  if (typeof value.properties.id !== "string") return null
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: readProperties(value.properties, value.properties.id, service),
  }
}

function readProperties(record: Record<string, unknown>, id: string, service: ServiceKind): TrainProperties {
  return {
    id,
    vehicleId: readString(record.vehicleId),
    label: readString(record.label),
    line: readString(record.line),
    platform: readString(record.platform),
    tripId: readString(record.tripId),
    stopId: readString(record.stopId),
    status: readString(record.status),
    timestamp: typeof record.timestamp === "number" ? record.timestamp : null,
    service,
    product: readString(record.product),
    bucket: readString(record.bucket),
    bucketLabel: readString(record.bucketLabel),
    bucketColor: readString(record.bucketColor),
    nucleus: readString(record.nucleus),
    nucleusLabel: readString(record.nucleusLabel),
    nucleusColor: readString(record.nucleusColor),
    groupColor: readString(record.groupColor),
    route: readString(record.route),
    previousStop: readString(record.previousStop),
    nextStop: readString(record.nextStop),
    currentStop: readString(record.currentStop),
    delaySeconds: typeof record.delaySeconds === "number" ? record.delaySeconds : null,
    delayLabel: readString(record.delayLabel),
    predictionsLabel: readString(record.predictionsLabel),
  }
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object"
}
