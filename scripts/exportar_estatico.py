"""Exporta cada respuesta de la API a JSON para publicar la página en GitHub Pages (sin servidor Python).

Escribe en dashboard/static-api/api/. Vite copia esa carpeta al build cuando se compila con `npm run build:pages`.
Nombre de archivo: la ruta con '?' -> '__' y '=' o '&' -> '-', más '.json'
  matriz?excluye_sacks=true  ->  api/matriz__excluye_sacks-true.json
  equipo/BUF                 ->  api/equipo/BUF.json
dashboard/src/api.ts aplica la misma regla en modo 'pages'. Si agregas un endpoint al dashboard, agrégalo aquí.

Uso: python data/scripts/exportar_estatico.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import VARIABLES_X, app  # noqa: E402

DESTINO = RAIZ / "dashboard" / "static-api" / "api"


def nombre_archivo(ruta: str) -> str:
    return ruta.replace("?", "__", 1).replace("=", "-").replace("&", "-") + ".json"


def main() -> None:
    c = TestClient(app)
    rutas = [
        "resumen", "ranking", "standings", "interaccion", "correlaciones", "calibracion", "equipos",
        "ttp/curvas", "ttp/grupos", "ttp/equipos", "ttp/posiciones", "ttp/mas-rapidos",
        "animaciones", "ranking-semanal", "descomposicion",
        *[f"matriz?excluye_sacks={v}" for v in ("false", "true")],
        *[f"escenarios?excluye_sacks={v}" for v in ("false", "true")],
        *[f"ridgeline?familia={f}" for f in ("rushers", "posicion", "equipo")],
        *[f"dispersion?x={x}" for x in VARIABLES_X],
    ]
    rutas += [f"equipo/{e}" for e in c.get("/api/equipos").json()]
    rutas += [f"animaciones/{a['gameId']}/{a['playId']}" for a in c.get("/api/animaciones").json()]

    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    total = 0
    for r in rutas:
        res = c.get(f"/api/{r}")
        if res.status_code != 200:
            sys.exit(f"ERROR {res.status_code} en /api/{r}: {res.text[:200]}")
        f = DESTINO / nombre_archivo(r)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(res.text, encoding="utf-8")
        total += f.stat().st_size
    print(f"OK: {len(rutas)} archivos, {total / 1024**2:.1f} MB en {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
