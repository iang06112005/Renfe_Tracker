export type FeedType = "cercanias" | "ld" | "all"
export type ServiceKind = "cercanias" | "ld"

export interface TrainProperties {
  id: string
  vehicleId: string | null
  label: string | null
  line: string | null
  platform: string | null
  tripId: string | null
  stopId: string | null
  status: string | null
  timestamp: number | null
  service: ServiceKind
  product: string | null
  bucket: string | null
  bucketLabel: string | null
  bucketColor: string | null
  nucleus: string | null
  nucleusLabel: string | null
  nucleusColor: string | null
  groupColor: string | null
  route: string | null
  previousStop: string | null
  nextStop: string | null
  currentStop: string | null
}

export interface TrainFeature {
  type: "Feature"
  geometry: {
    type: "Point"
    coordinates: [number, number]
  }
  properties: TrainProperties
}

export interface FeatureCollection {
  type: "FeatureCollection"
  features: TrainFeature[]
}

export const SERVICE_LABEL: Record<ServiceKind, string> = {
  cercanias: "Cercanías",
  ld: "Alta, media y larga",
}

export const EMPTY_COLLECTION: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
}
