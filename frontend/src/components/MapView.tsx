import { useEffect, useRef, useState } from "react"
import maplibregl, { GeoJSONSource, type Map as MapLibreMap } from "maplibre-gl"

import type { RouteLineCollection } from "../types/lines"
import type { StationCollection } from "../types/stops"
import type { FeatureCollection } from "../types/trains"

const STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
const RAIL_TILES = ["https://tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png"]
const RAIL_SOURCE = "openrailwaymap"
const RAIL_LAYER = "openrailwaymap"
const ROUTE_SOURCE = "route-lines"
const ROUTE_CASING = "route-lines-casing"
const ROUTE_LAYER = "route-lines"
const STATION_SOURCE = "stations"
const STATION_LAYER = "stations"
const STATION_LABELS = "station-labels"
const SOURCE_ID = "trains"
const HIT_LAYER = "trains-hit"
const CIRCLE_LAYER = "trains-circles"
const HIGHLIGHT_LAYER = "trains-highlight"
const LABEL_LAYER = "trains-labels"

interface MapViewProps {
  geojson: FeatureCollection
  routeLines: RouteLineCollection
  stations: StationCollection
  hiddenNuclei: ReadonlySet<string>
  hiddenLines: ReadonlySet<string>
  network: "renfe" | "metro"
  selectedId: string | null
  onSelect: (id: string | null) => void
  onReady: (map: MapLibreMap | null) => void
}

export function MapView({
  geojson,
  routeLines,
  stations,
  hiddenNuclei,
  hiddenLines,
  network,
  selectedId,
  onSelect,
  onReady,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const onSelectRef = useRef(onSelect)
  const onReadyRef = useRef(onReady)
  const geojsonRef = useRef(geojson)
  const [ready, setReady] = useState(false)

  onSelectRef.current = onSelect
  onReadyRef.current = onReady
  geojsonRef.current = geojson

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let cancelled = false
    const map = new maplibregl.Map({
      container,
      style: STYLE_URL,
      center: [-3.7, 40.0],
      zoom: 5.3,
      attributionControl: { compact: true },
      fadeDuration: 0,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")
    mapRef.current = map
    const applyPadding = () => {
      if (!map.isStyleLoaded()) return
      const narrow = window.innerWidth <= 720
      map.setPadding({ top: 0, left: 0, right: 0, bottom: narrow ? Math.round(window.innerHeight * 0.46) : 0 })
    }
    window.addEventListener("resize", applyPadding)

    map.on("load", () => {
      if (cancelled) return
      addRailNetwork(map)
      addRouteLines(map)
      addStations(map)
      map.addSource(SOURCE_ID, { type: "geojson", data: geojsonRef.current })
      map.addLayer({
        id: HIT_LAYER,
        type: "circle",
        source: SOURCE_ID,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 14, 8, 16, 12, 18],
          "circle-color": "#000000",
          "circle-opacity": 0.01,
        },
      })
      map.addLayer({
        id: CIRCLE_LAYER,
        type: "circle",
        source: SOURCE_ID,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4.5, 3.2, 8, 5, 12, 7],
          "circle-color": [
            "coalesce",
            ["get", "groupColor"],
            ["match", ["get", "service"], "cercanias", "#e10600", "#c8c2b4"],
          ],
          "circle-stroke-width": 1.4,
          "circle-stroke-color": "#1c1917",
          "circle-opacity": 0.96,
        },
      })
      map.addLayer({
        id: HIGHLIGHT_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["get", "id"], ""],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4.5, 7, 8, 10, 12, 13],
          "circle-color": "transparent",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#1c1917",
        },
      })
      map.addLayer({
        id: LABEL_LAYER,
        type: "symbol",
        source: SOURCE_ID,
        minzoom: 8,
        layout: {
          "text-field": ["coalesce", ["get", "line"], ["get", "vehicleId"], ""],
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
          "text-size": 11,
          "text-offset": [0, 1.05],
          "text-anchor": "top",
          "text-allow-overlap": false,
        },
        paint: {
          "text-color": "#1c1917",
          "text-halo-color": "#f7f5f0",
          "text-halo-width": 1.4,
        },
      })
      map.on("click", (event) => {
        const hits = map.queryRenderedFeatures(event.point, { layers: [HIT_LAYER, LABEL_LAYER] })
        const id = hits[0]?.properties?.id
        onSelectRef.current(typeof id === "string" ? id : null)
      })
      map.on("mouseenter", HIT_LAYER, () => {
        map.getCanvas().style.cursor = "pointer"
      })
      map.on("mouseleave", HIT_LAYER, () => {
        map.getCanvas().style.cursor = ""
      })
      for (const layerId of [HIT_LAYER, CIRCLE_LAYER, HIGHLIGHT_LAYER, LABEL_LAYER]) {
        if (map.getLayer(layerId)) map.moveLayer(layerId)
      }
      applyPadding()
      onReadyRef.current(map)
      setReady(true)
    })

    return () => {
      cancelled = true
      window.removeEventListener("resize", applyPadding)
      onReadyRef.current(null)
      map.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const source = map.getSource(SOURCE_ID)
    if (source instanceof GeoJSONSource) source.setData(geojson)
  }, [geojson, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const source = map.getSource(ROUTE_SOURCE)
    if (source instanceof GeoJSONSource) source.setData(visibleRouteLines(routeLines, hiddenNuclei, hiddenLines))
  }, [routeLines, hiddenNuclei, hiddenLines, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const source = map.getSource(STATION_SOURCE)
    if (source instanceof GeoJSONSource) source.setData(stations)
  }, [stations, ready])

  const positioned = useRef(false)

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !map.getLayer(RAIL_LAYER)) return
    map.setLayoutProperty(RAIL_LAYER, "visibility", network === "metro" ? "none" : "visible")
    if (!positioned.current) {
      positioned.current = true
      if (network === "renfe") return
    }
    const target =
      network === "metro"
        ? { center: [-3.7038, 40.4168] as [number, number], zoom: 12 }
        : { center: [-3.7, 40.0] as [number, number], zoom: 5.4 }
    map.flyTo({ ...target, essential: true })
  }, [network, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !map.getLayer(HIGHLIGHT_LAYER)) return
    map.setFilter(HIGHLIGHT_LAYER, ["==", ["get", "id"], selectedId ?? ""])
  }, [selectedId, ready])

  return <div ref={containerRef} className="map" />
}

