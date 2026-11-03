export async function fetchSession(): Promise<boolean> {
  const response = await fetch("/api/session", { credentials: "same-origin" })
  if (!response.ok) return false
  const body: unknown = await response.json()
  return Boolean(body && typeof body === "object" && "authenticated" in body && body.authenticated === true)
}

export async function login(password: string): Promise<string | null> {
  let response: Response
  try {
    response = await fetch("/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    })
  } catch {
    return "Sin conexión con el servidor"
  }
  if (response.ok) return null
  if (response.status === 401) return "Contraseña incorrecta"
  return "No se ha podido entrar"
}

export async function logout(): Promise<void> {
  await fetch("/api/logout", { method: "POST", credentials: "same-origin" })
}
