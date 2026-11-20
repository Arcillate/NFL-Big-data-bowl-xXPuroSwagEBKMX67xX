import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { num, pct, useApi } from '../api'

type Fila = Record<string, number | string | null> & { equipo: string; week: number; jugo: number }

const COLORES = ['#059669', '#dc2626', '#2563eb', '#d97706', '#7c3aed', '#0891b2']
const SEMANAS = [1, 2, 3, 4, 5, 6, 7, 8]

// escala T: 50 = promedio; verde arriba, rojo abajo
function colorPuntos(p: number | null) {
  if (p == null) return '#f1f5f9'
  const t = Math.max(-1, Math.min(1, (p - 50) / 20))
  return t >= 0 ? `hsl(152, ${45 + 25 * t}%, ${92 - 42 * t}%)` : `hsl(0, ${45 - 20 * t}%, ${92 + 34 * t}%)`
}

export default function RankingSemanal() {
  const { data } = useApi<Fila[]>('ranking-semanal')
  const [semana, setSemana] = useState(8)
  const [modo, setModo] = useState<'acumulado' | 'semana'>('acumulado')
  const [elegidos, setElegidos] = useState<string[]>(['BUF', 'MIN', 'IND', 'DET'])
  const k = (c: string) => `${c}_${modo}`

  const tablaSemana = useMemo(() => {
    if (!data) return []
    const previa = new Map(data.filter((d) => d.week === semana - 1).map((d) => [d.equipo, d[`rank_acumulado`] as number | null]))
    return data
      .filter((d) => d.week === semana)
      .map((d): Fila & { delta: number | null } => ({ ...d, delta: modo === 'acumulado' && previa.get(d.equipo) != null ? (previa.get(d.equipo) as number) - (d.rank_acumulado as number) : null }))
      .sort((a, b) => ((a[k('rank')] as number) ?? 99) - ((b[k('rank')] as number) ?? 99))
  }, [data, semana, modo])

  const orden = useMemo(() => (data ? data.filter((d) => d.week === 8).sort((a, b) => (a.rank_acumulado as number) - (b.rank_acumulado as number)).map((d) => d.equipo) : []), [data])
  const porEquipoSemana = useMemo(() => new Map((data ?? []).map((d) => [`${d.equipo}-${d.week}`, d])), [data])

  const serie = SEMANAS.map((w) => {
    const fila: Record<string, number | null> = { week: w }
    for (const e of elegidos) fila[e] = (porEquipoSemana.get(`${e}-${w}`)?.[k('puntuacion')] as number | null) ?? null
    return fila
  })

  const alternar = (e: string) => setElegidos((v) => (v.includes(e) ? v.filter((x) => x !== e) : v.length >= COLORES.length ? [...v.slice(1), e] : [...v, e]))

  if (!data) return <p className="text-slate-500">Cargando ranking…</p>
  const maxP = Math.max(...tablaSemana.map((d) => (d[k('puntuacion')] as number) ?? 0))

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-4">
        <div className="inline-flex rounded-full bg-slate-100 p-1 text-sm">
          {(['acumulado', 'semana'] as const).map((m) => (
            <button key={m} onClick={() => setModo(m)} className={`rounded-full px-4 py-1.5 ${modo === m ? 'bg-white font-semibold shadow' : 'text-slate-600'}`}>
              {m === 'acumulado' ? 'Acumulado hasta la semana' : 'Solo esa semana'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {SEMANAS.map((w) => (
            <button key={w} onClick={() => setSemana(w)} className={`h-9 w-9 rounded-full text-sm ${semana === w ? 'bg-emerald-700 font-bold text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>
              {w}
            </button>
          ))}
          <span className="ml-2 text-sm text-slate-500">semana</span>
        </div>
      </div>

      <div className="grid gap-8 xl:grid-cols-5">
        <div className="overflow-x-auto xl:col-span-3">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2">#</th>
                <th />
                <th>Equipo</th>
                <th className="w-40">Puntuación</th>
                <th>SR perm.</th>
                <th>Presión</th>
                <th>Sacks</th>
                <th>INT</th>
                <th>Yd/drop</th>
              </tr>
            </thead>
            <tbody>
              {tablaSemana.map((d) => {
                const p = d[k('puntuacion')] as number | null
                const activo = elegidos.includes(d.equipo)
                return (
                  <tr key={d.equipo} onClick={() => alternar(d.equipo)} className={`cursor-pointer border-t border-slate-100 ${activo ? 'bg-emerald-50' : 'hover:bg-slate-50'}`}>
                    <td className="py-1.5 font-semibold text-slate-700">{d[k('rank')] ?? '—'}</td>
                    <td className="w-8 text-xs">
                      {d.delta != null && d.delta !== 0 && <span className={d.delta > 0 ? 'text-emerald-600' : 'text-rose-600'}>{d.delta > 0 ? `▲${d.delta}` : `▼${-d.delta}`}</span>}
                    </td>
                    <td className={activo ? 'font-bold' : 'font-medium'}>{d.equipo}</td>
                    <td>
                      {p == null ? (
                        <span className="text-xs text-slate-400">descanso</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <div className="h-2.5 rounded-full" style={{ width: `${Math.max(4, (p / maxP) * 100)}px`, background: colorPuntos(p) === '#f1f5f9' ? '#cbd5e1' : p >= 50 ? '#10b981' : '#f87171' }} />
                          <span className="font-mono">{num(p, 1)}</span>
                        </div>
                      )}
                    </td>
                    <td>{pct(d[k('sr_permitido')] as number)}</td>
                    <td>{pct(d[k('presion')] as number, 0)}</td>
                    <td>{pct(d[k('sacks')] as number, 1)}</td>
                    <td>{pct(d[k('intercepciones')] as number, 1)}</td>
                    <td>{num(d[k('yardas_dropback')] as number, 1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="space-y-6 xl:col-span-2">
          <div>
            <h4 className="font-semibold text-slate-800">Evolución de la puntuación</h4>
            <p className="text-xs text-slate-500">Haz clic en un equipo de la tabla para agregarlo o quitarlo (máximo 6).</p>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={serie} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="week" tickFormatter={(w) => `S${w}`} />
                <YAxis domain={[20, 80]} />
                <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: 'promedio', fontSize: 10, fill: '#64748b', position: 'insideTopLeft' }} />
                <Tooltip formatter={(v) => num(Number(v), 1)} labelFormatter={(w) => `Semana ${w}`} />
                {elegidos.map((e, i) => (
                  <Line key={e} dataKey={e} stroke={COLORES[i]} strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-3 text-xs">
              {elegidos.map((e, i) => (
                <span key={e} className="flex items-center gap-1 font-semibold" style={{ color: COLORES[i] }}>
                  <span className="inline-block h-2 w-4 rounded" style={{ background: COLORES[i] }} /> {e}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 p-4 text-xs leading-relaxed text-slate-600">
            <b className="text-slate-800">Cómo se calcula.</b> Para cada defensa se promedian, en z-scores contra las otras 31, seis estadísticas contra el pase: success rate permitido
            (peso doble), yardas por dropback, jugadas de 20+ yardas, presión PFF, sacks e intercepciones. Escala T: 50 es el promedio de la liga y cada 10 puntos es una
            desviación estándar. La puntuación final tiene r = −0.82 con el success rate permitido.
          </div>
        </div>
      </div>

      <div>
        <h4 className="font-semibold text-slate-800">Las 32 defensas, semana a semana</h4>
        <p className="mb-3 text-xs text-slate-500">Número = posición en el ranking {modo === 'acumulado' ? 'acumulado' : 'de esa semana'}. Color = puntuación. Ordenadas por la posición final.</p>
        <div className="overflow-x-auto">
          <div className="inline-grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${orden.length}, minmax(30px, 1fr))` }}>
            {orden.map((e) => (
              <button key={e} onClick={() => alternar(e)} className={`text-center text-[11px] ${elegidos.includes(e) ? 'font-bold text-emerald-700' : 'text-slate-600'}`}>
                {e}
              </button>
            ))}
            {SEMANAS.map((w) =>
              orden.map((e) => {
                const d = porEquipoSemana.get(`${e}-${w}`)
                const p = (d?.[k('puntuacion')] as number | null) ?? null
                const r = d?.[k('rank')] as number | null
                return (
                  <div
                    key={`${e}-${w}`}
                    title={`${e} · semana ${w}: ${p == null ? 'descanso' : `${num(p, 1)} pts, #${r}`}`}
                    className={`flex h-7 items-center justify-center rounded text-[10px] font-medium ${w === semana ? 'ring-2 ring-slate-800' : ''}`}
                    style={{ background: colorPuntos(p), color: p != null && Math.abs(p - 50) > 14 ? 'white' : '#334155' }}
                  >
                    {p == null ? '·' : r}
                  </div>
                )
              }),
            )}
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
          <span>peor</span>
          {[30, 38, 46, 50, 54, 62, 70].map((p) => (
            <span key={p} className="inline-block h-3 w-6 rounded" style={{ background: colorPuntos(p) }} />
          ))}
          <span>mejor</span>
          <span className="ml-4">Filas: semanas 1 a 8 (de arriba abajo). Punto = semana de descanso.</span>
        </div>
      </div>
    </div>
  )
}
