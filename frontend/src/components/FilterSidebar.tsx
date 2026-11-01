import { useEffect, useState } from "react"

import { SERVICE_LABEL } from "../types/trains"
import type { FeedType } from "../types/trains"

interface GroupChip {
  id: string
  label: string
  color: string
}

interface FilterSidebarProps {
  network: "renfe" | "metro"
  onNetworkChange: (network: "renfe" | "metro") => void
  feed: FeedType
  onFeedChange: (feed: FeedType) => void
  lineColors: Record<string, string>
  lines: string[]
  hiddenLines: ReadonlySet<string>
  onToggleLine: (line: string) => void
  onShowAllLines: () => void
  nuclei: GroupChip[]
  hiddenNuclei: ReadonlySet<string>
  onToggleNucleus: (code: string) => void
  onShowAllNuclei: () => void
  products: GroupChip[]
  hiddenProducts: ReadonlySet<string>
  onToggleProduct: (name: string) => void
  onShowAllProducts: () => void
  visibleCount: number
  cercaniasCount: number
  ldCount: number
  updatedAt: number | null
  loading: boolean
  error: string | null
  linesError: string | null
  detailed: boolean
  onToggleDetail: () => void
  onLogout: () => void
}

const FEEDS: { id: FeedType; label: string }[] = [
  { id: "all", label: "Todos" },
  { id: "cercanias", label: "Cercanías" },
  { id: "ld", label: "Alta/MD/LD" },
]

