"""¿Qué le funciona más a una defensa contra el pase: presionar al QB o cubrir bien?

Lee data/processed/plays_features.csv (salida de limpieza.py) y escribe en data/processed:
  ranking_defensas.csv          32 defensas: success rate permitido, presión, sacks, blitz, man%
  standings_semanales.csv       success rate permitido por semana y acumulado, con ranking acumulado
  matriz_presion_cobertura.csv  presión (sí/no) x cobertura: success rate permitido, n, IC95
  interaccion_presion.csv       ¿la man depende más de la presión que la zona? (diferencia de diferencias)
  correlaciones_equipo.csv      success rate permitido vs presión, sacks, blitz (32 defensas)
  calibracion_umbral.csv        umbral de distancia del tracking vs presión PFF

Success rate (éxito ofensivo): la jugada gana >= 40% de las yardas por ganar en 1a, >= 60% en 2a, 100% en 3a/4a.
Una intercepción siempre es fracaso. Un success rate permitido más bajo es mejor defensa.

Uso: python data/scripts/presion_cobertura.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carga  # noqa: E402

OUT = carga.PROCESSED
SEMILLA = 2021
Z95 = 1.959964
COBERTURAS_PRINCIPALES = ["Cover-0", "Cover-1", "2-Man", "Cover-2", "Cover-3", "Quarters", "Cover-6"]


def wilson(k: np.ndarray, n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Intervalo de Wilson al 95% para una proporción."""
    k, n = np.asarray(k, float), np.asarray(n, float)
    p = np.where(n > 0, k / np.maximum(n, 1), np.nan)
    den = 1 + Z95**2 / n
    centro = (p + Z95**2 / (2 * n)) / den
    medio = Z95 * np.sqrt(p * (1 - p) / n + Z95**2 / (4 * n**2)) / den
    return centro - medio, centro + medio


def cargar() -> pd.DataFrame:
    f = pd.read_csv(OUT / "plays_features.csv")
    f["presion"] = f["pff_presion"].fillna(0).astype(int)
    f["presion_txt"] = np.where(f["presion"] == 1, "Con presión", "Sin presión")
    return f


# ----------------------------------------------------------------- ranking y standings
def ranking_defensas(f: pd.DataFrame) -> pd.DataFrame:
    g = f.groupby("defensiveTeam")
    r = pd.DataFrame({
        "jugadas": g.size(),
        "partidos": g["gameId"].nunique(),
        "success_rate_permitido": g["exito_of"].mean(),
        "presion_rate": g["presion"].mean(),
        "sack_rate": g["es_sack"].mean(),
        "blitz_rate": g["blitz"].mean(),
        "rushers_medio": g["n_rushers"].mean(),
        "man_rate": g["tipo_cobertura"].apply(lambda s: (s == "Man").mean()),
        "int_rate": g["es_int"].mean(),
        "yardas_permitidas": g["yardas"].mean(),
        "explosivas_rate": g["explosiva"].mean(),
        # success rate permitido según haya o no presión: separa pass rush de cobertura
        "sr_con_presion": f[f["presion"] == 1].groupby("defensiveTeam")["exito_of"].mean(),
        "sr_sin_presion": f[f["presion"] == 0].groupby("defensiveTeam")["exito_of"].mean(),
    })
    lo, hi = wilson(g["exito_of"].sum(), r["jugadas"])
    r["sr_ic95_bajo"], r["sr_ic95_alto"] = lo, hi
    r["cobertura_top"] = f.groupby("defensiveTeam")["cobertura"].agg(lambda s: s.mode().iat[0])
    r = r.sort_values("success_rate_permitido").reset_index().rename(columns={"defensiveTeam": "equipo"})
    r.insert(0, "rank", np.arange(1, len(r) + 1))
    return r


