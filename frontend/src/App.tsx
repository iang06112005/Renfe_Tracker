import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react"
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
  const [hiddenNuclei, setHiddenNuclei] = useState<Set<string>>(() => new Set())
  const [hiddenProducts, setHiddenProducts] = useState<Set<string>>(() => new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailed, setDetailed] = useState(true)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  const { data, error, updatedAt, loading } = useTrainsData(feed, onUnauthorized)
  const routeLines = useRouteLines(feed, onUnauthorized)
  const visible = useMemo(
    () => applyVisibility(data, hiddenLines, hiddenNuclei, hiddenProducts),
    [data, hiddenLines, hiddenNuclei, hiddenProducts],
  )
  const nuclei = useMemo(() => nucleusGroups(data), [data])
  const products = useMemo(() => productGroups(data), [data])
  const frame = useTrainInterpolation(visible)
  const selected = frame.features.find((feature) => feature.properties.id === selectedId) ?? null
  const lines = useMemo(() => uniqueLines(data), [data])
  const counts = useMemo(() => countServices(data), [data])
  const closePopup = useCallback(() => setSelectedId(null), [])

  function changeFeed(next: FeedType) {
    setFeed(next)
    setHiddenLines(new Set())
    setHiddenNuclei(new Set())
    setHiddenProducts(new Set())
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
        hiddenNuclei={hiddenNuclei}
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
        nuclei={nuclei}
        hiddenNuclei={hiddenNuclei}
        onToggleNucleus={(code) => toggleSet(setHiddenNuclei, code)}
        onShowAllNuclei={() => setHiddenNuclei(new Set())}
        products={products}
        hiddenProducts={hiddenProducts}
        onToggleProduct={(name) => toggleSet(setHiddenProducts, name)}
        onShowAllProducts={() => setHiddenProducts(new Set())}
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

function applyVisibility(
  data: FeatureCollection | null,
  hiddenLines: ReadonlySet<string>,
  hiddenNuclei: ReadonlySet<string>,
  hiddenProducts: ReadonlySet<string>,
): FeatureCollection | null {
  if (!data) return data
  if (hiddenLines.size === 0 && hiddenNuclei.size === 0 && hiddenProducts.size === 0) return data
  return {
    type: "FeatureCollection",
    features: data.features.filter((feature) => {
      const line = feature.properties.line
      if (line && hiddenLines.has(line)) return false
      const nucleus = feature.properties.nucleus
      if (nucleus && hiddenNuclei.has(nucleus)) return false
      const bucket = feature.properties.bucket
      if (feature.properties.service === "ld" && bucket && hiddenProducts.has(bucket)) return false
      return true
    }),
  }
}

function toggleSet(setter: Dispatch<SetStateAction<Set<string>>>, id: string) {
  setter((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
}

const BUCKET_ORDER = ["alta", "media", "larga"]

function nucleusGroups(data: FeatureCollection | null): GroupChip[] {
  const byCode = new Map<string, GroupChip>()
  for (const feature of data?.features ?? []) {
    const code = feature.properties.nucleus
    if (!code || byCode.has(code)) continue
    const place = feature.properties.nucleusLabel
    byCode.set(code, {
      id: code,
      label: place ? `${code} ${place}` : code,
      color: feature.properties.nucleusColor ?? "#e10600",
    })
  }
  return [...byCode.values()].sort((a, b) => a.id.localeCompare(b.id, "es", { numeric: true }))
}

function productGroups(data: FeatureCollection | null): GroupChip[] {
  const byBucket = new Map<string, GroupChip>()
  for (const feature of data?.features ?? []) {
    if (feature.properties.service !== "ld") continue
    const bucket = feature.properties.bucket
    if (!bucket || byBucket.has(bucket) || !BUCKET_ORDER.includes(bucket)) continue
    byBucket.set(bucket, {
      id: bucket,
      label: feature.properties.bucketLabel ?? bucket,
      color: feature.properties.bucketColor ?? "#c8c2b4",
    })
  }
  return [...byBucket.values()].sort((a, b) => BUCKET_ORDER.indexOf(a.id) - BUCKET_ORDER.indexOf(b.id))
}

interface GroupChip {
  id: string
  label: string
  color: string
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
