"""Métrica propia: tiempo hasta presión (TTP) con el tracking.

TTP = segundos desde el snap hasta que un pass rusher queda a <= 2 yardas del QB (umbral calibrado contra PFF en
calibracion_umbral.csv). Si el QB suelta el balón antes, la jugada queda "censurada": no sabemos cuándo habría
llegado la presión. Por eso las comparaciones usan curvas de Kaplan-Meier en vez del promedio de los TTP
observados (el promedio favorecería a quien solo presiona en jugadas largas).

Escribe en data/processed:
  rushers_jugada.csv         una fila por pass rusher y jugada: posición, t_llegada, distancia mínima
  plays_ttp.csv              una fila por jugada: TTP, tiempo de lanzamiento, rushers, blitz, resultado
  curvas_ttp.csv             % de jugadas ya presionadas a cada t, por grupo (4 rushers, blitz...)
  resumen_ttp_grupos.csv     4 vs 5 vs 6+ rushers, man vs zona
  ttp_equipos.csv            TTP por defensa (P(presión antes de 2.5 s), mediana KM)
  rusher_mas_rapido.csv      rusher más rápido de cada equipo
  ttp_posiciones.csv         qué pff_positionLinedUp presiona más rápido
  animaciones.csv            cuadros (coordenadas normalizadas) de jugadas de ejemplo
  animaciones_indice.csv     descripción de esas jugadas

Uso: python data/scripts/tiempo_presion.py [--lote 4]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carga  # noqa: E402

OUT = carga.PROCESSED
FPS = 10.0
UMBRAL_YD = 2.0
T_RAPIDA = 2.5  # "presión rápida": llega antes de 2.5 s
T_MIN = 0.5  # antes de 0.5 s ningún rusher real llega: lo que haya es alineación, no presión
ANCHO = 160 / 3  # 53.33 yardas
EVENTOS_SNAP = {"ball_snap", "autoevent_ballsnap"}
EVENTOS_FIN = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "fumble", "run"}
REJILLA = np.round(np.arange(0, 6.01, 0.1), 1)


# ----------------------------------------------------------------- tracking -> rusher/jugada
def procesar_jugada(g: pd.DataFrame, snap: int | None, fin: int | None) -> tuple[list[dict], dict] | None:
    g = g.sort_values(["nflId", "frameId"])
    n_frames = g.groupby("nflId", observed=True).size()
    if n_frames.nunique() != 1 or snap is None:
        return None
    F, P = int(n_frames.iloc[0]), len(n_frames)
    frames = g["frameId"].to_numpy()[:F]
    x = g["x"].to_numpy(np.float64).reshape(P, F)
    y = g["y"].to_numpy(np.float64).reshape(P, F)
    roles = g["pff_role"].to_numpy()[::F]
    ids = g["nflId"].to_numpy()[::F]
    qb, rush = roles == "Pass", roles == "Pass Rush"
    if qb.sum() != 1 or rush.sum() == 0:
        return None
    i0 = min(int(np.searchsorted(frames, snap)), F - 1)
    i1 = min(int(np.searchsorted(frames, fin)), F - 1) if fin is not None else F - 1
    if i1 <= i0:
        return None
    d = np.hypot(x[rush] - x[qb][0], y[rush] - y[qb][0])[:, i0 : i1 + 1]  # (rushers, frames)
    ttt = (i1 - i0) / FPS
    filas = []
    i_min = int(T_MIN * FPS)
    for j, nid in enumerate(ids[rush]):
        # Un nose tackle frente a un QB bajo el centro ya está a <= 2 yd en el snap: eso no es presión.
        # La llegada cuenta solo después de que el rusher estuvo a > 2 yd y nunca antes de T_MIN.
        lejos = np.flatnonzero(d[j] > UMBRAL_YD)
        inicio = max(int(lejos[0]) if lejos.size else d.shape[1], i_min)
        cerca = inicio + np.flatnonzero(d[j, inicio:] <= UMBRAL_YD)
        filas.append({"nflId": int(nid), "t_llegada": cerca[0] / FPS if cerca.size else np.nan,
                      "dist_min": float(d[j].min()), "dist_snap": float(d[j, 0])})
    tl = [f["t_llegada"] for f in filas if not np.isnan(f["t_llegada"])]
    jugada = {"ttp": min(tl) if tl else np.nan, "ttt": ttt, "presion_trk": float(bool(tl)),
              "n_llegan": len(tl), "snap_frame": int(frames[i0]), "fin_frame": int(frames[i1])}
    return filas, jugada


def pasar_tracking(ids: list[int], pff: pd.DataFrame, lote: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    roles = pff[["gameId", "playId", "nflId", "pff_role"]].copy()
    roles["nflId"] = roles["nflId"].astype("float32")
    roles["pff_role"] = roles["pff_role"].astype(str)
    R, J = [], []
    t0, hechos = time.time(), 0
    cols = ["gameId", "playId", "nflId", "frameId", "x", "y", "event"]
    for trk in carga.iterar_tracking(ids, tam_lote=lote, columnas=cols):
        trk = trk[trk["nflId"].notna()].merge(roles, on=["gameId", "playId", "nflId"], how="inner")
        ev = trk.loc[trk["event"].notna(), ["gameId", "playId", "frameId", "event"]].copy()
        ev["event"] = ev["event"].astype(str)
        snap = ev[ev["event"].isin(EVENTOS_SNAP)].groupby(["gameId", "playId"])["frameId"].min()
        fin = ev[ev["event"].isin(EVENTOS_FIN)].groupby(["gameId", "playId"])["frameId"].min()
        for (gid, pid), g in trk.groupby(["gameId", "playId"], sort=False, observed=True):
            r = procesar_jugada(g, snap.get((gid, pid)), fin.get((gid, pid)))
            if r is None:
                continue
            filas, jug = r
            R.extend({"gameId": gid, "playId": pid, **f} for f in filas)
            J.append({"gameId": gid, "playId": pid, **jug})
        hechos += trk["gameId"].nunique()
        print(f"  tracking {hechos}/{len(ids)} partidos, {len(J)} jugadas, {time.time() - t0:.0f}s", flush=True)
    return pd.DataFrame(R), pd.DataFrame(J)


# ----------------------------------------------------------------- Kaplan-Meier
def km_presionada(ttp: np.ndarray, ttt: np.ndarray, rejilla: np.ndarray = REJILLA) -> np.ndarray:
    """P(presión antes de t). Evento = presión en ttp; censura = lanzamiento en ttt sin presión."""
    evento = ~np.isnan(ttp)
    t = np.where(evento, ttp, ttt)
    orden = np.argsort(t, kind="stable")
    t, evento = t[orden], evento[orden]
    s, n, i, out = 1.0, len(t), 0, []
    tiempos = np.unique(t)
    surv = {}
    for tu in tiempos:
        en = t == tu
        d = int((en & evento).sum())
        if n > 0 and d:
            s *= 1 - d / n
        surv[tu] = s
        n -= int(en.sum())
    claves = np.array(sorted(surv))
    vals = np.array([surv[k] for k in claves])
    for r in rejilla:
        k = np.searchsorted(claves, r + 1e-9, side="right") - 1
        out.append(1 - (vals[k] if k >= 0 else 1.0))
    return np.array(out)


def mediana_km(curva: np.ndarray, rejilla: np.ndarray = REJILLA) -> float:
    k = np.flatnonzero(curva >= 0.5)
    return float(rejilla[k[0]]) if k.size else np.nan


def resumen_grupo(d: pd.DataFrame) -> dict:
    c = km_presionada(d["ttp"].to_numpy(), d["ttt"].to_numpy())
    obs = d["ttp"].dropna()
    return {"jugadas": len(d), "presion_trk_rate": d["presion_trk"].mean(),
            "p_presion_2s": c[REJILLA == 2.0][0], "p_presion_2_5s": c[REJILLA == 2.5][0], "p_presion_3s": c[REJILLA == 3.0][0],
            "mediana_km_s": mediana_km(c), "ttp_mediano_observado": obs.median() if len(obs) else np.nan,
            "ttt_medio": d["ttt"].mean(), "success_rate_permitido": d["exito_of"].mean(),
            "sr_si_presion_rapida": d.loc[d["ttp"] <= T_RAPIDA, "exito_of"].mean(),
            "sr_si_presion_tardia": d.loc[d["ttp"] > T_RAPIDA, "exito_of"].mean(),
            "sr_sin_presion_trk": d.loc[d["ttp"].isna(), "exito_of"].mean()}


# ----------------------------------------------------------------- animación
def seleccionar_ejemplos(J: pd.DataFrame) -> pd.DataFrame:
    """Jugadas de ejemplo: presión rápida con 4 rushers, blitz, y casos de BUF e IND."""
    d = J.dropna(subset=["ttp"]).copy()
    d = d[(d["ttp"] >= 1.0) & (d["ttt"] <= 6)]  # descarta artefactos de snap
    elegidas: list[tuple[int, int, str]] = []

    def tomar(sub: pd.DataFrame, etiqueta: str, n: int = 1, col: str = "ttp", asc: bool = True):
        usadas = {(g, p) for g, p, _ in elegidas}
        sub = sub[[(g, p) not in usadas for g, p in zip(sub["gameId"], sub["playId"])]]
        for _, r in sub.sort_values(col, ascending=asc).head(n).iterrows():
            elegidas.append((int(r["gameId"]), int(r["playId"]), etiqueta))

    tomar(d[(d["n_rushers"] == 4) & (d["es_sack"] == 1)], "Sack con 4 rushers: la presión más rápida", 2)
    tomar(d[(d["n_rushers"] >= 5) & (d["es_sack"] == 1)], "Sack con blitz: la presión más rápida", 2)
    tomar(d[(d["defensiveTeam"] == "BUF") & (d["n_rushers"] == 4)], "BUF: presión rápida con 4 rushers", 2)
    tomar(d[(d["defensiveTeam"] == "IND") & (d["n_rushers"] == 4)], "IND: presión rápida con 4 rushers", 1)
    sinp = J[J["ttp"].isna() & (J["ttt"] >= 4.0) & (J["ttt"] <= 6) & (J["exito_of"] == 1)]
    tomar(sinp, "Sin presión: el QB tiene tiempo y completa", 1, col="yardas", asc=False)
    return pd.DataFrame(elegidas, columns=["gameId", "playId", "etiqueta"])


def extraer_animaciones(ej: pd.DataFrame, pff: pd.DataFrame, J: pd.DataFrame, plays: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    roles = pff[["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp"]].copy()
    roles["nflId"] = roles["nflId"].astype("float32")
    frames = []
    for gid, sub in ej.groupby("gameId"):
        t = carga.cargar_tracking_juego(gid)
        t = t[t["playId"].isin(sub["playId"])]
        for pid in sub["playId"]:
            p = t[t["playId"] == pid].copy()
            info = J[(J["gameId"] == gid) & (J["playId"] == pid)].iloc[0]
            p = p[(p["frameId"] >= info["snap_frame"] - 5) & (p["frameId"] <= info["fin_frame"] + 10)]
            # coordenadas simétricas: la ofensiva siempre ataca hacia la derecha
            izq = p["playDirection"].astype(str) == "left"
            p["x"] = np.where(izq, 120 - p["x"], p["x"]).round(2)
            p["y"] = np.where(izq, ANCHO - p["y"], p["y"]).round(2)
            p = p.merge(roles, on=["gameId", "playId", "nflId"], how="left")
            p["rol"] = np.where(p["nflId"].isna(), "Balón", p["pff_role"].astype(object).fillna("Otro"))
            p["t"] = ((p["frameId"] - info["snap_frame"]) / FPS).round(1)
            qb = p[p["rol"] == "Pass"][["frameId", "x", "y"]].rename(columns={"x": "qx", "y": "qy"})
            p = p.merge(qb, on="frameId", how="left")
            p["dist_qb"] = np.where(p["rol"] == "Pass Rush", np.hypot(p["x"] - p["qx"], p["y"] - p["qy"]).round(2), np.nan)
            frames.append(p[["gameId", "playId", "frameId", "t", "nflId", "team", "rol", "pff_positionLinedUp",
                             "x", "y", "s", "dist_qb", "event"]])
    A = pd.concat(frames, ignore_index=True)
    meta = plays[["gameId", "playId", "playDescription", "possessionTeam", "defensiveTeam", "down", "yardsToGo",
                  "pff_passCoverage", "passResult"]]
    idx = ej.merge(meta, on=["gameId", "playId"], how="left").merge(
        J[["gameId", "playId", "ttp", "ttt", "n_rushers"]], on=["gameId", "playId"], how="left")
    # línea de scrimmage normalizada: posición x del balón en el snap
    los = A[(A["rol"] == "Balón") & (A["t"] == 0)].groupby(["gameId", "playId"])["x"].first().rename("linea_x")
    idx = idx.merge(los, on=["gameId", "playId"], how="left")
    return A, idx


# ----------------------------------------------------------------- principal
def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", type=int, default=4)
    ap.add_argument("--games", type=int, nargs="*")
    a = ap.parse_args(argv)
    ids = a.games or carga.game_ids_disponibles()

    pff = carga.cargar_pff(ids)
    plays_raw = carga.cargar_plays(ids)
    feat = pd.read_csv(OUT / "plays_features.csv")
    feat = feat[feat["gameId"].isin(ids)]

    R, J = pasar_tracking(ids, pff, a.lote)

    # jugada: añadir contexto
    ctx = feat[["gameId", "playId", "defensiveTeam", "possessionTeam", "week", "n_rushers", "blitz", "tipo_cobertura",
                "cobertura", "exito_of", "es_sack", "yardas", "pff_presion"]]
    J = J.merge(ctx, on=["gameId", "playId"], how="inner")
    J["grupo_rushers"] = pd.cut(J["n_rushers"], [0, 3, 4, 5, 20], labels=["3 o menos", "4", "5 (blitz)", "6+ (blitz)"]).astype(str)
    J.drop(columns=["snap_frame", "fin_frame"]).to_csv(OUT / "plays_ttp.csv", index=False)

    # rusher: añadir posición, equipo y PFF
    p2 = pff[pff["pff_role"].astype(str) == "Pass Rush"][["gameId", "playId", "nflId", "pff_positionLinedUp", "pff_hit", "pff_hurry", "pff_sack"]].copy()
    p2["presion_pff"] = (p2[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).sum(axis=1) > 0).astype(int)
    R = R.merge(p2[["gameId", "playId", "nflId", "pff_positionLinedUp", "presion_pff"]], on=["gameId", "playId", "nflId"], how="left")
    R = R.merge(J[["gameId", "playId", "defensiveTeam", "ttt", "n_rushers", "exito_of"]], on=["gameId", "playId"], how="inner")
    players = carga.cargar_players()[["nflId", "displayName", "officialPosition"]]
    R = R.merge(players, on="nflId", how="left")
    R.to_csv(OUT / "rushers_jugada.csv", index=False)

    # curvas y resumen por grupo
    grupos = {"Todas": J, **{f"{k} rushers": J[J["grupo_rushers"] == k] for k in ["3 o menos", "4", "5 (blitz)", "6+ (blitz)"]},
              "Man": J[J["tipo_cobertura"] == "Man"], "Zone": J[J["tipo_cobertura"] == "Zone"]}
    curvas, resumen = [], []
    for nombre, d in grupos.items():
        c = km_presionada(d["ttp"].to_numpy(), d["ttt"].to_numpy())
        curvas.append(pd.DataFrame({"grupo": nombre, "t": REJILLA, "p_presionada": c}))
        resumen.append({"grupo": nombre, **resumen_grupo(d)})
    pd.concat(curvas).to_csv(OUT / "curvas_ttp.csv", index=False)
    res = pd.DataFrame(resumen)
    res.to_csv(OUT / "resumen_ttp_grupos.csv", index=False)

    # equipos
    eq = []
    for team, d in J.groupby("defensiveTeam"):
        r4 = d[d["n_rushers"] == 4]
        eq.append({"equipo": team, **resumen_grupo(d),
                   "p_presion_2_5s_con_4": km_presionada(r4["ttp"].to_numpy(), r4["ttt"].to_numpy())[REJILLA == 2.5][0],
                   "jugadas_con_4": len(r4)})
    eq = pd.DataFrame(eq).sort_values("p_presion_2_5s", ascending=False)
    eq.to_csv(OUT / "ttp_equipos.csv", index=False)

    # rushers individuales
    R["rapida"] = (R["t_llegada"] <= T_RAPIDA).astype(int)
    R["llega"] = R["t_llegada"].notna().astype(int)
    R["pff_positionLinedUp"] = R["pff_positionLinedUp"].astype(str)
    ind = R.groupby(["nflId", "displayName", "officialPosition"], observed=True).agg(
        equipo=("defensiveTeam", lambda s: s.mode().iat[0]), posicion_top=("pff_positionLinedUp", lambda s: s.astype(str).mode().iat[0]),
        snaps_rush=("playId", "size"), llegadas=("llega", "sum"), llegadas_rapidas=("rapida", "sum"),
        t_llegada_mediana=("t_llegada", "median"), presiones_pff=("presion_pff", "sum")).reset_index()
    ind["llegadas_rapidas_por_100"] = 100 * ind["llegadas_rapidas"] / ind["snaps_rush"]
    ind["tasa_llegada"] = ind["llegadas"] / ind["snaps_rush"]
    elegibles = ind[ind["snaps_rush"] >= 60]
    rapido = elegibles.sort_values("llegadas_rapidas_por_100", ascending=False).groupby("equipo").head(1)
    rapido.sort_values("llegadas_rapidas_por_100", ascending=False).to_csv(OUT / "rusher_mas_rapido.csv", index=False)
    elegibles.sort_values("llegadas_rapidas_por_100", ascending=False).to_csv(OUT / "rushers_ranking.csv", index=False)

    # posiciones de la línea
    pos = R.groupby("pff_positionLinedUp", observed=True).agg(snaps_rush=("playId", "size"), tasa_llegada=("llega", "mean"),
                                               tasa_llegada_rapida=("rapida", "mean"), t_llegada_mediana=("t_llegada", "median"),
                                               dist_snap_media=("dist_snap", "mean"), presion_pff_rate=("presion_pff", "mean")).reset_index()
    pos = pos[pos["snaps_rush"] >= 150].sort_values("tasa_llegada_rapida", ascending=False)
    pos.to_csv(OUT / "ttp_posiciones.csv", index=False)

    # animaciones
    plays_desc = plays_raw.copy()
    for c in plays_desc.columns:
        if str(plays_desc[c].dtype) == "category":
            plays_desc[c] = plays_desc[c].astype(object)
    ej = seleccionar_ejemplos(J.merge(plays_desc[["gameId", "playId"]], on=["gameId", "playId"]))
    A, idx = extraer_animaciones(ej, pff, J, plays_desc)
    A.to_csv(OUT / "animaciones.csv", index=False)
    idx.to_csv(OUT / "animaciones_indice.csv", index=False)

    pd.set_option("display.width", 220)
    print("\n== Grupos ==\n", res.round(3).to_string(index=False))
    print("\n== Equipos (top 5 / bottom 3 por P(presión <2.5s)) ==\n",
          pd.concat([eq.head(5), eq.tail(3)])[["equipo", "jugadas", "p_presion_2_5s", "p_presion_2_5s_con_4", "mediana_km_s", "success_rate_permitido"]].round(3).to_string(index=False))
    print("\n== Posiciones ==\n", pos.round(3).to_string(index=False))
    print("\n== Rusher más rápido (top 10) ==\n", rapido.head(10)[["equipo", "displayName", "posicion_top", "snaps_rush", "llegadas_rapidas_por_100", "t_llegada_mediana"]].round(2).to_string(index=False))
    print("\n== Animaciones ==\n", idx[["gameId", "playId", "etiqueta", "ttp", "ttt", "n_rushers"]].to_string(index=False))
    print(f"\nanimaciones: {len(A)} filas")
    for c in ("p_presion_2s", "p_presion_2_5s", "p_presion_3s", "presion_trk_rate", "mediana_km_s", "p_presion_2_5s_con_4"):
        print(f"corr equipo {c} vs SR permitido: {eq[c].corr(eq['success_rate_permitido']):.3f}")
    # por jugada: ¿la presión rápida vale más que la tardía? (sin sacks, que son fracaso automático)
    ns = J[J["es_sack"] == 0]
    for nombre, m in (("rápida <=2.5s", ns["ttp"] <= T_RAPIDA), ("tardía >2.5s", ns["ttp"] > T_RAPIDA), ("sin presión trk", ns["ttp"].isna())):
        print(f"sin sacks, presión {nombre}: n={int(m.sum())}, SR={ns.loc[m, 'exito_of'].mean():.3f}, ttt={ns.loc[m, 'ttt'].mean():.2f}")


if __name__ == "__main__":
    main()
