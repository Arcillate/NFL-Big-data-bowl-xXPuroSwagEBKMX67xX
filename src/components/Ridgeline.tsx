import { useMemo, useState } from 'react'
import { num, pct, useApi } from '../api'

interface Punto {
  grupo: string
  t: number
  densidad: number
  n_presionadas: number
  n_jugadas: number
  pct_presionadas: number
  mediana: number
  orden: number
}

const FAMILIAS: [string, string, string][] = [
  ['rushers', 'Por número de rushers', '% de jugadas con presión'],
  ['posicion', 'Por posición del primer rusher que llega', 'llegadas por snap de rush'],
  ['equipo', 'Por defensa (32 equipos)', '% de jugadas con presión'],
]
const T0 = 0.5
const T1 = 5.0

export default function Ridgeline() {
  const [familia, setFamilia] = useState('rushers')
  const { data } = useApi<Punto[]>(`ridgeline?familia=${familia}`)

  const grupos = useMemo(() => {
    const m = new Map<string, Punto[]>()
    for (const p of data ?? []) m.set(p.grupo, [...(m.get(p.grupo) ?? []), p])
    return [...m.entries()].map(([g, pts]) => ({ g, pts, info: pts[0] })).sort((a, b) => a.info.orden - b.info.orden)
  }, [data])

  const muchos = grupos.length > 10
  const fila = muchos ? 22 : 64
  const alto = fila * 2.4 // cada cresta se sube sobre la de arriba
  const izq = muchos ? 56 : 190
  const der = 150
  const ancho = 900
  const H = fila * grupos.length + alto + 40
  const maxD = Math.max(...(data ?? []).map((p) => p.densidad), 1e-9)
  const sx = (t: number) => izq + ((t - T0) / (T1 - T0)) * (ancho - izq - der)
  const nota = FAMILIAS.find((f) => f[0] === familia)![2]

  return (
    <div className="space-y-3">
      <div className="inline-flex flex-wrap rounded-full bg-slate-100 p-1 text-sm">
        {FAMILIAS.map(([id, nombre]) => (
          <button key={id} onClick={() => setFamilia(id)} className={`rounded-full px-4 py-1.5 ${familia === id ? 'bg-white font-semibold shadow' : 'text-slate-600'}`}>
            {nombre}
          </button>
        ))}
      </div>
      {!data ? (
        <p className="text-slate-500">Cargando…</p>
      ) : (
        <svg viewBox={`0 0 ${ancho} ${H}`} className="w-full">
          <defs>
            <linearGradient id="rl" x1="0" x2="1">
              <stop offset="0%" stopColor="#dc2626" />
              <stop offset="45%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="#0ea5e9" />
            </linearGradient>
          </defs>
          {[1, 2, 2.5, 3, 4, 5].map((t) => (
            <g key={t}>
              <line x1={sx(t)} x2={sx(t)} y1={10} y2={H - 30} stroke={t === 2.5 ? '#64748b' : '#e2e8f0'} strokeDasharray={t === 2.5 ? '4 4' : undefined} />
              <text x={sx(t)} y={H - 12} textAnchor="middle" fontSize={12} fill="#64748b">
                {t} s
              </text>
            </g>
          ))}
          <text x={sx(2.5) + 4} y={20} fontSize={11} fill="#64748b">
            2.5 s: presión "rápida"
          </text>
          {grupos.map(({ g, pts, info }, i) => {
            const base = alto + i * fila + 10
            const ys = (d: number) => base - (d / maxD) * alto
            const linea = pts.map((p) => `${sx(p.t)},${ys(p.densidad)}`).join(' L ')
            const area = `M ${sx(pts[0].t)},${base} L ${linea} L ${sx(pts[pts.length - 1].t)},${base} Z`
            return (
              <g key={g}>
                <path d={area} fill="url(#rl)" fillOpacity={muchos ? 0.55 : 0.75} stroke="white" strokeWidth={1.5} />
                <path d={`M ${linea}`} fill="none" stroke="#0f172a" strokeWidth={muchos ? 0.8 : 1.2} />
                {info.mediana != null && <line x1={sx(info.mediana)} x2={sx(info.mediana)} y1={base} y2={base - (muchos ? 8 : 14)} stroke="#0f172a" strokeWidth={2} />}
                <text x={izq - 8} y={base - 4} textAnchor="end" fontSize={muchos ? 11 : 14} fontWeight={600} fill="#0f172a">
                  {g}
                </text>
                <text x={ancho - der + 10} y={base - 4} fontSize={muchos ? 10 : 12} fill="#475569">
                  {muchos ? `${num(info.mediana, 1)} s · ${pct(info.pct_presionadas, 0)}` : `mediana ${num(info.mediana, 1)} s`}
                </text>
                {!muchos && (
                  <text x={ancho - der + 10} y={base + 12} fontSize={11} fill="#94a3b8">
                    {pct(info.pct_presionadas, 1)} {nota}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      )}
      <p className="text-xs leading-relaxed text-slate-500">
        Cada cresta es la distribución del tiempo hasta presión (segundos desde el snap hasta que un rusher queda a 2 yardas o menos del QB) en las jugadas donde la presión sí
        llegó antes del lanzamiento. La raya vertical marca la mediana. {muchos && 'A la derecha: mediana y % de jugadas presionadas. Ordenadas de la más rápida a la más lenta.'}
      </p>
    </div>
  )
}
