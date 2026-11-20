import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { GrupoTTP, PosicionTTP, Rusher, num, pct, useApi } from '../api'

const GRUPOS: [string, string][] = [
  ['4 rushers', '#2563eb'],
  ['5 (blitz) rushers', '#f59e0b'],
  ['6+ (blitz) rushers', '#dc2626'],
]

export default function TiempoPresion() {
  const { data: curvas } = useApi<Record<string, number>[]>('ttp/curvas')
  const { data: grupos } = useApi<GrupoTTP[]>('ttp/grupos')
  const { data: posiciones } = useApi<PosicionTTP[]>('ttp/posiciones')
  const { data: rapidos } = useApi<Rusher[]>('ttp/mas-rapidos')

  const filasGrupo = grupos?.filter((g) => g.grupo.includes('rushers')) ?? []

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="font-semibold">% de jugadas ya presionadas a cada segundo</h3>
          <p className="text-sm text-gray-600">Kaplan-Meier: si el QB lanza antes, la jugada se cuenta hasta ese momento y no como "sin presión".</p>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={(curvas ?? []).filter((c) => c.t <= 4.5)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="t" type="number" domain={[0, 4.5]} ticks={[0, 1, 2, 2.5, 3, 4]} label={{ value: 'segundos desde el snap', position: 'insideBottom', offset: -3 }} />
              <YAxis tickFormatter={(v) => pct(Number(v), 0)} domain={[0, 0.8]} />
              <Tooltip formatter={(v) => pct(Number(v))} labelFormatter={(t) => `${t} s`} />
              <Legend />
              {GRUPOS.map(([g, c]) => (
                <Line key={g} dataKey={g} stroke={c} dot={false} strokeWidth={2} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3 className="font-semibold">4 rushers contra blitz</h3>
          <table className="mt-2 w-full text-sm">
            <thead className="text-left text-xs uppercase text-gray-500">
              <tr>
                <th>Rushers</th>
                <th>Jugadas</th>
                <th>Presión antes de 2.5 s</th>
                <th>Balón fuera</th>
                <th>SR permitido</th>
              </tr>
            </thead>
            <tbody>
              {filasGrupo.map((g) => (
                <tr key={g.grupo} className="border-t">
                  <td className="py-1">{g.grupo.replace(' rushers', '')}</td>
                  <td>{g.jugadas}</td>
                  <td>{pct(g.p_presion_2_5s)}</td>
                  <td>{num(g.ttt_medio)} s</td>
                  <td className="font-semibold">{pct(g.success_rate_permitido)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 rounded bg-amber-50 p-2 text-sm">
            El blitz hace que la presión llegue antes, pero el QB también suelta el balón antes. El success rate permitido queda igual con 4 que con 5
            rushers.
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="font-semibold">¿Qué posición de la línea llega más rápido?</h3>
          <p className="text-sm text-gray-600">Llegadas a 2 yardas del QB antes de 2.5 s, por snap de rush (posición PFF al alinearse).</p>
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={posiciones ?? []} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => pct(Number(v), 0)} />
              <YAxis type="category" dataKey="pff_positionLinedUp" width={50} fontSize={11} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Bar dataKey="tasa_llegada_rapida" name="Llegada rápida" fill="#dc2626" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
        <h3 className="font-semibold">Rusher más rápido de cada equipo</h3>
        <p className="text-sm text-gray-600">Mínimo 60 snaps de rush. Llegadas rápidas = a 2 yardas del QB antes de 2.5 s.</p>
        <div className="max-h-80 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white text-left text-xs uppercase text-gray-500">
              <tr>
                <th>Equipo</th>
                <th>Jugador</th>
                <th>Posición</th>
                <th>Snaps rush</th>
                <th>Llegadas rápidas / 100</th>
                <th>Llegada mediana</th>
                <th>Presiones PFF</th>
              </tr>
            </thead>
            <tbody>
              {(rapidos ?? []).map((r) => (
                <tr key={r.nflId} className="border-t">
                  <td className="py-1 font-semibold">{r.equipo}</td>
                  <td>{r.displayName}</td>
                  <td>{r.posicion_top}</td>
                  <td>{r.snaps_rush}</td>
                  <td>{num(r.llegadas_rapidas_por_100, 1)}</td>
                  <td>{r.t_llegada_mediana == null ? '—' : `${num(r.t_llegada_mediana, 1)} s`}</td>
                  <td>{r.presiones_pff}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </div>
      </div>
    </div>
  )
}
