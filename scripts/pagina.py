"""Datos para la página de entrega. Lee data/processed y escribe en data/processed:

  ranking_semanal.csv      32 defensas x 8 semanas: estadísticas acumuladas, puntuación defensiva y ranking
  escenarios.csv           presión (sí/no) x receptor (abierto/cubierto): success rate permitido
  ridgeline_ttp.csv        densidad del tiempo hasta presión por grupo (rushers, posición, equipo)

Puntuación defensiva (escala T: 50 = promedio de la liga, cada 10 puntos = 1 desviación estándar). Promedio
ponderado de z-scores entre las 32 defensas con las estadísticas acumuladas hasta esa semana:
  success rate permitido (x2, menos es mejor), yardas por dropback (menos), jugadas explosivas (menos),
  presión PFF (más), sacks (más), intercepciones (más).

Receptor abierto: al soltar el balón, al menos la mitad de las rutas tiene >= 3 yardas de separación del defensor
más cercano (columna pct_abiertas de limpieza.py).

Uso: python data/scripts/pagina.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carga  # noqa: E402

OUT = carga.PROCESSED

# (columna, peso, signo): signo +1 si más es mejor para la defensa
COMPONENTES = [
    ("sr_permitido", 2.0, -1),
    ("yardas_dropback", 1.0, -1),
    ("explosivas", 1.0, -1),
    ("presion", 1.0, +1),
    ("sacks", 1.0, +1),
    ("intercepciones", 1.0, +1),
]
POS_GRUPO = {
    **{p: "Interior (DT/NT)" for p in ("DLT", "DRT", "NT", "NLT", "NRT")},
    **{p: "Edge (DE/OLB)" for p in ("LE", "RE", "LEO", "REO", "LOLB", "ROLB")},
    **{p: "Linebacker en blitz" for p in ("LLB", "RLB", "MLB", "LILB", "RILB")},
}
REJILLA = np.round(np.arange(0.5, 5.01, 0.05), 2)
BW = 0.18  # ancho de banda del KDE, en segundos


def puntuacion(t: pd.DataFrame) -> pd.Series:
    z = 0.0
    peso = 0.0
    for col, w, signo in COMPONENTES:
        sd = t[col].std()
        z = z + w * signo * (t[col] - t[col].mean()) / (sd if sd > 0 else 1)
        peso += w
    comp = z / peso
    return 50 + 10 * (comp - comp.mean()) / comp.std()


def ranking_semanal(f: pd.DataFrame) -> pd.DataFrame:
    s = f.groupby(["defensiveTeam", "week"]).agg(
        jugadas=("playId", "size"), exitos=("exito_of", "sum"), yardas=("yardas", "sum"), expl=("explosiva", "sum"),
        pres=("pff_presion", "sum"), sacks_n=("es_sack", "sum"), ints=("es_int", "sum"),
    ).reset_index()
    equipos = sorted(f["defensiveTeam"].unique())
    semanas = sorted(f["week"].unique())
    filas = []
    for w in semanas:
        # acumulado hasta la semana w (los equipos en descanso conservan su acumulado)
        acum = s[s["week"] <= w].groupby("defensiveTeam")[["jugadas", "exitos", "yardas", "expl", "pres", "sacks_n", "ints"]].sum()
        jugo = set(s.loc[s["week"] == w, "defensiveTeam"])
        sem = s[s["week"] == w].set_index("defensiveTeam")
        for nombre, base in (("acumulado", acum), ("semana", sem)):
            t = pd.DataFrame({
                "sr_permitido": base["exitos"] / base["jugadas"],
                "yardas_dropback": base["yardas"] / base["jugadas"],
                "explosivas": base["expl"] / base["jugadas"],
                "presion": base["pres"] / base["jugadas"],
                "sacks": base["sacks_n"] / base["jugadas"],
                "intercepciones": base["ints"] / base["jugadas"],
                "jugadas": base["jugadas"],
            })
            t["puntuacion"] = puntuacion(t)
            t["rank"] = t["puntuacion"].rank(ascending=False, method="min").astype(int)
            t = t.add_suffix(f"_{nombre}")
            filas.append(t.assign(week=w).rename_axis("equipo").reset_index())
        for e in equipos:
            filas.append(pd.DataFrame({"equipo": [e], "week": [w], "jugo": [int(e in jugo)]}))
    r = pd.concat(filas)
    r = r.groupby(["equipo", "week"], as_index=False).first()
    return r.sort_values(["week", "rank_acumulado"])


def escenarios(f: pd.DataFrame) -> pd.DataFrame:
    d = f.dropna(subset=["pct_abiertas"]).copy()
    d["receptor"] = np.where(d["pct_abiertas"] >= 0.5, "Receptor abierto", "Receptor cubierto")
    d["presion_txt"] = np.where(d["pff_presion"].fillna(0) == 1, "Con presión", "Sin presión")
    filas = []
    for sin_sacks in (False, True):
        dd = d[d["es_sack"] == 0] if sin_sacks else d
        for (p, r), g in dd.groupby(["presion_txt", "receptor"]):
            n, k = len(g), g["exito_of"].sum()
            ph = k / n
            se = np.sqrt(ph * (1 - ph) / n)
            filas.append({"excluye_sacks": sin_sacks, "presion": p, "receptor": r, "escenario": f"{p} + {r.lower()}",
                          "jugadas": n, "pct_jugadas": n / len(dd), "success_rate": ph,
                          "ic95_bajo": ph - 1.96 * se, "ic95_alto": ph + 1.96 * se,
                          "yardas": g["yardas"].mean(), "int_rate": g["es_int"].mean(),
                          "explosivas_rate": g["explosiva"].mean(), "sep_media": g["sep_media"].mean()})
    return pd.DataFrame(filas)


def kde(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return np.zeros_like(REJILLA)
    u = (REJILLA[:, None] - x[None, :]) / BW
    dens = np.exp(-0.5 * u**2).sum(axis=1) / (len(x) * BW * np.sqrt(2 * np.pi))
    return dens


def ridgeline(J: pd.DataFrame, R: pd.DataFrame) -> pd.DataFrame:
    J = J[J["ttt"] <= 8]
    filas = []

    def agregar(familia: str, grupo: str, ttp: pd.Series, total: int, orden: float):
        x = ttp.dropna().to_numpy()
        x = x[(x >= 0.5) & (x <= 5.0)]
        for t, v in zip(REJILLA, kde(x)):
            filas.append({"familia": familia, "grupo": grupo, "t": t, "densidad": v, "n_presionadas": len(x),
                          "n_jugadas": total, "pct_presionadas": len(x) / total if total else np.nan,
                          "mediana": float(np.median(x)) if len(x) else np.nan, "orden": orden})

    for k, g in J.groupby("grupo_rushers"):
        agregar("rushers", k, g["ttp"], len(g), {"3 o menos": 0, "4": 1, "5 (blitz)": 2, "6+ (blitz)": 3}.get(k, 9))

    # posición del primer rusher que llega
    llegan = R.dropna(subset=["t_llegada"]).sort_values("t_llegada").groupby(["gameId", "playId"]).head(1).copy()
    llegan["grupo"] = llegan["pff_positionLinedUp"].map(POS_GRUPO).fillna("Secundaria (CB/S)")
    snaps = R.assign(grupo=R["pff_positionLinedUp"].map(POS_GRUPO).fillna("Secundaria (CB/S)")).groupby("grupo").size()
    for k, g in llegan.groupby("grupo"):
        agregar("posicion", k, g["t_llegada"], int(snaps.get(k, 0)), float(g["t_llegada"].median()))

    for k, g in J.groupby("defensiveTeam"):
        agregar("equipo", k, g["ttp"], len(g), float(g["ttp"].median()))
    return pd.DataFrame(filas)


def descomposicion(f: pd.DataFrame) -> pd.DataFrame:
    """¿Qué explica las diferencias ENTRE defensas? SR = p * SR_con + (1 - p) * SR_sin, con p = tasa de presión.
    Contrafactual: se iguala un componente al promedio de la liga y se mide cuánto baja la dispersión (desv. est.)
    del success rate permitido entre las 32 defensas."""
    f = f.assign(pres=f["pff_presion"].fillna(0))
    g = f.groupby("defensiveTeam")
    p = g["pres"].mean()
    sc = f[f["pres"] == 1].groupby("defensiveTeam")["exito_of"].mean()
    ss = f[f["pres"] == 0].groupby("defensiveTeam")["exito_of"].mean()
    sr = p * sc + (1 - p) * ss
    base = sr.std()
    casos = {
        "Real": sr,
        "Todos con la presión promedio": p.mean() * sc + (1 - p.mean()) * ss,
        "Todos con la cobertura promedio sin presión": p * sc + (1 - p) * ss.mean(),
        "Todos con el resultado promedio bajo presión": p * sc.mean() + (1 - p) * ss,
    }
    return pd.DataFrame([{"escenario": k, "desv_est_sr": v.std(), "reduccion_pct": 1 - v.std() / base} for k, v in casos.items()])


def main() -> None:
    f = pd.read_csv(OUT / "plays_features.csv")
    dsc = descomposicion(f)
    dsc.to_csv(OUT / "descomposicion_equipos.csv", index=False)
    print(dsc.round(4).to_string(index=False))
    rs = ranking_semanal(f)
    rs.to_csv(OUT / "ranking_semanal.csv", index=False)
    esc = escenarios(f)
    esc.to_csv(OUT / "escenarios.csv", index=False)
    J = pd.read_csv(OUT / "plays_ttp.csv")
    R = pd.read_csv(OUT / "rushers_jugada.csv")
    rl = ridgeline(J, R)
    rl.to_csv(OUT / "ridgeline_ttp.csv", index=False)

    pd.set_option("display.width", 200)
    print(esc.round(3).to_string(index=False))
    fin = rs[rs["week"] == rs["week"].max()].sort_values("rank_acumulado")
    print(fin[["equipo", "rank_acumulado", "puntuacion_acumulado", "sr_permitido_acumulado", "presion_acumulado"]].head(6).round(3).to_string(index=False))
    print(fin[["equipo", "rank_acumulado", "puntuacion_acumulado", "sr_permitido_acumulado", "presion_acumulado"]].tail(4).round(3).to_string(index=False))
    print("corr puntuación vs SR:", round(fin["puntuacion_acumulado"].corr(fin["sr_permitido_acumulado"]), 3))
    resumen = rl.groupby(["familia", "grupo"])[["n_presionadas", "n_jugadas", "pct_presionadas", "mediana"]].first().round(3)
    print(resumen.loc[["rushers", "posicion"]].to_string())


if __name__ == "__main__":
    main()
