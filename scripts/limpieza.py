"""Limpieza y construcción de features. Lee data/raw y escribe data/processed.

Salidas (CSV, pandas/numpy solamente):
  games_clean.csv        partidos con resultado estimado
  plays_features.csv     una fila por dropback: contexto, resultado, PFF y features de tracking
  defensores_pff.csv     una fila por defensor: snaps, presiones, sacks (para scouting)

Uso:
  python data/scripts/limpieza.py                  # todos los partidos
  python data/scripts/limpieza.py --semanas 1 2    # solo semanas 1 y 2
  python data/scripts/limpieza.py --games 2021090900 2021091200 --lote 2
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

FPS = 10.0  # el tracking se muestrea a 10 cuadros por segundo
PRESION_YD = 2.0  # un pass rusher a <= 2 yardas del QB cuenta como presión
ABIERTO_YD = 3.0  # receptor con separación >= 3 yardas del defensor más cercano
T_FIJO = 2.0  # segundos tras el snap para medir el estado defensivo a reloj fijo
EVENTOS_SNAP = {"ball_snap", "autoevent_ballsnap"}
EVENTOS_FIN = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "fumble", "run"}


# --------------------------------------------------------------------------- plays
def _clock_a_seg(s: pd.Series) -> pd.Series:
    mm_ss = s.astype(str).str.split(":", expand=True).astype(float)
    return (mm_ss[0] * 60 + mm_ss[1]).astype("float32")


def limpiar_plays(plays: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    p = plays.copy()
    for c in ("possessionTeam", "defensiveTeam", "yardlineSide", "pff_passCoverage", "pff_passCoverageType"):
        p[c] = p[c].astype("object")
    assert not p.duplicated(["gameId", "playId"]).any(), "gameId+playId duplicado en plays.csv"

    g = games[["gameId", "week", "homeTeamAbbr", "visitorTeamAbbr"]]
    p = p.merge(g, on="gameId", how="left")
    p["def_es_local"] = (p["defensiveTeam"] == p["homeTeamAbbr"]).astype("int8")

    p["clock_seg"] = _clock_a_seg(p["gameClock"])
    q = p["quarter"].astype("int32")
    p["seg_restantes"] = (np.where(q <= 4, (4 - q) * 900, 0) + p["clock_seg"]).astype("float32")

    # marcador desde la perspectiva de la defensa
    off_local = p["possessionTeam"] == p["homeTeamAbbr"]
    p["off_puntos"] = np.where(off_local, p["preSnapHomeScore"], p["preSnapVisitorScore"]).astype("int16")
    p["def_puntos"] = np.where(off_local, p["preSnapVisitorScore"], p["preSnapHomeScore"]).astype("int16")
    p["def_margen"] = (p["def_puntos"] - p["off_puntos"]).astype("int16")
    p["tiempo_basura"] = ((p["quarter"] >= 4) & (p["def_margen"].abs() > 16)).astype("int8")

    # yardas a la end zone (100 = propia goal line). yardlineSide NaN = mitad de campo
    propia = p["yardlineSide"] == p["possessionTeam"]
    p["yardline_100"] = np.where(p["yardlineSide"].isna(), 50, np.where(propia, 100 - p["yardlineNumber"], p["yardlineNumber"])).astype("int16")
    p["zona_roja"] = (p["yardline_100"] <= 20).astype("int8")

    # resultado de la jugada
    r = p["passResult"]
    p["es_sack"] = (r == "S").astype("int8")
    p["es_int"] = (r == "IN").astype("int8")
    p["es_incompleto"] = (r == "I").astype("int8")
    p["es_completo"] = (r == "C").astype("int8")
    p["es_scramble"] = (r == "R").astype("int8")
    p["yardas"] = p["playResult"].astype("int16")
    p["pen_def"] = (p["penaltyYards"].fillna(0) > 0).astype("int8")  # yardas a favor de la ofensiva
    p["pen_of"] = (p["penaltyYards"].fillna(0) < 0).astype("int8")
    p["explosiva"] = (p["yardas"] >= 20).astype("int8")

    # éxito ofensivo por down: 40% / 60% / 100% de las yardas por ganar
    umbral = np.select([p["down"] == 1, p["down"] == 2], [0.4 * p["yardsToGo"], 0.6 * p["yardsToGo"]], default=p["yardsToGo"])
    p["exito_of"] = ((p["yardas"] >= umbral) & (p["es_int"] == 0)).astype("int8")
    p["exito_def"] = (1 - p["exito_of"]).astype("int8")

    # personal defensivo "4 DL, 2 LB, 5 DB"
    for pos in ("DL", "LB", "DB"):
        p[f"n_{pos}"] = p["personnelD"].str.extract(rf"(\d+)\s*{pos}")[0].astype(float).fillna(0).astype("int8")

    p["cobertura"] = p["pff_passCoverage"].fillna("Desconocida")
    p["tipo_cobertura"] = p["pff_passCoverageType"].fillna("Other")
    p["play_action"] = p["pff_playAction"].fillna(0).astype("int8")
    p["dropback"] = p["dropBackType"].astype("object").fillna("UNKNOWN")
    return p.drop(columns=["playDescription", "gameClock", "foulName2", "foulNFLId2", "foulName3", "foulNFLId3"])


def agregar_pff_por_jugada(pff: pd.DataFrame) -> pd.DataFrame:
    """Conteos PFF por jugada: cuántos rushers/coverage y presiones logradas."""
    d = pff.copy()
    for c in ("pff_hit", "pff_hurry", "pff_sack"):
        d[c] = d[c].fillna(0)
    rol = d["pff_role"].astype(str)
    d["n_rushers"] = (rol == "Pass Rush").astype("int8")
    d["n_coverage"] = (rol == "Coverage").astype("int8")
    d["n_bloqueadores"] = (rol == "Pass Block").astype("int8")
    d["n_rutas"] = (rol == "Pass Route").astype("int8")
    out = (
        d.groupby(["gameId", "playId"], observed=True)[
            ["n_rushers", "n_coverage", "n_bloqueadores", "n_rutas", "pff_hit", "pff_hurry", "pff_sack"]
        ]
        .sum()
        .rename(columns={"pff_hit": "pff_hits", "pff_hurry": "pff_hurries", "pff_sack": "pff_sacks"})
        .reset_index()
    )
    out["pff_presion"] = ((out["pff_hits"] + out["pff_hurries"] + out["pff_sacks"]) > 0).astype("int8")
    out["blitz"] = (out["n_rushers"] >= 5).astype("int8")
    return carga.optimizar_dtypes(out)


# ------------------------------------------------------------------ tracking
def _nan_row() -> dict:
    keys = [
        "ttt", "t_presion", "presion_trk", "rush_dist_fin", "rush_dist_min", "rush_n3_fin",
        "rush_vel", "cierre_bolsa", "sep_media", "sep_min", "pct_abiertas", "sep_snap_media", "cierre_cobertura",
        "llego_2s", "rush_dist_t2", "rush_n5_t2", "presion_t2", "rush_vel_t2",
        "sep_media_t2", "sep_min_t2", "pct_abiertas_t2", "cierre_cobertura_t2",
    ]
    return {k: np.nan for k in keys}


def features_jugada(g: pd.DataFrame, snap: int | None, fin: int | None) -> dict:
    """Features de una jugada a partir de las posiciones de todos los jugadores.

    g: filas de tracking de una jugada, ya con `pff_role`. snap/fin: frameId del snap y del fin del dropback
    (pase, sack, scramble o fumble).
    """
    row = _nan_row()
    g = g.sort_values(["nflId", "frameId"])
    n_frames = g.groupby("nflId", observed=True).size()
    if n_frames.nunique() != 1:
        return row
    F = int(n_frames.iloc[0])
    P = len(n_frames)
    frame_ids = g["frameId"].to_numpy()[:F]
    x = g["x"].to_numpy(dtype=np.float64).reshape(P, F)
    y = g["y"].to_numpy(dtype=np.float64).reshape(P, F)
    s = g["s"].to_numpy(dtype=np.float64).reshape(P, F)
    roles = g["pff_role"].astype(str).to_numpy()[::F]

    qb, rush = roles == "Pass", roles == "Pass Rush"
    cov, ruta = roles == "Coverage", roles == "Pass Route"
    if qb.sum() != 1 or rush.sum() == 0:
        return row

    i_snap = int(np.searchsorted(frame_ids, snap)) if snap is not None else 0
    i_fin = int(np.searchsorted(frame_ids, fin)) if fin is not None else F - 1
    i_snap, i_fin = min(i_snap, F - 1), min(i_fin, F - 1)
    if i_fin <= i_snap:
        return row

    row["ttt"] = (i_fin - i_snap) / FPS
    # Estado a un reloj fijo (T2 = 2.0 s tras el snap, o la liberación si fue antes). Medir al soltar mezcla la
    # defensa con el estilo ofensivo (pase rápido vs largo); a reloj fijo la comparación entre equipos es justa.
    i_t2 = min(i_snap + int(T_FIJO * FPS), i_fin)
    row["llego_2s"] = float(i_fin - i_snap >= int(T_FIJO * FPS))

    qx, qy = x[qb][0], y[qb][0]
    dr = np.hypot(x[rush] - qx, y[rush] - qy)  # (rushers, frames)
    mind = dr.min(axis=0)
    ventana = mind[i_snap : i_fin + 1]
    cerca = np.flatnonzero(ventana <= PRESION_YD)
    row["presion_trk"] = float(cerca.size > 0)
    row["t_presion"] = cerca[0] / FPS if cerca.size else np.nan
    row["rush_dist_fin"] = mind[i_fin]
    row["rush_dist_min"] = ventana.min()
    row["rush_n3_fin"] = int((dr[:, i_fin] <= 3.0).sum())
    row["rush_vel"] = s[rush][:, i_snap : i_fin + 1].mean()
    row["cierre_bolsa"] = (mind[i_snap] - mind[i_fin]) / row["ttt"]  # yardas/seg que se cierra el bolsillo

    defensores = rush | cov
    if ruta.sum() and defensores.sum():
        def sep_en(i):
            dx = x[ruta][:, None, i] - x[defensores][None, :, i]
            dy = y[ruta][:, None, i] - y[defensores][None, :, i]
            return np.hypot(dx, dy).min(axis=1)  # defensor más cercano a cada ruta

        sep_f, sep_s = sep_en(i_fin), sep_en(i_snap)
        row["sep_media"], row["sep_min"] = sep_f.mean(), sep_f.min()
        row["pct_abiertas"] = (sep_f >= ABIERTO_YD).mean()
        row["sep_snap_media"] = sep_s.mean()
        row["cierre_cobertura"] = sep_s.mean() - sep_f.mean()  # >0: la cobertura se pegó más durante la jugada
        sep_2 = sep_en(i_t2)
        row["sep_media_t2"], row["sep_min_t2"] = sep_2.mean(), sep_2.min()
        row["pct_abiertas_t2"] = (sep_2 >= ABIERTO_YD).mean()
        row["cierre_cobertura_t2"] = sep_s.mean() - sep_2.mean()

    row["rush_dist_t2"] = mind[i_t2]
    row["rush_n5_t2"] = int((dr[:, i_t2] <= 5.0).sum())
    row["presion_t2"] = float(mind[i_snap : i_t2 + 1].min() <= PRESION_YD)
    row["rush_vel_t2"] = s[rush][:, i_snap : i_t2 + 1].mean()
    return row


def features_tracking(game_ids: list[int], pff: pd.DataFrame, lote: int) -> pd.DataFrame:
    roles = pff[["gameId", "playId", "nflId", "pff_role"]].copy()
    roles["nflId"] = roles["nflId"].astype("float32")
    roles["pff_role"] = roles["pff_role"].astype(str)
    filas = []
    t0 = time.time()
    hechos = 0
    for trk in carga.iterar_tracking(game_ids, tam_lote=lote):
        trk = trk[trk["nflId"].notna()]  # fuera el balón
        trk = trk.merge(roles, on=["gameId", "playId", "nflId"], how="inner")
        ev = trk.loc[trk["event"].notna(), ["gameId", "playId", "frameId", "event"]].copy()
        ev["event"] = ev["event"].astype(str)
        snap = ev[ev["event"].isin(EVENTOS_SNAP)].groupby(["gameId", "playId"])["frameId"].min()
        fin = ev[ev["event"].isin(EVENTOS_FIN)].groupby(["gameId", "playId"])["frameId"].min()
        for (gid, pid), g in trk.groupby(["gameId", "playId"], sort=False, observed=True):
            f = features_jugada(g, snap.get((gid, pid)), fin.get((gid, pid)))
            f["gameId"], f["playId"] = gid, pid
            filas.append(f)
        hechos += trk["gameId"].nunique()
        print(f"  tracking: {hechos}/{len(game_ids)} partidos, {len(filas)} jugadas, {time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(filas)
    out["gameId"], out["playId"] = out["gameId"].astype("int32"), out["playId"].astype("int32")
    return out


# ------------------------------------------------------------------ partidos
def resultados_juegos(plays: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Marcador final ESTIMADO: plays.csv solo trae dropbacks, así que se toma el marcador previo a la
    última jugada observada (+6 si esa jugada fue touchdown). Puede omitir puntos de carreras o goles de campo
    posteriores; `resultado_incierto` marca partidos con diferencia <= 10 donde el ganador podría cambiar.
    """
    orden = plays.sort_values(["gameId", "quarter", "clock_seg", "playId"], ascending=[True, True, False, True])
    ult = orden.groupby("gameId").tail(1).set_index("gameId")
    td = (ult["yardas"] >= ult["yardline_100"]) & (ult["es_completo"] == 1)
    local_of = ult["possessionTeam"] == ult["homeTeamAbbr"]
    loc = ult["preSnapHomeScore"] + np.where(td & local_of, 6, 0)
    vis = ult["preSnapVisitorScore"] + np.where(td & ~local_of, 6, 0)
    r = games[["gameId", "season", "week", "gameDate", "homeTeamAbbr", "visitorTeamAbbr"]].set_index("gameId").copy()
    r["pts_local_est"] = loc.reindex(r.index)
    r["pts_visita_est"] = vis.reindex(r.index)
    r["margen_local_est"] = r["pts_local_est"] - r["pts_visita_est"]
    r["ganador"] = np.select([r["margen_local_est"] > 0, r["margen_local_est"] < 0], [r["homeTeamAbbr"], r["visitorTeamAbbr"]], default="EMPATE")
    r["resultado_incierto"] = (r["margen_local_est"].abs() <= 10).astype("int8")
    return r.reset_index()