export function FilterSidebar({
  network,
  onNetworkChange,
  feed,
  onFeedChange,
  lines,
  lineColors,
  hiddenLines,
  onToggleLine,
  onShowAllLines,
  nuclei,
  hiddenNuclei,
  onToggleNucleus,
  onShowAllNuclei,
  products,
  hiddenProducts,
  onToggleProduct,
  onShowAllProducts,
  visibleCount,
  cercaniasCount,
  ldCount,
  updatedAt,
  loading,
  error,
  linesError,
  detailed,
  onToggleDetail,
  onLogout,
}: FilterSidebarProps) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <aside className="sidebar">
      <header className="sidebar-head">
        <p className="eyebrow">En vivo</p>
        <h1>
          <span>Renfe</span>Tracker
        </h1>
      </header>

      <div className="segment network" role="group" aria-label="Red">
        <button type="button" aria-pressed={network === "renfe"} onClick={() => onNetworkChange("renfe")}>
          Renfe
        </button>
        <button type="button" aria-pressed={network === "metro"} onClick={() => onNetworkChange("metro")}>
          Metro Madrid
        </button>
      </div>

      {network === "renfe" ? (
      <div className="segment" role="group" aria-label="Tipo de servicio">
        {FEEDS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={feed === item.id}
            onClick={() => onFeedChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      ) : null}

      <p className="count">
        <strong>{loading && visibleCount === 0 ? "…" : visibleCount}</strong>
        <span>{visibleCount === 1 ? "tren en el mapa" : "trenes en el mapa"}</span>
      </p>
      {network === "renfe" ? <p className="meta">{serviceSummary(cercaniasCount, ldCount)}</p> : null}
      {network === "metro" ? <p className="meta">Posición estimada por tiempos de llegada</p> : null}
      <p className="meta">{formatAge(updatedAt, now)}</p>
      {network === "metro" ? (
        <p className="hint">
          Trenes estimados con los teleindicadores de Metro de Madrid. Líneas y estaciones: CRTM.{" "}
          <a href="https://www.transportes.gob.es/" target="_blank" rel="noreferrer">
            Powered by MITRAMS
          </a>
          .
        </p>
      ) : null}
      {network === "renfe" && !loading && !error && updatedAt !== null && visibleCount === 0 ? (
        <p className="hint">Renfe responde, pero ahora mismo no publica ninguna posición.</p>
      ) : null}
      {network === "metro" && !loading && !error && updatedAt !== null && visibleCount === 0 ? (
        <p className="hint">No hay llegadas recientes para estimar trenes ahora mismo.</p>
      ) : null}
      {network === "renfe" && feed !== "cercanias" && products.length === 0 ? (
        <p className="hint">Alta velocidad, media y larga distancia comparten un feed. Cada una lleva su etiqueta.</p>
      ) : null}

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      {network === "renfe" && nuclei.length > 0 ? (
        <GroupFilters
          title="Núcleos"
          groups={nuclei}
          hidden={hiddenNuclei}
          onToggle={onToggleNucleus}
          onShowAll={onShowAllNuclei}
        />
      ) : null}
      {network === "renfe" && products.length > 0 ? (
        <GroupFilters
          title="Servicios"
          groups={products}
          hidden={hiddenProducts}
          onToggle={onToggleProduct}
          onShowAll={onShowAllProducts}
        />
      ) : null}

      {lines.length > 0 ? (
        <div className="lines">
          <div className="lines-head">
            <h2>Líneas</h2>
            {hiddenLines.size > 0 ? (
              <button type="button" className="text-button" onClick={onShowAllLines}>
                Mostrar todas
              </button>
            ) : null}
          </div>
          <div className="chips">
            {lines.map((line) => {
              const hidden = hiddenLines.has(line)
              const color = lineColors[line]
              return (
                <button
                  key={line}
                  type="button"
                  aria-pressed={!hidden}
                  className={color ? "chip group-chip" : "chip"}
                  style={color ? { borderColor: color } : undefined}
                  onClick={() => onToggleLine(line)}
                >
                  {color ? <span className="swatch" style={{ background: color }} /> : null}
                  {line}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}

      <p className="hint">
        {network === "metro"
          ? "Cada punto es un tren aproximado entre estaciones. Colores y trazados: CRTM."
          : "Núcleos y servicios coloreados. En Madrid cada C lleva su color. Las estaciones aparecen al acercar."}
      </p>
      {linesError ? <p className="hint">{linesError}</p> : null}

      <button type="button" className="detail-toggle" aria-pressed={detailed} onClick={onToggleDetail}>
        <span>Detalle del tren</span>
        <span>{detailed ? "Sí" : "No"}</span>
      </button>

      <button type="button" className="logout" onClick={onLogout}>
        Salir
      </button>
    </aside>
  )
}

function GroupFilters({
  title,
  groups,
  hidden,
  onToggle,
  onShowAll,
}: {
  title: string
  groups: GroupChip[]
  hidden: ReadonlySet<string>
  onToggle: (id: string) => void
  onShowAll: () => void
}) {
  return (
    <div className="lines">
      <div className="lines-head">
        <h2>{title}</h2>
        {hidden.size > 0 ? (
          <button type="button" className="text-button" onClick={onShowAll}>
            Mostrar todos
          </button>
        ) : null}
      </div>
      <div className="chips" role="group" aria-label={title}>
        {groups.map((group) => {
          const shown = !hidden.has(group.id)
          return (
            <button
              key={group.id}
              type="button"
              aria-pressed={shown}
              className="chip group-chip"
              style={{ borderColor: group.color }}
              onClick={() => onToggle(group.id)}
            >
              <span className="swatch" style={{ background: group.color }} />
              {group.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function serviceSummary(cercanias: number, ld: number): string {
  const parts = [
    cercanias > 0 ? `${cercanias} ${SERVICE_LABEL.cercanias}` : null,
    ld > 0 ? `${ld} ${SERVICE_LABEL.ld}` : null,
  ].filter((part) => part !== null)
  return parts.join(" · ")
}

function formatAge(updatedAt: number | null, now: number): string {
  if (updatedAt === null) return "Esperando la primera posición"
  const seconds = Math.max(0, Math.round((now - updatedAt) / 1000))
  if (seconds < 5) return "Actualizado ahora"
  return `Actualizado hace ${seconds} s`
}
