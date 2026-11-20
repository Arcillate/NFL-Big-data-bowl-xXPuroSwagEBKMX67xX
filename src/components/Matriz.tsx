import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CeldaMatriz, Interaccion, pct, useApi } from '../api'

const FILAS = ['Man', 'Zone', 'Cover-0', 'Cover-1', '2-Man', 'Cover-2', 'Cover-3', 'Quarters', 'Cover-6', 'Todas']

// Color de celda: verde = defensa gana (SR bajo), rojo = ofensiva gana (SR alto). Escala 30% a 65%.
function colorSR(sr: number) {
  const t = Math.max(0, Math.min(1, (sr - 0.3) / 0.35))
  const h = 140 - 140 * t
  return `hsl(${h}, 65%, ${88 - 10 * Math.abs(t - 0.5)}%)`
}

export default function Matriz() {
  const [sinSacks, setSinSacks] = useState(false)
  const { data } = useApi<CeldaMatriz[]>(`matriz?excluye_sacks=${sinSacks}`)
  const { data: inter } = useApi<Interaccion[]>('interaccion')

  if (!data) return <p className="text-gray-500">Cargando matriz…</p>
  const celda = (c: string, p: string) => data.find((d) => d.cobertura === c && d.presion === p)
  const barras = FILAS.slice(2, 9).map((c) => ({ cobertura: c, 'Con presión': celda(c, 'Con presión')?.success_rate, 'Sin presión': celda(c, 'Sin presión')?.success_rate }))
  const it = inter?.filter((d) => d.excluye_sacks === sinSacks) ?? []
  const fmtPts = (d?: Interaccion) => (d ? `${d.puntos_sr.toFixed(1)} pts (IC95 ${d.ic95_bajo.toFixed(1)} a ${d.ic95_alto.toFixed(1)})` : '—')

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={sinSacks} onChange={(e) => setSinSacks(e.target.checked)} />
        Excluir sacks (un sack siempre es fracaso ofensivo e infla el efecto de la presión)
      </label>
      <div className="grid gap-6 lg:grid-cols-2">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="py-1">Cobertura</th>
              <th>Con presión</th>
              <th>Sin presión</th>
              <th>Efecto presión</th>
            </tr>
          </thead>
          <tbody>
            {FILAS.map((c) => {
              const con = celda(c, 'Con presión')
              const sin = celda(c, 'Sin presión')
              const sep = c === 'Cover-0' || c === 'Todas'
              return (
                <tr key={c} className={sep ? 'border-t-2 border-gray-400' : 'border-t'}>
                  <td className="py-1 font-medium">{c}</td>
                  {[con, sin].map((d, k) => (
                    <td key={k} className="px-1">
                      {d && (
                        <div className="rounded px-2 py-1 text-center" style={{ background: colorSR(d.success_rate) }} title={`IC95 ${pct(d.ic95_bajo)} a ${pct(d.ic95_alto)}`}>
                          <b>{pct(d.success_rate)}</b> <span className="text-xs text-gray-600">n={d.jugadas}</span>
                        </div>
                      )}
                    </td>
                  ))}
                  <td className="text-center font-mono">{con && sin ? `${((con.success_rate - sin.success_rate) * 100).toFixed(1)} pts` : ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={barras} margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="cobertura" />
            <YAxis tickFormatter={(v) => pct(Number(v), 0)} domain={[0, 0.7]} />
            <Tooltip formatter={(v) => pct(Number(v))} />
            <Legend />
            <Bar dataKey="Con presión" fill="#059669" />
            <Bar dataKey="Sin presión" fill="#e11d48" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="rounded-lg bg-gray-50 p-3 text-sm">
        <p className="font-semibold">¿La man solo sirve con presión?</p>
        <ul className="ml-5 list-disc">
          <li>Efecto de la presión en man: {fmtPts(it.find((d) => d.contraste === 'efecto presión en Man'))}</li>
          <li>Efecto de la presión en zona: {fmtPts(it.find((d) => d.contraste === 'efecto presión en Zone'))}</li>
          <li>Diferencia entre ambos: {fmtPts(it.find((d) => d.contraste === 'diferencia (Man - Zone)'))}. Incluye el cero: la presión ayuda igual a las dos.</li>
          <li>Sin presión, man menos zona: {fmtPts(it.find((d) => d.contraste === 'Man - Zone sin presión'))}. Si la presión no llega, la man aguanta algo mejor.</li>
        </ul>
        <p className="mt-1 text-xs text-gray-500">IC95 por bootstrap remuestreando partidos completos.</p>
      </div>
    </div>
  )
}
