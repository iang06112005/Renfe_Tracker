import { useEffect, useRef, useState } from "react"

import { fetchRouteLines } from "../services/lines"
import { EMPTY_LINES, type RouteLineCollection } from "../types/lines"
import { AuthError } from "../services/trains"

export function useRouteLines(feed: string, onUnauthorized: () => void) {
  const [data, setData] = useState<RouteLineCollection>(EMPTY_LINES)
  const [error, setError] = useState<string | null>(null)
  const onUnauthorizedRef = useRef(onUnauthorized)
  onUnauthorizedRef.current = onUnauthorized

  useEffect(() => {
    let active = true
    let timer: number | null = null
    const controller = new AbortController()

    const load = async () => {
      try {
        const next = await fetchRouteLines(feed, controller.signal)
        if (!active) return
        setData(next)
        setError(null)
        if (next.features.length === 0) {
          timer = window.setTimeout(() => void load(), 15_000)
        }
      } catch (err: unknown) {
        if (!active || (err instanceof DOMException && err.name === "AbortError")) return
        if (err instanceof AuthError) {
          onUnauthorizedRef.current()
          return
        }
        setData(EMPTY_LINES)
        setError(err instanceof Error ? err.message : "No se han podido cargar los trazados")
        timer = window.setTimeout(() => void load(), 15_000)
      }
    }

    void load()
    return () => {
      active = false
      controller.abort()
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [feed])

  return { data, error }
}
