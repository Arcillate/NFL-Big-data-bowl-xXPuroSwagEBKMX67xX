"""API del scouting report defensivo: ¿presionar al QB o cubrir bien?

Sirve los resultados precalculados en data/processed (scripts en data/scripts). Solo lee archivos; no escribe nada.
Ejecuta: .venv/Scripts/uvicorn backend.main:app --reload
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "data" / "processed"
DIST = RAIZ / "dashboard" / "dist"

app = FastAPI(title="Scouting defensivo NFL: presión vs cobertura")


# ----------------------------------------------------------------- utilidades
@lru_cache(maxsize=None)
def tabla(nombre: str) -> pd.DataFrame:
    ruta = PROC / f"{nombre}.csv"
    if not ruta.exists():
        raise HTTPException(503, f"Falta data/processed/{nombre}.csv. Corre los scripts de data/scripts.")
    return pd.read_csv(ruta)


def registros(df: pd.DataFrame, dec: int = 4) -> list[dict]:
    """DataFrame a lista de dicts JSON (NaN -> null, flotantes redondeados)."""
    d = df.copy()
    for c in d.select_dtypes("float").columns:
        d[c] = d[c].round(dec)
    return d.astype(object).where(d.notna(), None).to_dict(orient="records")


@lru_cache(maxsize=1)
def jugadas() -> pd.DataFrame:
    cols = ["gameId", "playId", "week", "defensiveTeam", "possessionTeam", "tipo_cobertura", "cobertura",
            "pff_presion", "blitz", "n_rushers", "exito_of", "es_sack"]
    f = tabla("plays_features")[cols].copy()
    f["presion"] = np.where(f["pff_presion"].fillna(0) == 1, "Con presión", "Sin presión")
    return f


def equipo_valido(abbr: str) -> str:
    abbr = abbr.upper()
    if abbr not in set(tabla("ranking_defensas")["equipo"]):
        raise HTTPException(404, f"Equipo desconocido: {abbr}")
    return abbr


# ----------------------------------------------------------------- endpoints
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/resumen")
def resumen() -> dict:
    """Cifras clave para la portada."""
    m = tabla("matriz_presion_cobertura")
    tot = m[(m["nivel"] == "total") & (~m["excluye_sacks"])].set_index("presion")["success_rate"]
    tot_ns = m[(m["nivel"] == "total") & (m["excluye_sacks"])].set_index("presion")["success_rate"]
    c = tabla("correlaciones_equipo").set_index("metrica")["pearson_vs_sr_permitido"]
    r = tabla("ranking_defensas")
    f = jugadas()
    return {
        "jugadas": int(len(f)), "partidos": int(f["gameId"].nunique()), "equipos": int(f["defensiveTeam"].nunique()),
        "semanas": [int(f["week"].min()), int(f["week"].max())],
        "sr_con_presion": float(tot["Con presión"]), "sr_sin_presion": float(tot["Sin presión"]),
        "sr_con_presion_sin_sacks": float(tot_ns["Con presión"]), "sr_sin_presion_sin_sacks": float(tot_ns["Sin presión"]),
        "r_sacks": float(c["sack_rate"]), "r_presion": float(c["presion_rate"]), "r_blitz": float(c["blitz_rate"]),
        "mejor": registros(r.head(1))[0], "peor": registros(r.tail(1))[0],
    }


@app.get("/api/ranking")
def ranking() -> list[dict]:
    return registros(tabla("ranking_defensas"))


@app.get("/api/standings")
def standings() -> list[dict]:
    return registros(tabla("standings_semanales"))


@app.get("/api/matriz")
def matriz(excluye_sacks: bool = False) -> list[dict]:
    m = tabla("matriz_presion_cobertura")
    return registros(m[m["excluye_sacks"] == excluye_sacks].drop(columns="excluye_sacks"))


@app.get("/api/interaccion")
def interaccion() -> list[dict]:
    return registros(tabla("interaccion_presion"))


@app.get("/api/correlaciones")
def correlaciones() -> list[dict]:
    return registros(tabla("correlaciones_equipo"))


@app.get("/api/calibracion")
def calibracion() -> list[dict]:
    return registros(tabla("calibracion_umbral"))


@app.get("/api/equipos")
def equipos() -> list[str]:
    return sorted(tabla("ranking_defensas")["equipo"].tolist())


@app.get("/api/equipo/{abbr}")
def equipo(abbr: str) -> dict:
    """Perfil de una defensa: ranking, matriz propia, mezcla de coberturas, semanas, tiempo hasta presión."""
    abbr = equipo_valido(abbr)
    f = jugadas()
    d = f[f["defensiveTeam"] == abbr]
    mat = (d[d["tipo_cobertura"].isin(["Man", "Zone"])].groupby(["tipo_cobertura", "presion"])["exito_of"]
           .agg(success_rate="mean", jugadas="size").reset_index().rename(columns={"tipo_cobertura": "cobertura"}))
    mezcla = d["cobertura"].value_counts(normalize=True).rename_axis("cobertura").reset_index(name="pct")
    ttp = tabla("ttp_equipos")
    rusher = tabla("rusher_mas_rapido")
    return {
        "equipo": abbr,
        "ranking": registros(tabla("ranking_defensas").query("equipo == @abbr"))[0],
        "matriz": registros(mat),
        "coberturas": registros(mezcla),
        "semanas": registros(tabla("standings_semanales").query("equipo == @abbr")),
        "ttp": (registros(ttp.query("equipo == @abbr")) or [None])[0],
        "rusher_mas_rapido": (registros(rusher.query("equipo == @abbr")) or [None])[0],
    }


@app.get("/api/ttp/curvas")
def ttp_curvas(grupos: str = Query("Todas,4 rushers,5 (blitz) rushers,6+ (blitz) rushers")) -> list[dict]:
    """Curvas Kaplan-Meier: % de jugadas ya presionadas a cada segundo. Formato ancho para Recharts."""
    c = tabla("curvas_ttp")
    pedidos = [g.strip() for g in grupos.split(",") if g.strip()]
    c = c[c["grupo"].isin(pedidos)]
    ancho = c.pivot_table(index="t", columns="grupo", values="p_presionada").reset_index()
    return registros(ancho)


@app.get("/api/ttp/grupos")
def ttp_grupos() -> list[dict]:
    return registros(tabla("resumen_ttp_grupos"))


@app.get("/api/ttp/equipos")
def ttp_equipos() -> list[dict]:
    t = tabla("ttp_equipos").merge(tabla("ranking_defensas")[["equipo", "rank", "blitz_rate", "presion_rate"]], on="equipo")
    return registros(t)


@app.get("/api/ttp/posiciones")
def ttp_posiciones() -> list[dict]:
    return registros(tabla("ttp_posiciones"))


@app.get("/api/ttp/rushers")
def ttp_rushers(limite: int = Query(25, ge=1, le=200), equipo: str | None = None) -> list[dict]:
    r = tabla("rushers_ranking")
    if equipo:
        r = r[r["equipo"] == equipo_valido(equipo)]
    return registros(r.head(limite))


@app.get("/api/ttp/mas-rapidos")
def ttp_mas_rapidos() -> list[dict]:
    return registros(tabla("rusher_mas_rapido"))


@app.get("/api/animaciones")
def animaciones() -> list[dict]:
    return registros(tabla("animaciones_indice"))


@app.get("/api/animaciones/{game_id}/{play_id}")
def animacion(game_id: int, play_id: int) -> dict:
    """Cuadros de una jugada con coordenadas normalizadas (la ofensiva siempre ataca hacia la derecha)."""
    a = tabla("animaciones")
    p = a[(a["gameId"] == game_id) & (a["playId"] == play_id)]
    if p.empty:
        raise HTTPException(404, "Jugada sin animación precalculada")
    info = tabla("animaciones_indice").query("gameId == @game_id and playId == @play_id")
    cuadros = [{"frameId": int(fid), "t": float(g["t"].iloc[0]),
                "evento": next((e for e in g["event"].dropna().astype(str) if e != "None"), None),
                "jugadores": registros(g[["nflId", "team", "rol", "pff_positionLinedUp", "x", "y", "dist_qb"]], 2)}
               for fid, g in p.sort_values("frameId").groupby("frameId")]
    return {"info": registros(info)[0] if len(info) else None, "cuadros": cuadros}


# ----------------------------------------------------------------- página de entrega
@app.get("/api/ranking-semanal")
def ranking_semanal() -> list[dict]:
    """32 defensas x 8 semanas: puntuación defensiva y ranking (acumulado y de la semana)."""
    return registros(tabla("ranking_semanal"))


@app.get("/api/escenarios")
def escenarios(excluye_sacks: bool = False) -> list[dict]:
    e = tabla("escenarios")
    return registros(e[e["excluye_sacks"] == excluye_sacks].drop(columns="excluye_sacks"))


@app.get("/api/ridgeline")
def ridgeline(familia: str = Query("rushers", pattern="^(rushers|posicion|equipo)$")) -> list[dict]:
    """Densidad del tiempo hasta presión por grupo, en formato largo (grupo, t, densidad)."""
    r = tabla("ridgeline_ttp")
    return registros(r[r["familia"] == familia].drop(columns="familia"))


VARIABLES_X = {
    "presion_rate": "Presión (PFF), % de dropbacks",
    "sack_rate": "Sacks, % de dropbacks",
    "blitz_rate": "Blitz (5+ rushers), % de dropbacks",
    "p_presion_2_5s": "Presionadas antes de 2.5 s (tracking)",
    "man_rate": "Man coverage, % de dropbacks",
    "sr_sin_presion": "SR permitido cuando no hay presión (calidad de cobertura)",
}


@app.get("/api/dispersion")
def dispersion(x: str = Query("presion_rate")) -> dict:
    """Equipos (x, success rate permitido) con recta de mínimos cuadrados, r, R² y pendiente."""
    if x not in VARIABLES_X:
        raise HTTPException(400, f"x debe ser una de: {', '.join(VARIABLES_X)}")
    t = tabla("ranking_defensas").merge(tabla("ttp_equipos")[["equipo", "p_presion_2_5s"]], on="equipo", how="left")
    d = t[["equipo", "rank", x, "success_rate_permitido"]].dropna()
    xs, ys = d[x].to_numpy(float), d["success_rate_permitido"].to_numpy(float)
    pendiente, intercepto = np.polyfit(xs, ys, 1)
    r = float(np.corrcoef(xs, ys)[0, 1])
    x0, x1 = float(xs.min()), float(xs.max())
    return {
        "x": x, "etiqueta_x": VARIABLES_X[x], "variables": VARIABLES_X,
        "puntos": registros(d.rename(columns={x: "valor_x", "success_rate_permitido": "valor_y"})),
        "recta": [{"valor_x": x0, "recta": float(intercepto + pendiente * x0)}, {"valor_x": x1, "recta": float(intercepto + pendiente * x1)}],
        "pendiente": float(pendiente), "intercepto": float(intercepto), "r": r, "r2": r**2, "n": int(len(d)),
    }


@app.get("/api/descomposicion")
def descomposicion() -> list[dict]:
    """Cuánto bajaría la dispersión del SR permitido entre equipos si se igualara cada componente."""
    return registros(tabla("descomposicion_equipos"))


# El build del dashboard se sirve en la misma URL que la API (se monta al final para no tapar /api).
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="dashboard")
