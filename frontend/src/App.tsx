import { useCallback, useMemo, useState } from "react"
import type { Map as MapLibreMap } from "maplibre-gl"

import { FilterSidebar } from "./components/FilterSidebar"
import { LoginGate } from "./components/LoginGate"
import { MapView } from "./components/MapView"
import { TrainPopup } from "./components/TrainPopup"
import { useSession } from "./hooks/useSession"
import { useRouteLines } from "./hooks/useRouteLines"
import { useTrainInterpolation } from "./hooks/useTrainInterpolation"
import { useTrainsData } from "./hooks/useTrainsData"
import type { FeatureCollection, FeedType } from "./types/trains"

export function App() {
  const { status, refresh, markAnonymous, logout } = useSession()

  if (status === "loading") {
    return (
      <main className="gate">
        <p className="lede">Comprobando acceso…</p>
      </main>
    )
  }
  if (status === "anonymous") return <LoginGate onSuccess={() => void refresh()} />
  return <Tracker onLogout={() => void logout()} onUnauthorized={markAnonymous} />
}

function Tracker({ onLogout, onUnauthorized }: { onLogout: () => void; onUnauthorized: () => void }) {
  const [feed, setFeed] = useState<FeedType>("all")
  const [hiddenLines, setHiddenLines] = useState<Set<string>>(() => new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailed, setDetailed] = useState(true)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  const { data, error, updatedAt, loading } = useTrainsData(feed, onUnauthorized)
  const routeLines = useRouteLines(feed, onUnauthorized)
  const visible = useMemo(() => applyLineFilter(data, hiddenLines), [data, hiddenLines])
  const frame = useTrainInterpolation(visible)
  const selected = frame.features.find((feature) => feature.properties.id === selectedId) ?? null
  const lines = useMemo(() => uniqueLines(data), [data])
  const counts = useMemo(() => countServices(data), [data])
  const closePopup = useCallback(() => setSelectedId(null), [])

  function changeFeed(next: FeedType) {
    setFeed(next)
    setHiddenLines(new Set())
    setSelectedId(null)
  }

  function toggleLine(line: string) {
    setHiddenLines((current) => {
      const next = new Set(current)
      if (next.has(line)) next.delete(line)
      else next.add(line)
      return next
    })
  }

  return (
    <div className="app">
      <MapView
        geojson={frame}
        routeLines={routeLines.data}
        hiddenLines={hiddenLines}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onReady={setMap}
      />
      <TrainPopup map={map} train={selected} detailed={detailed} onClose={closePopup} />
      <FilterSidebar
        feed={feed}
        onFeedChange={changeFeed}
        lines={lines}
        hiddenLines={hiddenLines}
        onToggleLine={toggleLine}
        onShowAllLines={() => setHiddenLines(new Set())}
        visibleCount={frame.features.length}
        cercaniasCount={counts.cercanias}
        ldCount={counts.ld}
        updatedAt={updatedAt}
        loading={loading}
        error={error}
        linesError={routeLines.error}
        detailed={detailed}
        onToggleDetail={() => setDetailed((current) => !current)}
        onLogout={onLogout}
      />
    </div>
  )
}

function applyLineFilter(data: FeatureCollection | null, hidden: ReadonlySet<string>): FeatureCollection | null {
  if (!data || hidden.size === 0) return data
  return {
    type: "FeatureCollection",
    features: data.features.filter((feature) => {
      const line = feature.properties.line
      return line == null || !hidden.has(line)
    }),
  }
}

function uniqueLines(data: FeatureCollection | null): string[] {
  const lines = new Set<string>()
  for (const feature of data?.features ?? []) {
    if (feature.properties.line) lines.add(feature.properties.line)
  }
  return [...lines].sort((a, b) => a.localeCompare(b, "es"))
}

function countServices(data: FeatureCollection | null): { cercanias: number; ld: number } {
  const features = data?.features ?? []
  return {
    cercanias: features.filter((feature) => feature.properties.service === "cercanias").length,
    ld: features.filter((feature) => feature.properties.service === "ld").length,
  }
}
