import { useEffect, useRef, useState } from "react"

import { AuthError, fetchTrains } from "../services/trains"
import { EMPTY_COLLECTION, type FeatureCollection, type FeedType } from "../types/trains"

const POLL_INTERVAL_MS = 5_000

export function useTrainsData(feed: FeedType, onUnauthorized: () => void, enabled = true) {
  const [data, setData] = useState<FeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const onUnauthorizedRef = useRef(onUnauthorized)
  onUnauthorizedRef.current = onUnauthorized

  useEffect(() => {
    if (!enabled) {
      setData(EMPTY_COLLECTION)
      setError(null)
      setUpdatedAt(null)
      setLoading(false)
      return
    }
    let active = true
    let current: AbortController | null = null

    const load = async () => {
      current?.abort()
      const controller = new AbortController()
      current = controller
      try {
        const next = await fetchTrains(feed, controller.signal)
        if (!active || current !== controller) return
        setData(next)
        setError(null)
        setUpdatedAt(Date.now())
      } catch (err: unknown) {
        if (!active || current !== controller || isAbort(err)) return
        if (err instanceof AuthError) {
          onUnauthorizedRef.current()
          return
        }
        setError(err instanceof Error ? err.message : "No se han podido cargar los trenes")
      } finally {
        if (active && current === controller) setLoading(false)
      }
    }

    setLoading(true)
    void load()
    const timer = window.setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      active = false
      current?.abort()
      window.clearInterval(timer)
    }
  }, [feed, enabled])

  return { data, error, updatedAt, loading }
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError"
}
