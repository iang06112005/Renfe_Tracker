import { type FormEvent, useState } from "react"

import { login } from "../services/session"

interface LoginGateProps {
  onSuccess: () => void
}

export function LoginGate({ onSuccess }: LoginGateProps) {
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const message = await login(password)
    setPending(false)
    if (message) {
      setError(message)
      return
    }
    onSuccess()
  }

  return (
    <main className="gate">
      <form className="gate-card" onSubmit={(event) => void submit(event)}>
        <p className="eyebrow">Grupo privado</p>
        <h1>
          <span>Renfe</span>Tracker
        </h1>
        <p className="lede">
          Mapa en vivo de Cercanías, AVE, Media Distancia y Larga Distancia. Hace falta la contraseña compartida del
          grupo.
        </p>
        <label htmlFor="password">Contraseña</label>
        <input
          id="password"
          type="password"
          name="password"
          autoComplete="current-password"
          autoFocus
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" disabled={pending}>
          {pending ? "Comprobando…" : "Entrar"}
        </button>
      </form>
    </main>
  )
}