def tabla_defensores(plays: pd.DataFrame, pff: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    d = pff[pff["pff_role"].isin(["Coverage", "Pass Rush"])].merge(
        plays[["gameId", "playId", "defensiveTeam", "exito_of", "yardas"]], on=["gameId", "playId"], how="left"
    )
    for c in ("pff_hit", "pff_hurry", "pff_sack"):
        d[c] = d[c].fillna(0)
    d["rol"] = d["pff_role"].astype(str)
    d["rush"] = (d["rol"] == "Pass Rush").astype("int8")
    d["cob"] = (d["rol"] == "Coverage").astype("int8")
    d["presion"] = ((d["pff_hit"] + d["pff_hurry"] + d["pff_sack"]) > 0).astype("int8")
    g = d.groupby("nflId", observed=True)
    t = pd.DataFrame(
        {
            "equipo": g["defensiveTeam"].agg(lambda s: s.astype(str).mode().iat[0]),
            "posicion_pff": g["pff_positionLinedUp"].agg(lambda s: s.astype(str).mode().iat[0]),
            "snaps": g.size(),
            "snaps_rush": g["rush"].sum(),
            "snaps_cobertura": g["cob"].sum(),
            "hits": g["pff_hit"].sum(),
            "hurries": g["pff_hurry"].sum(),
            "sacks": g["pff_sack"].sum(),
            "presiones": g["presion"].sum(),
        }
    ).reset_index()
    t["tasa_presion"] = (t["presiones"] / t["snaps_rush"].replace(0, np.nan)).round(4)
    # éxito ofensivo permitido en jugadas donde el jugador estuvo en cobertura
    cob = d[d["cob"] == 1].groupby("nflId", observed=True)["exito_of"].mean().rename("exito_of_en_cobertura")
    t = t.merge(cob, on="nflId", how="left")
    t = t.merge(players[["nflId", "displayName", "officialPosition", "height", "weight"]], on="nflId", how="left")
    return carga.optimizar_dtypes(t)


# ------------------------------------------------------------------ principal
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semanas", type=int, nargs="*", help="filtrar por semana")
    ap.add_argument("--games", type=int, nargs="*", help="filtrar por gameId")
    ap.add_argument("--lote", type=int, default=4, help="partidos de tracking por lote (memoria)")
    ap.add_argument("--salida", type=Path, default=carga.PROCESSED)
    a = ap.parse_args(argv)

    ids = a.games or (carga.game_ids_por_semana(a.semanas) if a.semanas else carga.game_ids_disponibles())
    ids = sorted(set(ids) & set(carga.game_ids_disponibles()))
    if not ids:
        sys.exit("Ningún partido coincide con el filtro.")
    print(f"Partidos a procesar: {len(ids)}")
    a.salida.mkdir(parents=True, exist_ok=True)

    games = carga.cargar_games()
    games = games[games["gameId"].isin(ids)]
    plays = limpiar_plays(carga.cargar_plays(ids), games)
    pff = carga.cargar_pff(ids)
    players = carga.cargar_players()
    print(carga.reporte_memoria(plays, "plays"), "|", carga.reporte_memoria(pff, "pff"))

    resultados = resultados_juegos(plays, games)
    pff_jug = agregar_pff_por_jugada(pff)
    trk = features_tracking(ids, pff, a.lote)

    feat = plays.merge(pff_jug, on=["gameId", "playId"], how="left").merge(trk, on=["gameId", "playId"], how="left")
    assert len(feat) == len(plays), "el merge cambió el número de jugadas"
    feat = carga.optimizar_dtypes(feat)

    resultados.to_csv(a.salida / "games_clean.csv", index=False)
    feat.to_csv(a.salida / "plays_features.csv", index=False)
    tabla_defensores(plays, pff, players).to_csv(a.salida / "defensores_pff.csv", index=False)

    cobertura = trk["sep_media"].notna().mean()
    print(f"OK: {len(feat)} jugadas, {len(resultados)} partidos. Jugadas con features de tracking: {cobertura:.1%}")
    print(f"Escrito en {a.salida}")


if __name__ == "__main__":
    main()

