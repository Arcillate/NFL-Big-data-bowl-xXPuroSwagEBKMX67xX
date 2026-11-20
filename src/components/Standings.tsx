import { useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Ranking, Standing, pct, useApi } from '../api'

const COLORES = ['#047857', '#b91c1c', '#1d4ed8', '#a16207', '#7c3aed', '#0e7490']

export default function Standings() {
  const { data: ranking } = useApi<Ranking[]>('ranking')
  const { data: semanas } = useApi<Standing[]>('standings')
  const [elegidos, setElegidos] = useState<string[]>(['BUF', 'IND'])

  const serie = useMemo(() => {
    if (!semanas) return []
    const porSemana = new Map<number, Record<string, number>>()
    for (const s of semanas) {
      if (!elegidos.includes(s.equipo)) continue
      const fila = porSemana.get(s.week) ?? { week: s.week }
      fila[s.equipo] = s.rank_acumulado
      porSemana.set(s.week, fila)
    }
    return [...porSemana.values()].sort((a, b) => a.week - b.week)
  }, [semanas, elegidos])

  const alternar = (e: string) =>
    setElegidos((v) => (v.includes(e) ? v.filter((x) => x !== e) : v.length >= COLORES.length ? v : [...v, e]))

  if (!ranking) return <p className="text-gray-500">Cargando ranking…</p>
  const max = Math.max(...ranking.map((r) => r.success_rate_permitido))
  const min = Math.min(...ranking.map((r) => r.success_rate_permitido))

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="overflow-x-auto">
        <p className="mb-2 text-sm text-gray-600">Haz clic en un equipo para agregarlo a la gráfica semanal (máximo 6).</p>
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="py-1">#</th>
              <th>Equipo</th>
              <th>SR permitido</th>
              <th>Presión</th>
              <th>Blitz</th>
              <th>Sacks</th>
              <th>Man</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((r) => {
              const activo = elegidos.includes(r.equipo)
              const ancho = 20 + (80 * (r.success_rate_permitido - min)) / (max - min || 1)
              return (
                <tr key={r.equipo} onClick={() => alternar(r.equipo)} className={`cursor-pointer border-t ${activo ? 'bg-emerald-50 font-semibold' : 'hover:bg-gray-50'}`}>
                  <td className="py-1">{r.rank}</td>
                  <td>{r.equipo}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-2 rounded bg-rose-400" style={{ width: `${ancho}px` }} />
                      {pct(r.success_rate_permitido)}
                    </div>
                  </td>
                  <td>{pct(r.presion_rate, 0)}</td>
                  <td>{pct(r.blitz_rate, 0)}</td>
                  <td>{pct(r.sack_rate, 1)}</td>
                  <td>{pct(r.man_rate, 0)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div>
        <h3 className="mb-1 font-semibold">Posición acumulada semana a semana</h3>
        <p className="mb-2 text-sm text-gray-600">Ranking por success rate permitido acumulado hasta esa semana (1 = mejor defensa).</p>
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={serie} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="week" label={{ value: 'Semana', position: 'insideBottom', offset: -5 }} />
            <YAxis reversed domain={[1, 32]} ticks={[1, 8, 16, 24, 32]} allowDecimals={false} />
            <Tooltip formatter={(v) => `#${v}`} labelFormatter={(w) => `Semana ${w}`} />
            <Legend />
            {elegidos.map((e, k) => (
              <Line key={e} type="monotone" dataKey={e} stroke={COLORES[k]} strokeWidth={2} dot connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
