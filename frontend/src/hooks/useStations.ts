import { useEffect, useRef, useState } from "react"

import { fetchStations } from "../services/stops"
import { AuthError } from "../services/trains"
import { EMPTY_STATIONS, type StationCollection } from "../types/stops"

export function useStations(feed: string, onUnauthorized: () => void) {
  const [data, setData] = useState<StationCollection>(EMPTY_STATIONS)
  const [error, setError] = useState<string | null>(null)
  const onUnauthorizedRef = useRef(onUnauthorized)
  onUnauthorizedRef.current = onUnauthorized

  useEffect(() => {
    const controller = new AbortController()
    void fetchStations(feed, controller.signal)
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
        setData(EMPTY_STATIONS)
        setError(err instanceof Error ? err.message : "No se han podido cargar las estaciones")
      })
    return () => controller.abort()
  }, [feed])

  return { data, error }
}