function addRailNetwork(map: MapLibreMap) {
  map.addSource(RAIL_SOURCE, {
    type: "raster",
    tiles: RAIL_TILES,
    tileSize: 256,
    maxzoom: 19,
    attribution: "© OpenRailwayMap (CC-BY-SA), © OpenStreetMap",
  })
  map.addLayer({
    id: RAIL_LAYER,
    type: "raster",
    source: RAIL_SOURCE,
    paint: {
      "raster-opacity": 0.16,
      "raster-saturation": -0.85,
      "raster-contrast": -0.35,
      "raster-brightness-min": 0.15,
      "raster-brightness-max": 0.92,
      "raster-fade-duration": 0,
    },
  })
}

function addRouteLines(map: MapLibreMap) {
  map.addSource(ROUTE_SOURCE, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  })
  map.addLayer({
    id: ROUTE_CASING,
    type: "line",
    source: ROUTE_SOURCE,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": "#f7f5f0",
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.35, 11, 0.85, 14, 0.95],
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.9, 10, 2.2, 13, 4.2, 15, 6.4],
    },
  })
  map.addLayer({
    id: ROUTE_LAYER,
    type: "line",
    source: ROUTE_SOURCE,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": ["coalesce", ["get", "color"], "#5c6570"],
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.62, 10, 0.9, 14, 0.96],
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.7, 10, 1.8, 13, 3.1, 15, 4.6],
    },
  })
}

function addStations(map: MapLibreMap) {
  map.addSource(STATION_SOURCE, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  })
  map.addLayer({
    id: STATION_LAYER,
    type: "circle",
    source: STATION_SOURCE,
    minzoom: 11,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.2, 13, 3.4, 15, 5],
      "circle-color": "#ffffff",
      "circle-stroke-width": 1.4,
      "circle-stroke-color": "#2c333a",
    },
  })
  map.addLayer({
    id: STATION_LABELS,
    type: "symbol",
    source: STATION_SOURCE,
    minzoom: 13,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
      "text-size": 11,
      "text-offset": [0, 0.9],
      "text-anchor": "top",
      "text-optional": true,
    },
    paint: {
      "text-color": "#2c333a",
      "text-halo-color": "#f7f5f0",
      "text-halo-width": 1.2,
    },
  })
}

function visibleRouteLines(
  collection: RouteLineCollection,
  hiddenNuclei: ReadonlySet<string>,
  hiddenLines: ReadonlySet<string>,
): RouteLineCollection {
  if (hiddenNuclei.size === 0 && hiddenLines.size === 0) return collection
  return {
    type: "FeatureCollection",
    features: collection.features.filter((feature) => {
      const line = feature.properties.line
      if (line && hiddenLines.has(line)) return false
      const nucleus = nucleusFromShape(feature.properties.shapeId)
      return nucleus == null || !hiddenNuclei.has(nucleus)
    }),
  }
}

function nucleusFromShape(shapeId: string): string | null {
  const match = /^(\d{2})_/.exec(shapeId)
  return match ? match[1] : null
}
