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
    const controller = new AbortController()
    void fetchRouteLines(feed, controller.signal)
      .then((next) => {
        setData(next)
        setError(null)
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return
        if (err instanceof AuthError) {
          onUnauthorizedRef.current()
          return
        }
        setData(EMPTY_LINES)
        setError(err instanceof Error ? err.message : "No se han podido cargar los trazados")
      })
    return () => controller.abort()
  }, [feed])

  return { data, error }
}