def standings_semanales(f: pd.DataFrame) -> pd.DataFrame:
    s = f.groupby(["defensiveTeam", "week"]).agg(jugadas=("playId", "size"), exitos=("exito_of", "sum"),
                                                presiones=("presion", "sum")).reset_index()
    s = s.sort_values(["defensiveTeam", "week"])
    s["sr_semana"] = s["exitos"] / s["jugadas"]
    s["presion_semana"] = s["presiones"] / s["jugadas"]
    s["sr_acumulado"] = s.groupby("defensiveTeam")["exitos"].cumsum() / s.groupby("defensiveTeam")["jugadas"].cumsum()
    # ranking acumulado por semana. Equipos en semana de descanso conservan su acumulado anterior.
    filas = []
    for w in sorted(s["week"].unique()):
        hasta = s[s["week"] <= w].groupby("defensiveTeam").tail(1)[["defensiveTeam", "sr_acumulado"]]
        hasta = hasta.assign(week=w, rank_acumulado=hasta["sr_acumulado"].rank(method="min").astype(int))
        filas.append(hasta[["defensiveTeam", "week", "rank_acumulado"]])
    s = s.merge(pd.concat(filas), on=["defensiveTeam", "week"], how="left")
    return s.rename(columns={"defensiveTeam": "equipo"}).drop(columns=["exitos", "presiones"])


# ----------------------------------------------------------------- matriz presión x cobertura
def celda(d: pd.DataFrame) -> pd.Series:
    n, k = len(d), d["exito_of"].sum()
    lo, hi = wilson(k, n)
    return pd.Series({"jugadas": n, "success_rate": k / n if n else np.nan, "ic95_bajo": float(lo), "ic95_alto": float(hi),
                      "yardas": d["yardas"].mean(), "int_rate": d["es_int"].mean(), "explosivas_rate": d["explosiva"].mean()})


