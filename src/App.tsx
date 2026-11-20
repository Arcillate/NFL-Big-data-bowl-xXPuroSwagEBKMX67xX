import { ReactNode } from 'react'
import { Resumen, pct, useApi } from './api'
import Campo from './components/Campo'
import Comparacion from './components/Comparacion'
import Dispersion, { Descomposicion } from './components/Dispersion'
import Escenarios from './components/Escenarios'
import Matriz from './components/Matriz'
import RankingSemanal from './components/RankingSemanal'
import Ridgeline from './components/Ridgeline'
import TiempoPresion from './components/TiempoPresion'

const NAV: [string, string][] = [
  ['respuesta', 'Respuesta'],
  ['ranking', 'Ranking'],
  ['escenarios', 'Escenarios'],
  ['matriz', 'Coberturas'],
  ['dispersion', 'Equipos'],
  ['tiempo', 'Tiempo a presión'],
  ['comparar', 'BUF vs IND'],
  ['jugada', 'Jugada'],
  ['metodo', 'Método'],
]

function Seccion({ id, n, titulo, idea, children }: { id: string; n: number; titulo: string; idea: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 md:p-8">
      <p className="text-xs font-bold uppercase tracking-widest text-emerald-700">{String(n).padStart(2, '0')}</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900 md:text-3xl">{titulo}</h2>
      <p className="mt-2 max-w-4xl text-slate-600">{idea}</p>
      <div className="mt-6">{children}</div>
    </section>
  )
}

function Hallazgo({ n, titulo, texto }: { n: number; titulo: string; texto: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white/10 p-5 ring-1 ring-white/15 backdrop-blur">
      <p className="text-sm font-bold text-emerald-300">{n}</p>
      <p className="mt-1 font-semibold text-white">{titulo}</p>
      <p className="mt-1 text-sm leading-relaxed text-slate-200">{texto}</p>
    </div>
  )
}

