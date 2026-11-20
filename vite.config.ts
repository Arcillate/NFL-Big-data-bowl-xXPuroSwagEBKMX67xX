import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' para que el build funcione desde cualquier ruta (la app se publica en una subruta).
// En desarrollo, /api va a Uvicorn en el puerto 8000.
// `vite build --mode pages` (npm run build:pages) genera la versión estática para GitHub Pages: copia los JSON de
// static-api/ al build en lugar de llamar a FastAPI.
export default defineConfig(({ mode }) => ({
  base: './',
  plugins: [react()],
  publicDir: mode === 'pages' ? 'static-api' : 'public',
  server: { proxy: { '/api': 'http://localhost:8000' } },
}))
