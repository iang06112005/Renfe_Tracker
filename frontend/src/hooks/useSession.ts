import { useCallback, useEffect, useState } from "react"

import { fetchSession, logout as logoutRequest } from "../services/session"

type SessionStatus = "loading" | "anonymous" | "in"

export function useSession() {
  const [status, setStatus] = useState<SessionStatus>("loading")

  const refresh = useCallback(async () => {
    setStatus((await fetchSession()) ? "in" : "anonymous")
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const markAnonymous = useCallback(() => setStatus("anonymous"), [])

  const logout = useCallback(async () => {
    await logoutRequest()
    setStatus("anonymous")
  }, [])

  return { status, refresh, markAnonymous, logout }
}
