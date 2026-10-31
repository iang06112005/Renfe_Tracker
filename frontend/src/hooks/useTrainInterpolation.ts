import { useEffect, useRef, useState } from "react"

import { EMPTY_COLLECTION, type FeatureCollection, type TrainFeature, type TrainProperties } from "../types/trains"

const FRAME_MS = 100
const SNAP_DEGREES = 0.05

interface Motion {
  fromLng: number
  fromLat: number
  toLng: number
  toLat: number
  start: number
  duration: number
  properties: TrainProperties
}

export function useTrainInterpolation(source: FeatureCollection | null, durationMs = 5_000): FeatureCollection {
  const motions = useRef<Map<string, Motion>>(new Map())
  const settled = useRef(false)
  const [frame, setFrame] = useState<FeatureCollection>(EMPTY_COLLECTION)

  useEffect(() => {
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : durationMs
    const now = performance.now()
    const next = new Map<string, Motion>()
    for (const feature of source?.features ?? []) {
      const [lng, lat] = feature.geometry.coordinates
      const previous = motions.current.get(feature.properties.id)
      const current = previous ? positionAt(previous, now) : { lng, lat }
      const jump = Math.hypot(lng - current.lng, lat - current.lat) > SNAP_DEGREES
      next.set(feature.properties.id, {
        fromLng: jump ? lng : current.lng,
        fromLat: jump ? lat : current.lat,
        toLng: lng,
        toLat: lat,
        start: now,
        duration,
        properties: feature.properties,
      })
    }
    motions.current = next
    settled.current = false
    setFrame(buildFrame(next, now))
  }, [source, durationMs])

  useEffect(() => {
    let raf = 0
    let last = 0
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      if (motions.current.size === 0) return
      const done = [...motions.current.values()].every((motion) => now >= motion.start + motion.duration)
      if (done && settled.current) return
      if (!done && now - last < FRAME_MS) return
      last = now
      settled.current = done
      setFrame(buildFrame(motions.current, now))
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return frame
}

function buildFrame(motions: Map<string, Motion>, now: number): FeatureCollection {
  const features: TrainFeature[] = [...motions.values()].map((motion) => {
    const point = positionAt(motion, now)
    return {
      type: "Feature",
      geometry: { type: "Point", coordinates: [point.lng, point.lat] },
      properties: motion.properties,
    }
  })
  return { type: "FeatureCollection", features }
}

function positionAt(motion: Motion, now: number): { lng: number; lat: number } {
  const progress = motion.duration <= 0 ? 1 : Math.min(1, Math.max(0, (now - motion.start) / motion.duration))
  return {
    lng: motion.fromLng + (motion.toLng - motion.fromLng) * progress,
    lat: motion.fromLat + (motion.toLat - motion.fromLat) * progress,
  }
}
