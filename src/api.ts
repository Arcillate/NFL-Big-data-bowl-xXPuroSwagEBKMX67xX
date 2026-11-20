// Rutas relativas SIN diagonal inicial: la app se publica en una subruta (/evento/equipo/).
import { useEffect, useState } from 'react'

// En GitHub Pages no hay servidor: `npm run build:pages` compila en modo 'pages' y cada ruta se lee de un JSON
// exportado por data/scripts/exportar_estatico.py (misma regla de nombres que allá).
const ESTATICO = import.meta.env.MODE === 'pages'
const archivo = (ruta: string) => (ESTATICO ? ruta.replace('?', '__').replace(/[=&]/g, '-') + '.json' : ruta)

export async function getJSON<T>(ruta: string): Promise<T> {
  const r = await fetch(`api/${archivo(ruta)}`)
  if (!r.ok) throw new Error(`${r.status} en api/${ruta}`)
  return r.json() as Promise<T>
}

export function useApi<T>(ruta: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!ruta) return
    let vivo = true
    setError(null)
    getJSON<T>(ruta)
      .then((d) => vivo && setData(d))
      .catch((e: Error) => vivo && setError(e.message))
    return () => {
      vivo = false
    }
  }, [ruta])
  return { data, error }
}

export const pct = (v: number | null | undefined, dec = 1) => (v == null ? '—' : `${(v * 100).toFixed(dec)}%`)
export const num = (v: number | null | undefined, dec = 2) => (v == null ? '—' : v.toFixed(dec))

// ---- tipos de la API
export interface Resumen {
  jugadas: number
  partidos: number
  equipos: number
  semanas: [number, number]
  sr_con_presion: number
  sr_sin_presion: number
  sr_con_presion_sin_sacks: number
  sr_sin_presion_sin_sacks: number
  r_sacks: number
  r_presion: number
  r_blitz: number
  mejor: Ranking
  peor: Ranking
}

export interface Ranking {
  rank: number
  equipo: string
  jugadas: number
  partidos: number
  success_rate_permitido: number
  presion_rate: number
  sack_rate: number
  blitz_rate: number
  rushers_medio: number
  man_rate: number
  int_rate: number
  yardas_permitidas: number
  explosivas_rate: number
  sr_con_presion: number
  sr_sin_presion: number
  sr_ic95_bajo: number
  sr_ic95_alto: number
  cobertura_top: string
}

export interface Standing {
  equipo: string
  week: number
  jugadas: number
  sr_semana: number
  presion_semana: number
  sr_acumulado: number
  rank_acumulado: number
}

export interface CeldaMatriz {
  nivel: 'tipo' | 'cobertura' | 'total'
  cobertura: string
  presion: 'Con presión' | 'Sin presión'
  jugadas: number
  success_rate: number
  ic95_bajo: number
  ic95_alto: number
  yardas: number
  int_rate: number
  explosivas_rate: number
}

export interface Interaccion {
  excluye_sacks: boolean
  contraste: string
  puntos_sr: number
  ic95_bajo: number
  ic95_alto: number
}

export interface GrupoTTP {
  grupo: string
  jugadas: number
  presion_trk_rate: number
  p_presion_2s: number
  p_presion_2_5s: number
  p_presion_3s: number
  mediana_km_s: number | null
  ttt_medio: number
  success_rate_permitido: number
}

export interface EquipoTTP {
  equipo: string
  rank: number
  p_presion_2_5s: number
  p_presion_2_5s_con_4: number
  success_rate_permitido: number
  blitz_rate: number
  presion_rate: number
  ttt_medio: number
}

export interface PosicionTTP {
  pff_positionLinedUp: string
  snaps_rush: number
  tasa_llegada: number
  tasa_llegada_rapida: number
  t_llegada_mediana: number | null
  dist_snap_media: number
}

export interface Rusher {
  nflId: number
  displayName: string
  officialPosition: string
  equipo: string
  posicion_top: string
  snaps_rush: number
  llegadas: number
  llegadas_rapidas: number
  llegadas_rapidas_por_100: number
  t_llegada_mediana: number | null
  presiones_pff: number
}

export interface PerfilEquipo {
  equipo: string
  ranking: Ranking
  matriz: { cobertura: string; presion: string; success_rate: number; jugadas: number }[]
  coberturas: { cobertura: string; pct: number }[]
  semanas: Standing[]
  ttp: (GrupoTTP & { p_presion_2_5s_con_4: number }) | null
  rusher_mas_rapido: Rusher | null
}

export interface AnimIndice {
  gameId: number
  playId: number
  etiqueta: string
  playDescription: string
  possessionTeam: string
  defensiveTeam: string
  down: number
  yardsToGo: number
  pff_passCoverage: string
  passResult: string
  ttp: number | null
  ttt: number
  n_rushers: number
  linea_x: number | null
}

export interface Jugador {
  nflId: number | null
  team: string
  rol: string
  pff_positionLinedUp: string | null
  x: number
  y: number
  dist_qb: number | null
}

export interface Animacion {
  info: AnimIndice | null
  cuadros: { frameId: number; t: number; evento: string | null; jugadores: Jugador[] }[]
}