def matriz(f: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for sin_sacks in (False, True):
        d0 = f[f["es_sack"] == 0] if sin_sacks else f
        for nivel, col, valores in (("tipo", "tipo_cobertura", ["Man", "Zone"]), ("cobertura", "cobertura", COBERTURAS_PRINCIPALES)):
            for v in valores:
                for p in (1, 0):
                    c = celda(d0[(d0[col] == v) & (d0["presion"] == p)])
                    filas.append({"excluye_sacks": sin_sacks, "nivel": nivel, "cobertura": v,
                                  "presion": "Con presión" if p else "Sin presión", **c.to_dict()})
        for p in (1, 0):
            c = celda(d0[d0["presion"] == p])
            filas.append({"excluye_sacks": sin_sacks, "nivel": "total", "cobertura": "Todas",
                          "presion": "Con presión" if p else "Sin presión", **c.to_dict()})
    return pd.DataFrame(filas)


def interaccion(f: pd.DataFrame, B: int = 2000) -> pd.DataFrame:
    """Efecto de la presión (SR sin presión - SR con presión) en man y en zona, y su diferencia, con IC bootstrap
    remuestreando partidos completos (las jugadas de un mismo partido no son independientes)."""
    rng = np.random.default_rng(SEMILLA)
    filas = []
    for sin_sacks in (False, True):
        d = f[f["tipo_cobertura"].isin(["Man", "Zone"])]
        if sin_sacks:
            d = d[d["es_sack"] == 0]
        # sumas por partido y celda para un bootstrap rápido
        agg = d.groupby(["gameId", "tipo_cobertura", "presion"])["exito_of"].agg(["sum", "count"]).unstack(["tipo_cobertura", "presion"], fill_value=0)
        juegos = agg.index.to_numpy()

        def efectos(idx):
            t = agg.iloc[idx].sum()
            sr = {(c, p): t[("sum", c, p)] / t[("count", c, p)] for c in ("Man", "Zone") for p in (0, 1)}
            em, ez = sr[("Man", 0)] - sr[("Man", 1)], sr[("Zone", 0)] - sr[("Zone", 1)]
            return np.array([em, ez, em - ez, sr[("Man", 0)] - sr[("Zone", 0)], sr[("Man", 1)] - sr[("Zone", 1)]])

        base = efectos(np.arange(len(juegos)))
        bs = np.array([efectos(rng.integers(0, len(juegos), len(juegos))) for _ in range(B)])
        lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
        nombres = ["efecto presión en Man", "efecto presión en Zone", "diferencia (Man - Zone)",
                   "Man - Zone sin presión", "Man - Zone con presión"]
        for i, nm in enumerate(nombres):
            filas.append({"excluye_sacks": sin_sacks, "contraste": nm, "puntos_sr": base[i] * 100,
                          "ic95_bajo": lo[i] * 100, "ic95_alto": hi[i] * 100})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------- equipo y calibración
def correlaciones(r: pd.DataFrame, B: int = 2000) -> pd.DataFrame:
    rng = np.random.default_rng(SEMILLA)
    filas = []
    for m in ["sack_rate", "presion_rate", "blitz_rate", "rushers_medio", "man_rate", "int_rate"]:
        x, y = r[m].to_numpy(), r["success_rate_permitido"].to_numpy()
        rr = np.corrcoef(x, y)[0, 1]
        bs = []
        for _ in range(B):
            i = rng.integers(0, len(r), len(r))
            bs.append(np.corrcoef(x[i], y[i])[0, 1])
        lo, hi = np.percentile(bs, [2.5, 97.5])
        filas.append({"metrica": m, "pearson_vs_sr_permitido": rr, "ic95_bajo": lo, "ic95_alto": hi,
                      "spearman": pd.Series(x).rank().corr(pd.Series(y).rank()), "n_equipos": len(r)})
    return pd.DataFrame(filas)


def calibracion(f: pd.DataFrame) -> pd.DataFrame:
    """Compara 'un rusher llegó a <= u yardas del QB antes de soltar' contra la presión de PFF."""
    d = f.dropna(subset=["rush_dist_min"])
    y = d["presion"].to_numpy() == 1
    filas = []
    for u in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        x = d["rush_dist_min"].to_numpy() <= u
        tp, fp, fn = (x & y).sum(), (x & ~y).sum(), (~x & y).sum()
        prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        filas.append({"umbral_yd": u, "tasa_tracking": x.mean(), "tasa_pff": y.mean(), "acuerdo": (x == y).mean(),
                      "precision": prec, "recall": rec, "f1": 2 * prec * rec / max(prec + rec, 1e-9),
                      "sr_permitido_si_llega": d.loc[x, "exito_of"].mean(), "sr_permitido_no_llega": d.loc[~x, "exito_of"].mean()})
    return pd.DataFrame(filas)


def main() -> None:
    f = cargar()
    r = ranking_defensas(f)
    r.to_csv(OUT / "ranking_defensas.csv", index=False)
    standings_semanales(f).to_csv(OUT / "standings_semanales.csv", index=False)
    m = matriz(f)
    m.to_csv(OUT / "matriz_presion_cobertura.csv", index=False)
    it = interaccion(f)
    it.to_csv(OUT / "interaccion_presion.csv", index=False)
    c = correlaciones(r)
    c.to_csv(OUT / "correlaciones_equipo.csv", index=False)
    cal = calibracion(f)
    cal.to_csv(OUT / "calibracion_umbral.csv", index=False)

    pd.set_option("display.width", 200)
    print("== Ranking (top 5 y bottom 3) ==")
    cols = ["rank", "equipo", "success_rate_permitido", "presion_rate", "sack_rate", "blitz_rate", "man_rate", "sr_con_presion", "sr_sin_presion"]
    print(pd.concat([r.head(5), r.tail(3)])[cols].round(3).to_string(index=False))
    print("\n== Correlaciones con SR permitido ==")
    print(c.round(3).to_string(index=False))
    print("\n== Matriz (con sacks) ==")
    print(m[~m["excluye_sacks"]].pivot_table(index=["nivel", "cobertura"], columns="presion", values=["success_rate", "jugadas"]).round(3).to_string())
    print("\n== Matriz (sin sacks) ==")
    print(m[m["excluye_sacks"]].pivot_table(index=["nivel", "cobertura"], columns="presion", values="success_rate").round(3).to_string())
    print("\n== Interacción ==")
    print(it.round(2).to_string(index=False))
    print("\n== Calibración ==")
    print(cal.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
