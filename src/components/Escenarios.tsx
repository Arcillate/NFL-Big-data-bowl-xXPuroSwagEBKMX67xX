import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { num, pct, useApi } from '../api'

interface Escenario {
  presion: string
  receptor: string
  escenario: string
  jugadas: number
  pct_jugadas: number
  success_rate: number
  ic95_bajo: number
  ic95_alto: number
  yardas: number
  int_rate: number
  explosivas_rate: number
}

const ORDEN: [string, string, string, string][] = [
  ['Sin presión', 'Receptor abierto', 'Sin presión\nreceptor abierto', '#e11d48'],
  ['Sin presión', 'Receptor cubierto', 'Sin presión\nreceptor cubierto', '#fb7185'],
  ['Con presión', 'Receptor abierto', 'Con presión\nreceptor abierto', '#34d399'],
  ['Con presión', 'Receptor cubierto', 'Con presión\nreceptor cubierto', '#059669'],
]

function Tick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const [a, b] = (payload?.value ?? '').split('\n')
  return (
    <text x={x} y={(y ?? 0) + 12} textAnchor="middle" fontSize={12} fill="#334155">
      <tspan x={x} fontWeight={600}>
        {a}
      </tspan>
      <tspan x={x} dy={15}>
        {b}
      </tspan>
    </text>
  )
}

export default function Escenarios() {
  const [sinSacks, setSinSacks] = useState(false)
  const { data } = useApi<Escenario[]>(`escenarios?excluye_sacks=${sinSacks}`)
  if (!data) return <p className="text-slate-500">Cargando escenarios…</p>

  const filas = ORDEN.map(([p, r, etiqueta, color]) => {
    const d = data.find((x) => x.presion === p && x.receptor === r)!
    return { ...d, etiqueta, color, err: [d.success_rate - d.ic95_bajo, d.ic95_alto - d.success_rate] }
  })
  const [saAb, saCu, caAb, caCu] = filas.map((f) => f.success_rate)

  return (
    <div className="grid gap-8 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <ResponsiveContainer width="100%" height={380}>
          <BarChart data={filas} margin={{ top: 30, right: 10, left: -10, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="etiqueta" tick={<Tick />} interval={0} height={50} />
            <YAxis tickFormatter={(v) => pct(Number(v), 0)} domain={[0, 0.7]} />
            <Tooltip
              cursor={{ fill: '#f8fafc' }}
              content={({ payload }) => {
                const d = payload?.[0]?.payload as (typeof filas)[number] | undefined
                return d ? (
                  <div className="rounded-lg border bg-white p-3 text-xs shadow">
                    <b>{d.escenario}</b>
                    <br />
                    Success rate: {pct(d.success_rate)} (IC95 {pct(d.ic95_bajo)} a {pct(d.ic95_alto)})
                    <br />
                    Jugadas: {d.jugadas.toLocaleString()} ({pct(d.pct_jugadas, 0)} del total)
                    <br />
                    Yardas por jugada: {num(d.yardas, 1)}
                  </div>
                ) : null
              }}
            />
            <Bar dataKey="success_rate" radius={[8, 8, 0, 0]}>
              {filas.map((f) => (
                <Cell key={f.escenario} fill={f.color} />
              ))}
              <ErrorBar dataKey="err" width={8} stroke="#334155" />
              <LabelList dataKey="success_rate" position="top" offset={14} formatter={(v) => pct(Number(v))} style={{ fontWeight: 700, fill: '#0f172a' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <label className="mt-2 flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={sinSacks} onChange={(e) => setSinSacks(e.target.checked)} className="accent-emerald-700" />
          Excluir sacks (un sack siempre cuenta como fracaso ofensivo)
        </label>
      </div>
      <div className="space-y-4 lg:col-span-2">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-3xl font-bold text-emerald-800">{((saCu - caCu) * 100).toFixed(0)} pts</p>
          <p className="text-sm text-emerald-900">baja el success rate cuando llega la presión, aunque la cobertura sea la misma (receptor cubierto).</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-3xl font-bold text-slate-800">{((saAb - saCu) * 100).toFixed(1)} pts</p>
          <p className="text-sm text-slate-700">es lo que gana la defensa por cubrir bien cuando no hay presión. Con presión, la diferencia es de solo {((caAb - caCu) * 100).toFixed(1)} pts.</p>
        </div>
        <p className="text-xs leading-relaxed text-slate-500">
          <b>Receptor abierto</b>: al soltar el balón, al menos la mitad de las rutas tiene 3 o más yardas de separación del defensor más cercano (tracking). Las barras negras son
          el intervalo de confianza del 95%. La separación se mide al soltar: un QB presionado lanza antes, cuando las rutas aún no se abren, así que parte del efecto de la
          cobertura viene de la presión.
        </p>
      </div>
    </div>
  )
}
