"""Build the user guide as a ZIP importable with Zinapsia's knowledge_transfer.

The guide is written as one HTML file per article in ``articulos/``. This
script packs them in the knowledge_transfer format (manifest.json + one
``articles/<key>/body.html`` per article, format_version 1) so the whole tree
can be imported in Knowledge > Transfer > Import.

Usage (no Odoo needed):
    python3 docs/guia_usuario/build_knowledge_zip.py
Output:
    docs/guia_usuario/guia_gestion_seguros_knowledge.zip
"""

import json
import pathlib
import zipfile
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
SOURCE_DIR = HERE / "articulos"
OUTPUT = HERE / "guia_gestion_seguros_knowledge.zip"
ODOO_SERIES = "19.0"
FORMAT_VERSION = 1

# (key, parent key, article name, icon, source file). Parents must come
# before their children; the order is the order shown in Knowledge.
ARTICLES = [
    ("guia", None, "Gestión de seguros – Guía de implementación", "🛡️", "00_inicio.html"),
    ("conceptos", "guia", "Conceptos y alcance", "📘", "01_conceptos.html"),
    ("puesta_en_marcha", "guia", "Puesta en marcha", "🚀", "02_puesta_en_marcha.html"),
    ("cargar_poliza", "guia", "Cargar una póliza", "📝", "03_cargar_poliza.html"),
    ("estados", "guia", "Estados de la póliza", "🔄", "04_estados.html"),
    ("avisos", "guia", "Avisos de vencimiento", "⏰", "05_avisos.html"),
    ("renovacion", "guia", "Renovar o no renovar", "🔁", "06_renovacion.html"),
    ("documentos", "guia", "Documentos", "📎", "07_documentos.html"),
    ("endosos", "guia", "Endosos", "✏️", "12_endosos.html"),
    ("cuotas_facturas", "guia", "Cuotas y facturas", "🧾", "13_cuotas_facturas.html"),
    ("pagos", "guia", "Pagos y cuotas impagas", "💳", "14_pagos.html"),
    ("devengamiento", "guia", "Devengamiento", "📅", "15_devengamiento.html"),
    ("carga_inicial", "guia", "Carga inicial e importación", "📥", "16_carga_inicial.html"),
    ("consultas", "guia", "Consultas y reportes", "📊", "08_consultas.html"),
    ("permisos", "guia", "Permisos y costos ocultos", "🔐", "09_permisos.html"),
    ("faq", "guia", "Preguntas frecuentes", "❓", "10_faq.html"),
    ("novedades", "guia", "Novedades por versión", "🆕", "11_novedades.html"),
]


def build():
    manifest_articles = []
    bodies = {}
    sequence_by_parent = {}
    for key, parent_key, name, icon, filename in ARTICLES:
        body = (SOURCE_DIR / filename).read_text(encoding="utf-8").strip()
        body_path = f"articles/{key}/body.html"
        bodies[body_path] = body
        sequence = sequence_by_parent.get(parent_key, 0) + 1
        sequence_by_parent[parent_key] = sequence
        manifest_articles.append(
            {
                "key": key,
                "parent_key": parent_key,
                "sequence": sequence,
                "name": name,
                "icon": icon,
                "full_width": False,
                "is_article_item": False,
                "body": body_path,
                "cover": None,
                "stage_key": None,
                "stages": [],
                "properties_definition": [],
                "properties": {},
                "attachments": [],
            }
        )
    manifest = {
        "format_version": FORMAT_VERSION,
        "odoo_series": ODOO_SERIES,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "articles": manifest_articles,
        "attachments": [],
        "warnings": [],
    }
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for path, body in bodies.items():
            archive.writestr(path, body)
    return OUTPUT, len(manifest_articles)


if __name__ == "__main__":
    output, count = build()
    print(f"{output} ({count} articles)")
