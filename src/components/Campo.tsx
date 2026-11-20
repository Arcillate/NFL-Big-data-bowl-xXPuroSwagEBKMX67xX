import { useEffect, useMemo, useState } from 'react'
import { AnimIndice, Animacion, num, useApi } from '../api'

// Coordenadas normalizadas: la ofensiva siempre ataca hacia la derecha. Campo 120 x 53.3 yardas (con end zones).
const LARGO = 120
const ANCHO = 160 / 3
const UMBRAL = 2

const COLOR: Record<string, string> = {
  'Pass Rush': '#dc2626',
  Coverage: '#2563eb',
  'Pass Block': '#9ca3af',
  'Pass Route': '#f59e0b',
  Pass: '#ffffff',
  Balón: '#7c2d12',
}
const LEYENDA = [
  ['Pass Rush', 'Pass rusher'],
  ['Coverage', 'Cobertura'],
  ['Pass Block', 'Bloqueador'],
  ['Pass Route', 'Receptor'],
  ['Pass', 'QB'],
]

export default function Campo() {
  const { data: lista, error } = useApi<AnimIndice[]>('animaciones')
  const [sel, setSel] = useState(0)
  const jugada = lista?.[sel]
  const { data: anim } = useApi<Animacion>(jugada ? `animaciones/${jugada.gameId}/${jugada.playId}` : null)
  const [i, setI] = useState(0)
  const [play, setPlay] = useState(false)

  useEffect(() => {
    setI(0)
    setPlay(false)
  }, [sel])

  const n = anim?.cuadros.length ?? 0
  useEffect(() => {
    if (!play || !n) return
    const id = setInterval(() => setI((v) => (v + 1 >= n ? (setPlay(false), v) : v + 1)), 100) // 10 cuadros/s
    return () => clearInterval(id)
  }, [play, n])

  const cuadro = anim?.cuadros[Math.min(i, Math.max(n - 1, 0))]
  const qb = cuadro?.jugadores.find((j) => j.rol === 'Pass')
  const rusherMin = useMemo(() => {
    const d = cuadro?.jugadores.filter((j) => j.rol === 'Pass Rush' && j.dist_qb != null) ?? []
    return d.length ? Math.min(...d.map((j) => j.dist_qb as number)) : null
  }, [cuadro])
  const presionado = cuadro != null && cuadro.t >= 0.5 && rusherMin != null && rusherMin <= UMBRAL

  // vista centrada en la jugada: 40 yardas alrededor de la línea de scrimmage
  const lx = jugada?.linea_x ?? 60
  const x0 = Math.max(0, Math.min(LARGO - 40, lx - 15))

  if (error) return <p className="text-red-600">No se pudo cargar: {error}</p>
  if (!lista) return <p className="text-gray-500">Cargando jugadas…</p>

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select className="rounded border px-2 py-1" value={sel} onChange={(e) => setSel(Number(e.target.value))}>
          {lista.map((j, k) => (
            <option key={`${j.gameId}-${j.playId}`} value={k}>
              {j.etiqueta} · {j.defensiveTeam} vs {j.possessionTeam}
            </option>
          ))}
        </select>
        <button className="rounded bg-emerald-700 px-3 py-1 text-white" onClick={() => (i >= n - 1 ? (setI(0), setPlay(true)) : setPlay(!play))}>
          {play ? 'Pausa' : 'Reproducir'}
        </button>
        <input type="range" min={0} max={Math.max(n - 1, 0)} value={i} onChange={(e) => (setPlay(false), setI(Number(e.target.value)))} className="w-48" />
        <span className="font-mono text-sm">t = {cuadro ? num(cuadro.t, 1) : '—'} s</span>
        <span className={`rounded px-2 py-0.5 text-sm ${presionado ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700'}`}>
          rusher más cercano: {rusherMin == null ? '—' : `${num(rusherMin, 1)} yd`} {presionado ? '· PRESIÓN' : ''}
        </span>
      </div>

      <svg viewBox={`${x0} 0 40 ${ANCHO}`} className="w-full rounded-lg bg-emerald-800" style={{ maxHeight: 420 }}>
        {Array.from({ length: 23 }, (_, k) => 10 + k * 5).map((x) => (
          <line key={x} x1={x} x2={x} y1={0} y2={ANCHO} stroke="white" strokeOpacity={x % 10 === 0 ? 0.5 : 0.2} strokeWidth={0.15} />
        ))}
        {Array.from({ length: 9 }, (_, k) => 20 + k * 10).map((x) => (
          <text key={x} x={x} y={4} fontSize={2} fill="white" fillOpacity={0.5} textAnchor="middle">
            {x <= 60 ? x - 10 : 110 - x}
          </text>
        ))}
        {jugada?.linea_x != null && <line x1={lx} x2={lx} y1={0} y2={ANCHO} stroke="#60a5fa" strokeWidth={0.3} />}
        {qb && <circle cx={qb.x} cy={ANCHO - qb.y} r={UMBRAL} fill={presionado ? '#ef4444' : 'white'} fillOpacity={0.15} stroke={presionado ? '#ef4444' : 'white'} strokeDasharray="0.5 0.4" strokeWidth={0.15} />}
        {cuadro?.jugadores.map((j, k) => (
          <circle key={k} cx={j.x} cy={ANCHO - j.y} r={j.rol === 'Balón' ? 0.4 : 0.8} fill={COLOR[j.rol] ?? '#d1d5db'} stroke="black" strokeWidth={0.1}>
            <title>
              {j.rol} {j.pff_positionLinedUp ?? ''} {j.dist_qb != null ? `· ${num(j.dist_qb, 1)} yd del QB` : ''}
            </title>
          </circle>
        ))}
      </svg>

      <div className="flex flex-wrap gap-3 text-xs text-gray-600">
        {LEYENDA.map(([k, t]) => (
          <span key={k} className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full border border-black" style={{ background: COLOR[k] }} /> {t}
          </span>
        ))}
        <span>Círculo punteado: 2 yardas alrededor del QB (umbral de presión). Línea azul: línea de scrimmage.</span>
      </div>
      {jugada && (
        <p className="text-sm text-gray-700">
          <b>{jugada.down}ª y {jugada.yardsToGo}</b> · {jugada.pff_passCoverage} · {jugada.n_rushers} rushers · presión a los{' '}
          <b>{jugada.ttp == null ? 'no llegó' : `${num(jugada.ttp, 1)} s`}</b> · balón fuera a los {num(jugada.ttt, 1)} s
          <br />
          <span className="text-gray-500">{jugada.playDescription}</span>
        </p>
      )}
    </div>
  )
}
