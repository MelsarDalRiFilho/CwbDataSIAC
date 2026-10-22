# /// script
# requires-python = ">=3.12"
# dependencies = ["pyshp>=2.3", "pyproj>=3.6", "shapely>=2.0"]
# ///
"""Converte a divisa de bairros do IPPUC (shapefile SIRGAS 2000 / UTM 22S) em GeoJSON WGS84.

Fonte: IPPUC — Instituto de Pesquisa e Planejamento Urbano de Curitiba,
https://ippuc.org.br/geodownloads/geo.htm (SHAPES_SIRGAS/DIVISA_DE_BAIRROS_SIRGAS.zip).

    curl -o /tmp/bairros.zip https://ippuc.org.br/geodownloads/SHAPES_SIRGAS/DIVISA_DE_BAIRROS_SIRGAS.zip
    unzip /tmp/bairros.zip -d /tmp/bairros
    uv run scripts/build_bairros_geojson.py /tmp/bairros/DIVISA_DE_BAIRROS \
        dashboard/geo/bairros.geojson

A propriedade `chave` (maiúsculas, sem acento) casa com o `bairro` do SIAC 156.
"""

import json
import sys
import unicodedata
from pathlib import Path

import shapefile
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape

# ~10 m em graus: suficiente para um mapa da cidade inteira, arquivo bem menor.
SIMPLIFY_TOLERANCE = 0.0001
DECIMALS = 5
# Nomes do IPPUC que o SIAC 156 escreve de outro jeito.
ALIASES = {"CIDADE INDUSTRIAL DE CURITIBA": "CIDADE INDUSTRIAL"}


def chave(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    normalizado = " ".join(sem_acento.upper().split())
    return ALIASES.get(normalizado, normalizado)


def titulo(nome: str) -> str:
    """Caixa de título sem capitalizar preposições: "Cidade Industrial de Curitiba"."""
    palavras = nome.strip().lower().split()
    return " ".join(
        p if i and p in {"de", "da", "do", "das", "dos", "e"} else p.capitalize()
        for i, p in enumerate(palavras)
    )


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(c, DECIMALS) for c in coords]
    return [_round(c) for c in coords]


def main(source: str, dest: str) -> None:
    reader = shapefile.Reader(source, encoding="latin-1")
    to_wgs84 = Transformer.from_crs("EPSG:31982", "EPSG:4326", always_xy=True).transform

    features = []
    for record, geom in zip(reader.records(), reader.shapes(), strict=True):
        polygon = shapely.transform(
            shape(geom.__geo_interface__), to_wgs84, interleaved=False
        ).simplify(SIMPLIFY_TOLERANCE)
        geometry = mapping(polygon)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "nome": titulo(record["NOME"]),
                    "chave": chave(record["NOME"]),
                    "regional": titulo(record["NM_REGIONA"]),
                },
                "geometry": {**geometry, "coordinates": _round(geometry["coordinates"])},
            }
        )

    collection = {
        "type": "FeatureCollection",
        "attribution": "Divisa de bairros: IPPUC (ippuc.org.br/geodownloads)",
        "features": sorted(features, key=lambda f: f["properties"]["chave"]),
    }
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(collection, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(features)} bairros → {dest} ({Path(dest).stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
