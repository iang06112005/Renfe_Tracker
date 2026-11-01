export interface StationFeature {
  type: "Feature"
  geometry: {
    type: "Point"
    coordinates: [number, number]
  }
  properties: {
    name: string
    service: string
    stopId: string
  }
}

export interface StationCollection {
  type: "FeatureCollection"
  features: StationFeature[]
}

export const EMPTY_STATIONS: StationCollection = {
  type: "FeatureCollection",
  features: [],
}
