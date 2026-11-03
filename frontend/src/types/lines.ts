export interface RouteLineFeature {
  type: "Feature"
  geometry: {
    type: "LineString"
    coordinates: [number, number][]
  }
  properties: {
    line: string | null
    color: string
    service: "cercanias" | "ld" | "metro"
    shapeId: string
  }
}

export interface RouteLineCollection {
  type: "FeatureCollection"
  features: RouteLineFeature[]
}

export const EMPTY_LINES: RouteLineCollection = {
  type: "FeatureCollection",
  features: [],
}
