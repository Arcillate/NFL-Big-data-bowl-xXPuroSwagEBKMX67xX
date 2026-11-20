"""Carga de datos del Big Data Bowl con pandas.

- Rutas relativas a la raíz del proyecto (no dependen del directorio actual).
- Carga por lotes: el tracking vive en un archivo por partido, así que se lee
  solo lo que se pide (filtro por gameId o por semana) y se entrega en lotes.
- Optimización de tipos: enteros y flotantes reducidos, texto repetido a category.

Descripción de columnas: data/raw/README.md
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
RAW = RAIZ / "data" / "raw"
PROCESSED = RAIZ / "data" / "processed"
TRACKING_DIR = RAW / "tracking"

# Tipos explícitos para el tracking (la tabla grande, ~825 MB en CSV).
# float32 alcanza para posiciones/velocidades (precisión de centésimas de yarda).
TRACKING_COLS = {
    "gameId": "int32",
    "playId": "int32",
    "nflId": "float32",  # NaN = balón
    "frameId": "int16",
    "team": "category",
    "playDirection": "category",
    "x": "float32",
    "y": "float32",
    "s": "float32",
    "a": "float32",
    "dis": "float32",
    "o": "float32",
    "dir": "float32",
    "event": "category",
}

PLAYS_DTYPES = {
    "gameId": "int32",
    "playId": "int32",
    "quarter": "int8",
    "preSnapHomeScore": "int16",
    "preSnapVisitorScore": "int16",
    "prePenaltyPlayResult": "int16",
    "playResult": "int16",
    # estas columnas pueden traer NA: float32 y optimizar_dtypes decide el tipo final
    "down": "float32",
    "yardsToGo": "float32",
    "absoluteYardlineNumber": "float32",
    "defendersInBox": "float32",
    "pff_playAction": "float32",
}


def optimizar_dtypes(df: pd.DataFrame, max_categorias: float = 0.5) -> pd.DataFrame:
    """Reduce memoria: downcast numérico y category para texto con pocos valores únicos."""
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_integer_dtype(s):
            df[col] = pd.to_numeric(s, downcast="integer")
        elif pd.api.types.is_float_dtype(s):
            sin_na = s.dropna()
            if len(sin_na) and (sin_na == sin_na.round()).all() and sin_na.abs().max() < 2**31:
                if s.isna().any():
                    df[col] = s.astype("float32")
                else:
                    df[col] = pd.to_numeric(s, downcast="integer")
            else:
                df[col] = pd.to_numeric(s, downcast="float")
        elif s.dtype == object:
            if s.nunique(dropna=True) / max(len(s), 1) < max_categorias:
                df[col] = s.astype("category")
    return df


def _filtrar(df: pd.DataFrame, game_ids: Iterable[int] | None) -> pd.DataFrame:
    if game_ids is None:
        return df
    return df[df["gameId"].isin(set(int(g) for g in game_ids))].reset_index(drop=True)


def cargar_games() -> pd.DataFrame:
    df = pd.read_csv(RAW / "games.csv", dtype={"gameId": "int32", "season": "int16", "week": "int8"})
    df["gameDate"] = pd.to_datetime(df["gameDate"], format="%m/%d/%Y")
    return optimizar_dtypes(df)


def cargar_players() -> pd.DataFrame:
    df = pd.read_csv(RAW / "players.csv", dtype={"nflId": "int32"})
    return optimizar_dtypes(df)


def cargar_plays(game_ids: Iterable[int] | None = None) -> pd.DataFrame:
    df = pd.read_csv(RAW / "plays.csv", dtype=PLAYS_DTYPES)
    return optimizar_dtypes(_filtrar(df, game_ids))


def cargar_pff(game_ids: Iterable[int] | None = None) -> pd.DataFrame:
    df = pd.read_csv(RAW / "pffScoutingData.csv", dtype={"gameId": "int32", "playId": "int32", "nflId": "int32"})
    return optimizar_dtypes(_filtrar(df, game_ids))


def game_ids_disponibles() -> list[int]:
    """gameId de los archivos de tracking presentes en data/raw/tracking."""
    ids = []
    for p in TRACKING_DIR.glob("tracking_*.csv"):
        m = re.fullmatch(r"tracking_(\d+)\.csv", p.name)
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


def game_ids_por_semana(semanas: Sequence[int]) -> list[int]:
    g = cargar_games()
    return sorted(g.loc[g["week"].isin(list(semanas)), "gameId"].astype(int).tolist())


def cargar_tracking_juego(game_id: int, columnas: Sequence[str] | None = None) -> pd.DataFrame:
    """Un partido de tracking con tipos optimizados. `columnas` limita lo que se lee."""
    cols = list(columnas) if columnas else list(TRACKING_COLS)
    df = pd.read_csv(
        TRACKING_DIR / f"tracking_{int(game_id)}.csv",
        usecols=cols,
        dtype={c: TRACKING_COLS[c] for c in cols},
    )
    return df


def iterar_tracking(
    game_ids: Iterable[int] | None = None,
    tam_lote: int = 4,
    columnas: Sequence[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Entrega el tracking en lotes de `tam_lote` partidos, filtrando por gameId.

    Mantiene en memoria solo un lote a la vez.
    """
    ids = sorted(int(g) for g in (game_ids if game_ids is not None else game_ids_disponibles()))
    disponibles = set(game_ids_disponibles())
    faltan = [g for g in ids if g not in disponibles]
    if faltan:
        raise FileNotFoundError(f"Sin archivo de tracking para gameId: {faltan[:5]}...")
    for i in range(0, len(ids), tam_lote):
        lote = ids[i : i + tam_lote]
        yield pd.concat([cargar_tracking_juego(g, columnas) for g in lote], ignore_index=True)


def cargar_tracking(game_ids: Iterable[int], columnas: Sequence[str] | None = None) -> pd.DataFrame:
    """Conveniencia: concatena el tracking de pocos partidos (úsalo con filtros)."""
    ids = list(game_ids)
    return pd.concat(list(iterar_tracking(ids, tam_lote=max(len(ids), 1), columnas=columnas)), ignore_index=True)


def reporte_memoria(df: pd.DataFrame, nombre: str = "df") -> str:
    mb = df.memory_usage(deep=True).sum() / 1024**2
    return f"{nombre}: {len(df):,} filas x {df.shape[1]} cols, {mb:.1f} MB"


if __name__ == "__main__":
    ids = game_ids_disponibles()
    print(f"{len(ids)} partidos de tracking disponibles")
    print(reporte_memoria(cargar_games(), "games"))
    print(reporte_memoria(cargar_plays(), "plays"))
    print(reporte_memoria(cargar_pff(), "pff"))
    lote = next(iterar_tracking(ids[:2]))
    print(reporte_memoria(lote, "tracking (2 partidos)"))
