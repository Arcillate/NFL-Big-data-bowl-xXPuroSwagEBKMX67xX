import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { num, pct, useApi } from '../api'

interface Descomp {
  escenario: string
  desv_est_sr: number
  reduccion_pct: number
}

export function Descomposicion() {
  const { data } = useApi<Descomp[]>('descomposicion')
  const filas = (data ?? [])
    .filter((d) => d.escenario !== 'Real')
    .map((d) => ({
      ...d,
      corto: d.escenario.includes('presión promedio') ? 'Misma tasa de presión' : d.escenario.includes('cobertura') ? 'Misma cobertura sin presión' : 'Mismo resultado bajo presión',
    }))
    .sort((a, b) => b.reduccion_pct - a.reduccion_pct)
  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={filas} layout="vertical" margin={{ left: 20, right: 60 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
            <XAxis type="number" tickFormatter={(v) => pct(Number(v), 0)} domain={[0, 0.5]} />
            <YAxis type="category" dataKey="corto" width={190} tick={{ fontSize: 13, fill: '#334155' }} />
            <Tooltip formatter={(v) => pct(Number(v))} />
            <Bar dataKey="reduccion_pct" name="Reducción de la diferencia entre equipos" radius={[0, 6, 6, 0]}>
              {filas.map((f) => (
                <Cell key={f.corto} fill={f.corto.includes('cobertura') ? '#2563eb' : f.corto.includes('presión') && f.corto.startsWith('Misma tasa') ? '#94a3b8' : '#059669'} />
              ))}
              <LabelList dataKey="reduccion_pct" position="right" formatter={(v) => pct(Number(v), 0)} style={{ fontWeight: 700 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-sm leading-relaxed text-slate-600 lg:col-span-2">
        Si las 32 defensas tuvieran la misma tasa de presión, la diferencia de success rate entre ellas casi no cambiaría (−5%). Si todas cubrieran igual cuando no hay presión,
        bajaría 40%. Todas presionan entre 32% y 44% de las veces; lo que más las separa es qué pasa cuando la presión no llega, y después qué tan bien terminan la jugada cuando
        sí llega.
      </p>
    </div>
  )
}

interface Punto {
  equipo: string
  rank: number
  valor_x: number
  valor_y: number
}
interface Respuesta {
  x: string
  etiqueta_x: string
  variables: Record<string, string>
  puntos: Punto[]
  recta: { valor_x: number; recta: number }[]
  pendiente: number
  r: number
  r2: number
  n: number
}

const DESTACADOS: Record<string, string> = { BUF: '#059669', IND: '#dc2626' }

export default function Dispersion() {
  const [x, setX] = useState('presion_rate')
  const { data } = useApi<Respuesta>(`dispersion?x=${x}`)

  const recta = data?.recta.map((p) => ({ valor_x: p.valor_x, valor_y: p.recta })) ?? []
  const fuerza = data ? (Math.abs(data.r) >= 0.5 ? 'fuerte' : Math.abs(data.r) >= 0.3 ? 'moderada' : Math.abs(data.r) >= 0.15 ? 'débil' : 'casi nula') : ''

  return (
    <div className="grid gap-8 lg:grid-cols-4">
      <div className="space-y-2 lg:col-span-1">
        <p className="text-sm font-semibold text-slate-700">Variable del eje X</p>
        {data &&
          Object.entries(data.variables).map(([k, v]) => (
            <button key={k} onClick={() => setX(k)} className={`block w-full rounded-lg border px-3 py-2 text-left text-sm ${x === k ? 'border-emerald-600 bg-emerald-50 font-semibold text-emerald-900' : 'border-slate-200 hover:bg-slate-50'}`}>
              {v}
            </button>
          ))}
      </div>
      <div className="lg:col-span-3">
        {data && (
          <div className="mb-2 flex flex-wrap gap-3">
            <span className="rounded-full bg-slate-900 px-3 py-1 text-sm font-semibold text-white">r = {num(data.r, 2)}</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm">R² = {num(data.r2, 2)}</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm">
              +10 pts en X → {data.pendiente * 0.1 >= 0 ? '+' : ''}
              {num(data.pendiente * 10, 1)} pts de SR permitido
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm">relación {fuerza}</span>
          </div>
        )}
        <ResponsiveContainer width="100%" height={420}>
          <ComposedChart margin={{ top: 20, right: 30, bottom: 30, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              type="number"
              dataKey="valor_x"
              domain={['dataMin - 0.01', 'dataMax + 0.01']}
              tickFormatter={(v) => pct(Number(v), 0)}
              label={{ value: data?.etiqueta_x ?? '', position: 'insideBottom', offset: -18, fill: '#475569', fontSize: 13 }}
            />
            <YAxis
              type="number"
              dataKey="valor_y"
              domain={['dataMin - 0.01', 'dataMax + 0.01']}
              tickFormatter={(v) => pct(Number(v), 0)}
              label={{ value: 'Success rate permitido (menos = mejor)', angle: -90, position: 'insideLeft', offset: 0, fill: '#475569', fontSize: 13, dy: 120 }}
            />
            <ZAxis range={[90, 90]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              content={({ payload }) => {
                const p = payload?.[0]?.payload as Punto | undefined
                return p?.equipo ? (
                  <div className="rounded-lg border bg-white p-2 text-xs shadow">
                    <b>{p.equipo}</b> · #{p.rank} en SR permitido
                    <br />
                    X: {pct(p.valor_x)} · SR permitido: {pct(p.valor_y)}
                  </div>
                ) : null
              }}
            />
            <Scatter data={recta} line={{ stroke: '#0f172a', strokeWidth: 2.5, strokeDasharray: '6 4' }} shape={() => <g />} isAnimationActive={false} legendType="none" />
            <Scatter
              data={data?.puntos ?? []}
              shape={(props: { cx?: number; cy?: number; payload?: Punto }) => (
                <circle cx={props.cx} cy={props.cy} r={DESTACADOS[props.payload?.equipo ?? ''] ? 8 : 6} fill={DESTACADOS[props.payload?.equipo ?? ''] ?? '#6366f1'} fillOpacity={0.85} stroke="white" strokeWidth={1.5} />
              )}
            >
              <LabelList dataKey="equipo" position="top" offset={8} style={{ fontSize: 10, fill: '#334155' }} />
            </Scatter>
          </ComposedChart>
        </ResponsiveContainer>
        <p className="text-xs text-slate-500">
          Cada punto es una defensa (n = {data?.n ?? 32}). Línea punteada: regresión por mínimos cuadrados. Una pendiente negativa significa que más de esa variable va con menos
          éxito ofensivo. En verde Buffalo (la mejor), en rojo Indianapolis (la peor).
        </p>
      </div>
    </div>
  )
}
