import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useState } from 'react'
import { PerfilEquipo, num, pct, useApi } from '../api'

const COLOR_A = '#047857'
const COLOR_B = '#b91c1c'

function Selector({ valor, cambiar, equipos }: { valor: string; cambiar: (v: string) => void; equipos: string[] }) {
  return (
    <select className="rounded border px-2 py-1 font-semibold" value={valor} onChange={(e) => cambiar(e.target.value)}>
      {equipos.map((e) => (
        <option key={e}>{e}</option>
      ))}
    </select>
  )
}

function Tarjeta({ p, color }: { p: PerfilEquipo; color: string }) {
  const r = p.ranking
  const filas: [string, string][] = [
    ['Ranking (SR permitido)', `#${r.rank} · ${pct(r.success_rate_permitido)}`],
    ['Presión (PFF)', pct(r.presion_rate)],
    ['Blitz (5+ rushers)', pct(r.blitz_rate)],
    ['Sack rate', pct(r.sack_rate)],
    ['Man coverage', pct(r.man_rate)],
    ['SR con presión', pct(r.sr_con_presion)],
    ['SR sin presión', pct(r.sr_sin_presion)],
    ['Presionadas antes de 2.5 s', pct(p.ttp?.p_presion_2_5s)],
    ['Cobertura más usada', r.cobertura_top],
  ]
  return (
    <div className="rounded-lg border-2 p-3" style={{ borderColor: color }}>
      <h3 className="mb-2 text-xl font-bold" style={{ color }}>
        {p.equipo}
      </h3>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1 text-sm">
        {filas.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-gray-600">{k}</dt>
            <dd className="font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      {p.rusher_mas_rapido && (
        <p className="mt-2 text-sm">
          Rusher más rápido: <b>{p.rusher_mas_rapido.displayName}</b> ({p.rusher_mas_rapido.posicion_top}),{' '}
          {num(p.rusher_mas_rapido.llegadas_rapidas_por_100, 1)} llegadas antes de 2.5 s por cada 100 snaps
        </p>
      )}
    </div>
  )
}

export default function Comparacion() {
  const { data: equipos } = useApi<string[]>('equipos')
  const [a, setA] = useState('BUF')
  const [b, setB] = useState('IND')
  const { data: pa } = useApi<PerfilEquipo>(`equipo/${a}`)
  const { data: pb } = useApi<PerfilEquipo>(`equipo/${b}`)

  if (!equipos || !pa || !pb) return <p className="text-gray-500">Cargando equipos…</p>

  const celda = (p: PerfilEquipo, c: string, pr: string) => p.matriz.find((m) => m.cobertura === c && m.presion === pr)?.success_rate
  const matriz = ['Man', 'Zone'].flatMap((c) =>
    ['Con presión', 'Sin presión'].map((pr) => ({ caso: `${c} ${pr.toLowerCase()}`, [a]: celda(pa, c, pr), [b]: celda(pb, c, pr) })),
  )
  const covs = [...new Set([...pa.coberturas, ...pb.coberturas].map((c) => c.cobertura))]
  const mezcla = covs
    .map((c) => ({ cobertura: c, [a]: pa.coberturas.find((x) => x.cobertura === c)?.pct ?? 0, [b]: pb.coberturas.find((x) => x.cobertura === c)?.pct ?? 0 }))
    .sort((x, y) => (y[a] as number) + (y[b] as number) - (x[a] as number) - (x[b] as number))
    .slice(0, 7)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Selector valor={a} cambiar={setA} equipos={equipos} />
        <span className="text-gray-500">contra</span>
        <Selector valor={b} cambiar={setB} equipos={equipos} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Tarjeta p={pa} color={COLOR_A} />
        <Tarjeta p={pb} color={COLOR_B} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="font-semibold">Success rate permitido por cobertura y presión</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={matriz}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="caso" fontSize={11} />
              <YAxis tickFormatter={(v) => pct(Number(v), 0)} domain={[0, 0.8]} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Legend />
              <Bar dataKey={a} fill={COLOR_A} />
              <Bar dataKey={b} fill={COLOR_B} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3 className="font-semibold">Mezcla de coberturas</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={mezcla}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="cobertura" fontSize={11} />
              <YAxis tickFormatter={(v) => pct(Number(v), 0)} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Legend />
              <Bar dataKey={a} fill={COLOR_A} />
              <Bar dataKey={b} fill={COLOR_B} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className="text-xs text-gray-500">Muestras por equipo de 7 a 8 partidos (unas 250 jugadas): cada celda tiene entre 20 y 100 jugadas.</p>
    </div>
  )
}
