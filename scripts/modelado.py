"""Modelado: métrica DCI y prueba de "Defense wins championships".

Lee data/processed/plays_features.csv y games_clean.csv (salida de limpieza.py) y escribe en data/processed:
  plays_dci.csv                       DCI por jugada
  dci_coeficientes.csv                pesos del modelo (variables estandarizadas)
  equipo_partido.csv                  una fila por equipo y partido
  equipos_temporada.csv               una fila por equipo (insumo del scouting report)
  correlaciones_defensa_vs_victorias.csv
  prediccion_partidos.csv             defensa vs ofensiva para predecir ganador y margen
  estabilidad_metricas.csv            confiabilidad split-half de cada métrica
  patrones_*.csv                      patrones defensivos
  informe_hallazgos.md                resumen legible con las cifras

Solo pandas y numpy. Uso: python data/scripts/modelado.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carga  # noqa: E402

SEMILLA = 2021
OUT = carga.PROCESSED

# Variables de situación y de estilo ofensivo (conocidas antes del snap o decididas por la ofensiva): definen lo
# "esperado". `llego_2s`=0 marca un pase rápido (liberación antes de 2.0 s), decisión de la ofensiva.
SITUACION = ["down2", "down3", "down4", "yardsToGo", "ytg_x_d3", "yardline_100", "zona_roja", "play_action", "def_margen", "llego_2s"]
# Estado de la defensa a reloj fijo (2.0 s tras el snap, o la liberación si fue antes): lo que aporta el DCI.
# No incluye el tiempo hasta soltar ni la distancia al soltar: dependen de cuándo decide lanzar la ofensiva
# y de si hubo sack, y harían que el DCI midiera estilo ofensivo y resultado en vez de defensa.
TRACKING = [
    "presion_t2", "rush_dist_t2", "rush_n5_t2", "rush_vel_t2",
    "sep_media_t2", "sep_min_t2", "pct_abiertas_t2", "cierre_cobertura_t2", "n_rushers",
]


# ----------------------------------------------------------------- utilidades numéricas
def ajustar_logit(X: np.ndarray, y: np.ndarray, l2: float = 5.0, iters: int = 100) -> np.ndarray:
    """Regresión logística con ridge (IRLS). X ya incluye la columna de unos en la posición 0."""
    k = X.shape[1]
    b = np.zeros(k)
    pen = np.eye(k) * l2
    pen[0, 0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        w = p * (1 - p) + 1e-9
        paso = np.linalg.solve((X.T * w) @ X + pen, X.T @ (y - p) - pen @ b)
        b += paso
        if np.abs(paso).max() < 1e-8:
            break
    return b


def prob(X: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))


def con_unos(Z: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(Z)), Z])


def auc(y: np.ndarray, p: np.ndarray) -> float:
    r = pd.Series(p).rank().to_numpy()
    n1, n0 = y.sum(), len(y) - y.sum()
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def folds_por_grupo(grupos: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    ids = np.unique(grupos)
    rng.shuffle(ids)
    asign = {g: i % k for i, g in enumerate(ids)}
    return np.array([asign[g] for g in grupos])


def r_con_ic(x: pd.Series, y: pd.Series, B: int = 2000, seed: int = SEMILLA) -> tuple[float, float, float]:
    """Pearson con intervalo bootstrap del 95% (remuestreo de equipos)."""
    d = pd.concat([x, y], axis=1).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    r = np.corrcoef(d[:, 0], d[:, 1])[0, 1]
    bs = []
    for _ in range(B):
        i = rng.integers(0, len(d), len(d))
        if d[i, 0].std() > 0 and d[i, 1].std() > 0:
            bs.append(np.corrcoef(d[i, 0], d[i, 1])[0, 1])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return float(r), float(lo), float(hi)


def tabla_md(df: pd.DataFrame, dec: int = 3) -> str:
    cols = list(df.columns)
    filas = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        filas.append("| " + " | ".join(f"{v:.{dec}f}" if isinstance(v, (float, np.floating)) else str(v) for v in r) + " |")
    return "\n".join(filas)


# ----------------------------------------------------------------- DCI
def preparar_matrices(f: pd.DataFrame) -> pd.DataFrame:
    d = f.copy()
    d["down2"], d["down3"], d["down4"] = (d["down"] == 2) * 1.0, (d["down"] == 3) * 1.0, (d["down"] == 4) * 1.0
    d["ytg_x_d3"] = d["yardsToGo"] * d["down3"]
    for c in ("rush_dist_t2", "sep_media_t2", "sep_min_t2"):
        d[c] = d[c].clip(upper=d[c].quantile(0.99))
    for c in ("cierre_cobertura_t2", "rush_vel_t2"):
        d[c] = d[c].clip(d[c].quantile(0.01), d[c].quantile(0.99))
    return d


def calcular_dci(f: pd.DataFrame, k: int = 5) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """DCI (Defensive Control Index) por jugada.

    DCI = P(éxito ofensivo | situación) - P(éxito ofensivo | situación + estado de tracking al soltar).
    Positivo: la defensa dejó a la ofensiva en peor posición de lo que la situación predecía.
    Las probabilidades son fuera de muestra (k pliegues agrupados por partido).
    """
    d = preparar_matrices(f)
    d = d.dropna(subset=TRACKING + SITUACION + ["exito_of"]).reset_index(drop=True)
    y = d["exito_of"].to_numpy(dtype=float)
    rng = np.random.default_rng(SEMILLA)
    fold = folds_por_grupo(d["gameId"].to_numpy(), k, rng)

    def oof(cols: list[str]) -> np.ndarray:
        X = d[cols].to_numpy(dtype=float)
        p = np.zeros(len(d))
        for i in range(k):
            tr, te = fold != i, fold == i
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            b = ajustar_logit(con_unos((X[tr] - mu) / sd), y[tr])
            p[te] = prob(con_unos((X[te] - mu) / sd), b)
        return p

    p_sit, p_full = oof(SITUACION), oof(SITUACION + TRACKING)
    d["p_sit"], d["p_full"], d["dci"] = p_sit, p_full, (p_sit - p_full) * 100

    metricas = {
        "n_jugadas": len(d),
        "auc_situacion": auc(y, p_sit), "auc_situacion_tracking": auc(y, p_full),
        "logloss_situacion": logloss(y, p_sit), "logloss_situacion_tracking": logloss(y, p_full),
        "auc_tracking_solo": auc(y, oof(TRACKING)),
    }

    # coeficientes del modelo completo (ajustado con todos los datos, variables estandarizadas)
    cols = SITUACION + TRACKING
    X = d[cols].to_numpy(dtype=float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    b = ajustar_logit(con_unos((X - mu) / sd), y)
    coef = pd.DataFrame({"variable": cols, "coef_estandarizado": b[1:], "grupo": ["situacion"] * len(SITUACION) + ["tracking"] * len(TRACKING)})
    coef["efecto_en_exito_ofensivo"] = np.where(coef["coef_estandarizado"] > 0, "sube", "baja")
    return d[["gameId", "playId", "p_sit", "p_full", "dci"]], coef, metricas


# ----------------------------------------------------------------- equipos
def tabla_equipo_partido(f: pd.DataFrame, juegos: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido, con sumas (para promediar ponderado) y resultado."""
    f = f.copy()
    f["tiene_dci"] = f["dci"].notna().astype(int)
    f["dci0"] = f["dci"].fillna(0.0)
    f["ttt_c"] = f["ttt"].clip(1.0, 6.0)  # segundos de exposición del dropback (sin scrambles largos)
    d = f.groupby(["gameId", "defensiveTeam"], observed=True).agg(
        d_n=("playId", "size"), d_exito_def_s=("exito_def", "sum"), d_yds_s=("yardas", "sum"),
        d_sack_s=("es_sack", "sum"), d_int_s=("es_int", "sum"), d_presion_s=("pff_presion", "sum"),
        d_expl_s=("explosiva", "sum"), d_dci_s=("dci0", "sum"), d_dci_n=("tiene_dci", "sum"),
        d_ptrk_s=("presion_trk", "sum"), d_seg_s=("ttt_c", "sum"),
    ).reset_index().rename(columns={"defensiveTeam": "equipo"})
    o = f.groupby(["gameId", "possessionTeam"], observed=True).agg(
        o_n=("playId", "size"), o_exito_s=("exito_of", "sum"), o_yds_s=("yardas", "sum"),
        o_sack_perm_s=("es_sack", "sum"), o_dci_enf_s=("dci0", "sum"), o_dci_n=("tiene_dci", "sum"),
    ).reset_index().rename(columns={"possessionTeam": "equipo"})
    t = d.merge(o, on=["gameId", "equipo"], how="outer").fillna(0)

    j = juegos.set_index("gameId")
    t = t.join(j[["week", "homeTeamAbbr", "visitorTeamAbbr", "pts_local_est", "pts_visita_est", "resultado_incierto"]], on="gameId")
    t["local"] = (t["equipo"] == t["homeTeamAbbr"]).astype(int)
    t["oponente"] = np.where(t["local"] == 1, t["visitorTeamAbbr"], t["homeTeamAbbr"])
    t["pts_favor"] = np.where(t["local"] == 1, t["pts_local_est"], t["pts_visita_est"])
    t["pts_contra"] = np.where(t["local"] == 1, t["pts_visita_est"], t["pts_local_est"])
    t["margen"] = t["pts_favor"] - t["pts_contra"]
    t["victoria"] = np.select([t["margen"] > 0, t["margen"] < 0], [1.0, 0.0], default=0.5)
    return t.drop(columns=["homeTeamAbbr", "visitorTeamAbbr", "pts_local_est", "pts_visita_est"])


