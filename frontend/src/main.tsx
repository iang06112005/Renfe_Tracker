import "@fontsource/ibm-plex-sans/400.css"
import "@fontsource/ibm-plex-sans/600.css"
import "@fontsource/ibm-plex-mono/500.css"
import "maplibre-gl/dist/maplibre-gl.css"

import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { App } from "./App"
import "./index.css"

const root = document.getElementById("root")
if (!root) throw new Error("No se encontró #root")

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