export default function App() {
  const { data: r, error } = useApi<Resumen>('resumen')
  const efecto = r ? Math.round((r.sr_sin_presion - r.sr_con_presion) * 100) : 23

  return (
    <div className="min-h-screen bg-slate-100 font-sans text-slate-900 antialiased">
      <header className="relative overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-emerald-950 text-white">
        <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.07]" preserveAspectRatio="none" viewBox="0 0 100 50">
          {Array.from({ length: 11 }, (_, i) => (
            <line key={i} x1={i * 10} x2={i * 10} y1={0} y2={50} stroke="white" strokeWidth={0.3} />
          ))}
        </svg>
        <div className="relative mx-auto max-w-7xl px-6 pb-14 pt-12">
          <p className="text-sm font-semibold uppercase tracking-widest text-emerald-300">NFL Big Data Bowl · Scouting defensivo</p>
          <h1 className="mt-3 max-w-4xl text-4xl font-extrabold leading-tight md:text-6xl">
            ¿Presionar al QB <span className="text-slate-400">o</span> cubrir bien a los receptores?
          </h1>
          {error && <p className="mt-4 rounded bg-rose-500/20 p-2 text-rose-100">No se pudo conectar con la API: {error}</p>}
          <p className="mt-5 max-w-3xl text-lg text-slate-300">
            {r ? `${r.jugadas.toLocaleString()} dropbacks, ${r.partidos} partidos y ${r.equipos} defensas` : '8,557 dropbacks, 122 partidos y 32 defensas'} de las semanas 1 a 8 de 2021,
            con datos de PFF y tracking de Next Gen Stats.
          </p>

          <div id="respuesta" className="mt-10 scroll-mt-24">
            <div className="flex flex-wrap items-end gap-6">
              <div>
                <p className="text-sm uppercase tracking-wide text-slate-400">Success rate permitido</p>
                <p className="text-5xl font-extrabold">
                  <span className="text-rose-400">{pct(r?.sr_sin_presion ?? 0.573, 0)}</span>
                  <span className="mx-3 text-3xl text-slate-500">→</span>
                  <span className="text-emerald-400">{pct(r?.sr_con_presion ?? 0.344, 0)}</span>
                </p>
                <p className="text-sm text-slate-400">sin presión → con presión</p>
              </div>
              <p className="max-w-xl pb-2 text-xl font-semibold text-white">
                En cada jugada, la presión vale más que la cobertura: baja el éxito ofensivo {efecto} puntos. Entre equipos, lo que más separa a las mejores defensas es cómo cubren
                cuando la presión no llega.
              </p>
            </div>
            <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <Hallazgo n={1} titulo="La presión domina la jugada" texto={`Con presión, todas las coberturas permiten entre 31% y 37%. Sin presión, entre 54% y 63%.`} />
              <Hallazgo
                n={2}
                titulo="La cobertura separa a los equipos"
                texto="Todas las defensas presionan entre 32% y 44%. Igualar su cobertura sin presión borraría 40% de la diferencia entre ellas; igualar su presión, solo 5%."
              />
              <Hallazgo
                n={3}
                titulo="Mandar no es llegar"
                texto={r ? `Entre las 32 defensas, presión r = ${r.r_presion.toFixed(2)} y sacks r = ${r.r_sacks.toFixed(2)} con el SR permitido; blitz r = ${r.r_blitz.toFixed(2)}.` : 'Presión r = −0.36, sacks r = −0.41, blitz r = −0.02.'}
              />
              <Hallazgo n={4} titulo="Rápido no es mejor" texto="El blitz acelera la presión (20% contra 13% antes de 2.5 s), pero el QB también suelta antes: el SR permitido es el mismo." />
            </div>
          </div>
        </div>
      </header>

      <nav className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4">
          {NAV.map(([id, t]) => (
            <a key={id} href={`#${id}`} className="whitespace-nowrap px-3 py-3 text-sm font-medium text-slate-600 hover:text-emerald-700">
              {t}
            </a>
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-7xl space-y-8 px-4 py-10 md:px-6">
        <Seccion
          id="ranking"
          n={1}
          titulo="Ranking defensivo, semana 1 a 8"
          idea="Las 32 defensas puntuadas con seis estadísticas contra el pase. Buffalo es la #1 desde la semana 3 y termina con 73.8 puntos, casi 10 más que la segunda (Minnesota). Detroit cierra última."
        >
          <RankingSemanal />
        </Seccion>

        <Seccion
          id="escenarios"
          n={2}
          titulo="Cuatro escenarios: presión y cobertura"
          idea="Separamos cada dropback por dos preguntas: ¿llegó la presión? y ¿los receptores estaban cubiertos al soltar el balón? La altura de las barras la decide la presión, no la cobertura."
        >
          <Escenarios />
        </Seccion>

        <Seccion
          id="matriz"
          n={3}
          titulo="Presión × tipo de cobertura"
          idea="La zona sin presión es la peor combinación grande (58% de éxito ofensivo) y Cover-3 sin presión, la jugada más común, permite 60%. La man no depende más de la presión que la zona: la presión ayuda igual a las dos."
        >
          <Matriz />
        </Seccion>

        <Seccion
          id="dispersion"
          n={4}
          titulo="¿Qué separa a las mejores defensas?"
          idea="Cada punto es una defensa. Presionar y sacar al QB se relaciona con permitir menos y blitzear no. Pero la variable que más separa a los equipos es su success rate cuando no hay presión: la calidad de la cobertura."
        >
          <div className="space-y-10">
            <Dispersion />
            <div>
              <h3 className="text-lg font-semibold text-slate-800">¿Qué explica las diferencias entre defensas?</h3>
              <p className="mb-3 text-sm text-slate-500">Cuánto bajaría la diferencia de success rate entre las 32 defensas si todas fueran iguales en un componente.</p>
              <Descomposicion />
            </div>
          </div>
        </Seccion>

        <Seccion
          id="tiempo"
          n={5}
          titulo="Tiempo hasta presión"
          idea="Métrica propia con el tracking: segundos desde el snap hasta que un rusher queda a 2 yardas o menos del QB. El blitz y los linebackers llegan antes, pero llegar antes no mejora el resultado de la jugada."
        >
          <div className="space-y-10">
            <Ridgeline />
            <TiempoPresion />
          </div>
        </Seccion>

        <Seccion
          id="comparar"
          n={6}
          titulo="La mejor contra la peor"
          idea="Buffalo (41.8%) e Indianapolis (57.3%) blitzean casi lo mismo (16% y 18%). De sus 15.5 puntos de diferencia, 2.2 vienen de que Buffalo presiona más (43% contra 33%), 7.7 de cómo cubren cuando no hay presión y 5.6 de qué tan bien terminan cuando sí la hay."
        >
          <Comparacion />
        </Seccion>

        <Seccion id="jugada" n={7} titulo="Así llega la presión" idea="Jugadas reales en coordenadas normalizadas (la ofensiva siempre ataca hacia la derecha). El círculo marca 2 yardas alrededor del QB y se pone rojo cuando entra un rusher.">
          <Campo />
        </Seccion>

        <section id="metodo" className="scroll-mt-20 rounded-3xl bg-slate-900 p-6 text-slate-300 md:p-8">
          <h2 className="text-2xl font-bold text-white">Método y limitaciones</h2>
          <div className="mt-4 grid gap-6 text-sm leading-relaxed md:grid-cols-3">
            <div>
              <p className="font-semibold text-white">Definiciones</p>
              <p className="mt-1">
                <b>Success rate</b>: la jugada gana ≥ 40% de las yardas por ganar en 1ª, ≥ 60% en 2ª y 100% en 3ª/4ª; una intercepción siempre es fracaso. <b>Presión</b>: hit, hurry o
                sack según PFF. <b>Blitz</b>: 5 o más pass rushers. <b>Receptor abierto</b>: al menos la mitad de las rutas con 3+ yardas de separación al soltar.
              </p>
            </div>
            <div>
              <p className="font-semibold text-white">Tiempo hasta presión</p>
              <p className="mt-1">
                Umbral de 2 yardas calibrado contra PFF (82% de acuerdo). La llegada cuenta después de 0.5 s y solo si el rusher empezó a más de 2 yardas. Si el QB lanza antes, la
                jugada se trata como censurada (curvas de Kaplan-Meier).
              </p>
            </div>
            <div>
              <p className="font-semibold text-white">Limitaciones</p>
              <p className="mt-1">
                Solo hay dropbacks: es defensa contra el pase. Son asociaciones, no causas: una jugada larga da tiempo a la presión y a los receptores. Cada equipo tiene 7 a 8
                partidos, así que las diferencias entre equipos tienen intervalos amplios.
              </p>
            </div>
          </div>
          <p className="mt-6 text-xs text-slate-500">Datos: NFL Big Data Bowl (Next Gen Stats y Pro Football Focus). Hecho con pandas, FastAPI, React y Recharts.</p>
        </section>
      </main>
    </div>
  )
}