def metricas_desde_sumas(s: pd.DataFrame) -> pd.DataFrame:
    """De sumas a tasas. Convención: *_def_* y *_of_* con 'mejor = más alto' donde se indica."""
    m = pd.DataFrame(index=s.index)
    m["def_exito_def"] = s["d_exito_def_s"] / s["d_n"]            # % de dropbacks que la defensa gana (mejor = más)
    m["def_yds_dropback"] = -s["d_yds_s"] / s["d_n"]              # -yardas permitidas por dropback (mejor = más)
    m["def_sack_rate"] = s["d_sack_s"] / s["d_n"]
    m["def_int_rate"] = s["d_int_s"] / s["d_n"]
    m["def_presion_pff"] = s["d_presion_s"] / s["d_n"]
    m["def_prs"] = s["d_ptrk_s"] / s["d_seg_s"]                    # presiones por segundo de dropback (tracking)
    m["def_dci"] = s["d_dci_s"] / s["d_dci_n"].replace(0, np.nan)  # DCI medio (pp), mejor = más
    m["of_exito"] = s["o_exito_s"] / s["o_n"]                      # éxito ofensivo (mejor = más)
    m["of_yds_dropback"] = s["o_yds_s"] / s["o_n"]
    m["of_proteccion"] = 1 - s["o_sack_perm_s"] / s["o_n"]
    m["of_oci"] = -s["o_dci_enf_s"] / s["o_dci_n"].replace(0, np.nan)  # DCI ajeno invertido
    return m


def tabla_temporada(tp: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    sumas_cols = [c for c in tp.columns if c.endswith("_s") or c in ("d_n", "d_dci_n", "o_n", "o_dci_n")]
    s = tp.groupby("equipo")[sumas_cols].sum()
    t = metricas_desde_sumas(s)
    res = tp.groupby("equipo").agg(
        partidos=("gameId", "nunique"), victorias=("victoria", "sum"),
        pts_favor_pp=("pts_favor", "mean"), pts_contra_pp=("pts_contra", "mean"), margen_pp=("margen", "mean"),
    )
    res["win_pct"] = res["victorias"] / res["partidos"]
    t = res.join(t)

    # perfil de scouting defensivo (jugadas en que el equipo defendió)
    f = f.copy()
    g = f.groupby("defensiveTeam", observed=True)
    perfil = pd.DataFrame(
        {
            "dropbacks_defendidos": g.size(),
            "blitz_rate": g["blitz"].mean(),
            "rushers_medio": g["n_rushers"].mean(),
            "man_pct": g["tipo_cobertura"].apply(lambda s: (s == "Man").mean()),
            "defensores_en_caja": g["defendersInBox"].mean(),
            "tiempo_lanzar_ttt": g["ttt"].mean(),
            "separacion_media": g["sep_media"].mean(),
            "pct_rutas_abiertas": g["pct_abiertas"].mean(),
            "presion_trk_rate": g["presion_trk"].mean(),
        }
    )
    cob = pd.crosstab(f["defensiveTeam"], f["cobertura"], normalize="index").add_prefix("cob_")
    return t.join(perfil).join(cob).reset_index()


def correlaciones(t: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for m in ["def_exito_def", "def_yds_dropback", "def_sack_rate", "def_int_rate", "def_presion_pff", "def_prs", "def_dci",
              "of_exito", "of_yds_dropback", "of_proteccion", "of_oci"]:
        for obj in ("win_pct", "margen_pp"):
            r, lo, hi = r_con_ic(t[m], t[obj])
            filas.append({"metrica": m, "lado": "defensa" if m.startswith("def") else "ofensiva", "objetivo": obj,
                          "n_equipos": int(t[[m, obj]].dropna().shape[0]), "pearson": r, "ic95_bajo": lo, "ic95_alto": hi,
                          "spearman": t[m].rank().corr(t[obj].rank())})  # pandas usa scipy para 'spearman'; no está en el stack
    return pd.DataFrame(filas)


def regresion_equipos(t: pd.DataFrame, B: int = 2000) -> pd.DataFrame:
    """OLS estandarizada a nivel equipo: win% (o margen) ~ defensa + ofensiva. Compara el peso de cada lado."""
    rng = np.random.default_rng(SEMILLA)
    filas = []
    familias = {
        "Yardas/dropback": ("def_yds_dropback", "of_yds_dropback"),
        "Éxito por jugada": ("def_exito_def", "of_exito"),
        "DCI / OCI": ("def_dci", "of_oci"),
    }
    for nombre, (cd, co) in familias.items():
        for obj in ("win_pct", "margen_pp"):
            d = t[[cd, co, obj]].dropna()
            X = ((d[[cd, co]] - d[[cd, co]].mean()) / d[[cd, co]].std()).to_numpy()
            y = ((d[obj] - d[obj].mean()) / d[obj].std()).to_numpy()
            Z = con_unos(X)
            b = np.linalg.lstsq(Z, y, rcond=None)[0]
            r2 = 1 - ((y - Z @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()
            bs = []
            for _ in range(B):
                i = rng.integers(0, len(d), len(d))
                bs.append(np.linalg.lstsq(Z[i], y[i], rcond=None)[0][1:])
            lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
            for j, lado in enumerate(("defensa", "ofensiva")):
                filas.append({"familia": nombre, "objetivo": obj, "lado": lado, "n_equipos": len(d),
                              "beta_estandarizado": b[1 + j], "ic95_bajo": lo[j], "ic95_alto": hi[j], "r2": r2})
    return pd.DataFrame(filas)


def cuartiles(t: pd.DataFrame, col: str) -> pd.Series:
    q = pd.qcut(t[col].rank(method="first"), 4, labels=["Q1 (peor)", "Q2", "Q3", "Q4 (mejor)"])
    return t.groupby(q, observed=True)["win_pct"].mean()


def estabilidad(tp: pd.DataFrame, metricas: list[str]) -> pd.DataFrame:
    """Confiabilidad split-half: partidos pares vs impares de cada equipo (ordenados por semana)."""
    tp = tp.sort_values(["equipo", "week", "gameId"]).copy()
    tp["mitad"] = tp.groupby("equipo").cumcount() % 2
    sumas_cols = [c for c in tp.columns if c.endswith("_s") or c in ("d_n", "d_dci_n", "o_n", "o_dci_n")]
    A = metricas_desde_sumas(tp[tp["mitad"] == 0].groupby("equipo")[sumas_cols].sum())
    B = metricas_desde_sumas(tp[tp["mitad"] == 1].groupby("equipo")[sumas_cols].sum())
    wA = tp[tp["mitad"] == 0].groupby("equipo")["victoria"].mean()
    wB = tp[tp["mitad"] == 1].groupby("equipo")["victoria"].mean()
    filas = []
    for m in metricas:
        r = A[m].corr(B[m])
        filas.append({
            "metrica": m,
            "confiabilidad_split_half": r,
            "spearman_brown": 2 * r / (1 + r) if r > -1 else np.nan,
            "predice_win_pct_otra_mitad": 0.5 * (A[m].corr(wB) + B[m].corr(wA)),
        })
    return pd.DataFrame(filas)


# ----------------------------------------------------------------- predicción de partidos
def calidad_excluyendo_partido(tp: pd.DataFrame) -> pd.DataFrame:
    """Para cada equipo-partido, las métricas del equipo calculadas SIN ese partido (sin fuga de información)."""
    sumas_cols = [c for c in tp.columns if c.endswith("_s") or c in ("d_n", "d_dci_n", "o_n", "o_dci_n")]
    tot = tp.groupby("equipo")[sumas_cols].transform("sum")
    excl = tot - tp[sumas_cols]
    m = metricas_desde_sumas(excl)
    return pd.concat([tp[["gameId", "equipo", "local", "victoria", "margen", "resultado_incierto"]], m], axis=1)


def preparar_partidos(tp: pd.DataFrame) -> pd.DataFrame:
    q = calidad_excluyendo_partido(tp)
    h = q[q["local"] == 1].set_index("gameId")
    v = q[q["local"] == 0].set_index("gameId")
    g = h[["equipo", "victoria", "margen", "resultado_incierto"]].rename(columns={"equipo": "local"}).join(v[["equipo"]].rename(columns={"equipo": "visita"}))
    for m in ["def_exito_def", "def_yds_dropback", "def_dci", "of_exito", "of_yds_dropback", "of_oci"]:
        g[f"d_{m}"] = h[m] - v[m]
    return g.reset_index()


def evaluar_prediccion(g: pd.DataFrame, k: int = 5, B: int = 1000) -> pd.DataFrame:
    """Ganador (logit) y margen (OLS) a partir de la diferencia local-visita en defensa y ofensiva."""
    g = g[g["victoria"] != 0.5].dropna().reset_index(drop=True)
    y = g["victoria"].to_numpy(dtype=float)
    mg = g["margen"].to_numpy(dtype=float)
    rng = np.random.default_rng(SEMILLA)
    pares = {
        "Éxito (defensa vs ofensiva)": ("d_def_exito_def", "d_of_exito"),
        "Yardas/dropback": ("d_def_yds_dropback", "d_of_yds_dropback"),
        "DCI (defensa) vs OCI (ofensiva)": ("d_def_dci", "d_of_oci"),
    }
    filas = []
    for nombre, (cd, co) in pares.items():
        for etiqueta, cols in (("solo defensa", [cd]), ("solo ofensiva", [co]), ("defensa + ofensiva", [cd, co])):
            X = g[cols].to_numpy(dtype=float)
            fold = folds_por_grupo(np.arange(len(g)), k, rng)
            p = np.zeros(len(g))
            pm = np.zeros(len(g))
            for i in range(k):
                tr, te = fold != i, fold == i
                mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
                Ztr, Zte = con_unos((X[tr] - mu) / sd), con_unos((X[te] - mu) / sd)
                p[te] = prob(Zte, ajustar_logit(Ztr, y[tr], l2=1.0))
                pm[te] = Zte @ np.linalg.lstsq(Ztr, mg[tr], rcond=None)[0]
            mu, sd = X.mean(0), X.std(0) + 1e-9
            Z = con_unos((X - mu) / sd)
            b = ajustar_logit(Z, y, l2=1.0)
            bm = np.linalg.lstsq(Z, mg, rcond=None)[0]
            bs, bsm = [], []
            for _ in range(B):
                i = rng.integers(0, len(g), len(g))
                bs.append(ajustar_logit(Z[i], y[i], l2=1.0)[1:])
                bsm.append(np.linalg.lstsq(Z[i], mg[i], rcond=None)[0][1:])
            lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
            r2 = 1 - ((mg - pm) ** 2).sum() / ((mg - mg.mean()) ** 2).sum()
            for j, c in enumerate(cols):
                filas.append({
                    "familia": nombre, "modelo": etiqueta, "variable": "defensa" if c == cd else "ofensiva",
                    "n_partidos": len(g), "coef_logit_std": b[1 + j], "ic95_bajo": lo[j], "ic95_alto": hi[j],
                    "coef_margen_pts_por_sd": bm[1 + j],
                    "precision_cv": float(((p > 0.5) == (y == 1)).mean()), "logloss_cv": logloss(y, p), "r2_margen_cv": float(r2),
                })
    return pd.DataFrame(filas)


# ----------------------------------------------------------------- patrones
def resumen_patron(f: pd.DataFrame, por, minimo: int = 100) -> pd.DataFrame:
    g = f.groupby(por, observed=True)
    r = g.agg(
        jugadas=("playId", "size"), exito_def=("exito_def", "mean"), yds_permitidas=("yardas", "mean"),
        sack_rate=("es_sack", "mean"), int_rate=("es_int", "mean"), explosivas=("explosiva", "mean"),
        presion_pff=("pff_presion", "mean"), sep_media=("sep_media", "mean"), dci=("dci", "mean"),
    )
    return r[r["jugadas"] >= minimo].reset_index()


def patrones(f: pd.DataFrame) -> dict[str, pd.DataFrame]:
    f = f.copy()
    f["rushers_cat"] = pd.cut(f["n_rushers"], [0, 3, 4, 5, 20], labels=["<=3", "4", "5", "6+"])
    f["presion"] = np.where(f["pff_presion"] == 1, "con presion", "sin presion")
    f["sep_tercil"] = pd.qcut(f["sep_media"], 3, labels=["cobertura pegada", "media", "cobertura suelta"])
    f["t_lanzar"] = pd.cut(f["ttt"], [0, 2.3, 2.8, 3.3, 99], labels=["<2.3s", "2.3-2.8s", "2.8-3.3s", ">3.3s"])
    f["situacion"] = np.select([f["down"] == 1, f["down"] == 2, (f["down"] >= 3) & (f["yardsToGo"] >= 7), f["down"] >= 3],
                               ["1ra", "2da", "3ra/4ta larga (7+)", "3ra/4ta corta"], default="otra")
    return {
        "cobertura": resumen_patron(f, "cobertura").sort_values("exito_def", ascending=False),
        "man_vs_zone": resumen_patron(f, "tipo_cobertura"),
        "rushers": resumen_patron(f, "rushers_cat"),
        "presion": resumen_patron(f, "presion"),
        "presion_x_cobertura": resumen_patron(f, ["presion", "sep_tercil"]),
        "tiempo_lanzar": resumen_patron(f, "t_lanzar"),
        "cobertura_x_blitz": resumen_patron(f.assign(blitz_txt=np.where(f["blitz"] == 1, "blitz (5+)", "4 o menos")), ["cobertura", "blitz_txt"], minimo=150),
        "situacion": resumen_patron(f, "situacion"),
        "play_action": resumen_patron(f.assign(pa=np.where(f["play_action"] == 1, "play action", "sin PA")), "pa"),
    }


# ----------------------------------------------------------------- informe
def escribir_informe(ruta: Path, m: dict, coef: pd.DataFrame, corr: pd.DataFrame, reg: pd.DataFrame, pred: pd.DataFrame,
                     estab: pd.DataFrame, q_def: pd.Series, q_of: pd.Series, q_dci: pd.Series, pats: dict, n_equipos: int,
                     n_juegos: int, n_inciertos: int) -> None:
    c = corr.copy()
    c["pearson (IC95)"] = c.apply(lambda r: f"{r['pearson']:.2f} [{r['ic95_bajo']:.2f}, {r['ic95_alto']:.2f}]", axis=1)
    cw = c[c["objetivo"] == "win_pct"][["metrica", "lado", "n_equipos", "pearson (IC95)", "spearman"]]
    cm = c[c["objetivo"] == "margen_pp"][["metrica", "pearson (IC95)", "spearman"]]
    p = pred.copy()
    p["coef (IC95)"] = p.apply(lambda r: f"{r['coef_logit_std']:.2f} [{r['ic95_bajo']:.2f}, {r['ic95_alto']:.2f}]", axis=1)
    p = p[["familia", "modelo", "variable", "coef (IC95)", "coef_margen_pts_por_sd", "precision_cv", "r2_margen_cv"]]
    reg_t = reg.assign(**{"beta (IC95)": reg.apply(lambda r: f"{r['beta_estandarizado']:.2f} [{r['ic95_bajo']:.2f}, {r['ic95_alto']:.2f}]", axis=1)})
    reg_t = reg_t[["familia", "objetivo", "lado", "n_equipos", "beta (IC95)", "r2"]]
    cuart = pd.DataFrame({"cuartil": q_def.index.astype(str), "win% por defensa (exito)": q_def.values,
                          "win% por defensa (DCI)": q_dci.values, "win% por ofensiva (exito)": q_of.values})
    txt = f"""# Hallazgos: ¿Defense wins championships?

Generado por `data/scripts/modelado.py`. Datos: {n_juegos} partidos, {n_equipos} equipos, semanas 1 a 8 de 2021.

## Limitaciones que condicionan toda conclusión

- `plays.csv` contiene solo dropbacks (pases, sacks, scrambles). No hay jugadas de carrera: **todo es defensa contra el pase**.
- No hay marcador final en los datos del concurso. Se **estima** con el marcador previo a la última jugada observada
  (+6 si fue touchdown). Puede omitir carreras o goles de campo posteriores. {n_inciertos} partidos tienen diferencia <= 10
  y su ganador puede estar mal; usa `resultado_incierto` en `games_clean.csv` para filtrarlos.
- Cada equipo tiene unos 7 a 8 partidos: el win% es ruidoso. Los intervalos de confianza son anchos.

## 1. Métrica nueva: DCI (Defensive Control Index)

DCI = P(éxito ofensivo | situación) - P(éxito ofensivo | situación + estado de tracking al soltar el balón), en puntos
porcentuales por dropback. Positivo: la defensa dejó a la ofensiva en peor posición de lo que down, distancia, yarda,
marcador y play action predecían. Se calcula con regresión logística y validación cruzada agrupada por partido, así
que no se evalúa sobre jugadas con las que se entrenó.

Entradas de tracking, medidas a reloj fijo (2.0 s tras el snap, o la liberación si fue antes): presión (rusher a
<= 2 yd del QB), distancia del rusher más cercano, rushers a <= 5 yd, velocidad de los rushers, separación media y
mínima entre receptores y defensor más cercano, % de rutas abiertas (>= 3 yd), cuánto se cerró la cobertura desde el
snap y número de rushers. No usa el tiempo hasta soltar ni el estado al soltar: dependen de cuándo decide lanzar la
ofensiva y de si hubo sack. Un pase rápido (liberación antes de 2.0 s) entra como control de situación.

Métrica complementaria PRS (Pressure Rate per Second) = jugadas con presión / segundos totales de dropback del equipo.
Corrige que las defensas contra pases rápidos tienen menos tiempo para llegar al QB.

| Modelo | AUC | Logloss |
|---|---|---|
| Solo situación | {m['auc_situacion']:.3f} | {m['logloss_situacion']:.3f} |
| Situación + tracking | {m['auc_situacion_tracking']:.3f} | {m['logloss_situacion_tracking']:.3f} |
| Solo tracking | {m['auc_tracking_solo']:.3f} | |

({m['n_jugadas']:,} jugadas con tracking completo). Si "Situación + tracking" casi no mejora a "Solo situación", la
estructura defensiva a reloj fijo describe cómo juega el equipo más que el resultado de cada jugada.

Coeficientes estandarizados (ver `dci_coeficientes.csv`):

{tabla_md(coef[['variable', 'grupo', 'coef_estandarizado']])}

## 2. Defensa y victorias por equipo

Correlación con win% (n = {n_equipos} equipos). Para todas las métricas, más alto = mejor.

{tabla_md(cw, 2)}

Correlación con margen de puntos por partido:

{tabla_md(cm, 2)}

Win% promedio por cuartil de equipos ordenados por métrica:

{tabla_md(cuart, 3)}

Regresión a nivel equipo (betas estandarizados con ambos lados a la vez; si el beta de defensa no supera al de
ofensiva, los datos no respaldan que la defensa pese más):

{tabla_md(reg_t, 2)}

## 3. Defensa contra ofensiva para predecir partidos

Cada partido se predice con la calidad de cada equipo calculada sin ese partido. Coeficientes estandarizados
(por desviación estándar de la diferencia local - visita).

{tabla_md(p, 2)}

## 4. Estabilidad de las métricas

Correlación entre mitades de partidos de cada equipo (pares vs impares). Una métrica estable describe al equipo, no
al azar de unos partidos.

{tabla_md(estab, 2)}

## 5. Patrones defensivos

Cobertura (ordenadas por éxito defensivo):

{tabla_md(pats['cobertura'], 3)}

Rushers:

{tabla_md(pats['rushers'], 3)}

Presión por separación (cobertura pegada, media, suelta):

{tabla_md(pats['presion_x_cobertura'], 3)}

Tiempo hasta soltar:

{tabla_md(pats['tiempo_lanzar'], 3)}
"""
    ruta.write_text(txt, encoding="utf-8")


def main() -> None:
    f = pd.read_csv(OUT / "plays_features.csv")
    juegos = pd.read_csv(OUT / "games_clean.csv")

    dci_play, coef, met = calcular_dci(f)
    f = f.merge(dci_play, on=["gameId", "playId"], how="left")
    dci_play.to_csv(OUT / "plays_dci.csv", index=False)
    coef.to_csv(OUT / "dci_coeficientes.csv", index=False)
    print("DCI:", {k: round(v, 4) if isinstance(v, float) else v for k, v in met.items()})

    tp = tabla_equipo_partido(f, juegos)
    tp.to_csv(OUT / "equipo_partido.csv", index=False)
    ts = tabla_temporada(tp, f)
    ts.to_csv(OUT / "equipos_temporada.csv", index=False)

    corr = correlaciones(ts)
    corr.to_csv(OUT / "correlaciones_defensa_vs_victorias.csv", index=False)
    reg = regresion_equipos(ts)
    reg.to_csv(OUT / "regresion_equipos.csv", index=False)
    estab = estabilidad(tp, ["def_exito_def", "def_yds_dropback", "def_int_rate", "def_sack_rate", "def_presion_pff", "def_prs", "def_dci", "of_exito", "of_oci"])
    estab.to_csv(OUT / "estabilidad_metricas.csv", index=False)

    partidos = preparar_partidos(tp)
    pred = evaluar_prediccion(partidos)
    pred.to_csv(OUT / "prediccion_partidos.csv", index=False)
    pred_ciertos = evaluar_prediccion(partidos[tp.groupby("gameId")["resultado_incierto"].max().reindex(partidos["gameId"]).to_numpy() == 0])
    pred_ciertos.to_csv(OUT / "prediccion_partidos_sin_inciertos.csv", index=False)

    pats = patrones(f)
    for k, v in pats.items():
        v.to_csv(OUT / f"patrones_{k}.csv", index=False)

    n_inc = int(juegos["resultado_incierto"].sum())
    escribir_informe(OUT / "informe_hallazgos.md", met, coef, corr, reg, pred, estab,
                     cuartiles(ts, "def_exito_def"), cuartiles(ts, "of_exito"), cuartiles(ts, "def_dci"), pats,
                     len(ts), len(juegos), n_inc)
    print("Listo. Archivos en", OUT)


if __name__ == "__main__":
    main()
