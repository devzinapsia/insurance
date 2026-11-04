# Guía de implementación para usuarios — Gestión de seguros

Guía para los usuarios finales del módulo `insurance_management`, en
español, armada para importarse en **Knowledge** (Odoo Enterprise) con el
módulo `knowledge_transfer` de Zinapsia (repo `devzinapsia/knowledge`).

Se actualiza **en cada fase y en cada versión del módulo**: cuando cambia
algo visible para el usuario, se edita el artículo que corresponde y se
agrega la entrada en `articulos/11_novedades.html`.

## Estructura

- `articulos/*.html`: un archivo por artículo (fuente editable). HTML simple
  (títulos, párrafos, listas, tablas y avisos `alert`) que Knowledge muestra
  tal cual.
- `build_knowledge_zip.py`: arma el ZIP importable. El árbol de artículos
  (nombres, íconos, orden) está definido en la lista `ARTICLES` del script.
- `guia_gestion_seguros_knowledge.zip`: el ZIP generado, listo para
  importar.

Los artículos pueden tener subartículos: en `ARTICLES`, el segundo valor es
la clave del artículo padre (por ejemplo, *Parametrización contable* cuelga
de *Puesta en marcha*).

Imágenes: se guardan en `img/` y se usan en el artículo como
`<img src="../img/<archivo>.png" .../>` (así se ven al abrir el HTML en un
navegador). El script las empaqueta como adjuntos de `knowledge_transfer`
(`attachments/` + marca `kt-attachment:N:image`) y al importar quedan como
adjuntos del artículo.

## Regenerar el ZIP

```bash
python3 docs/guia_usuario/build_knowledge_zip.py
```

## Importar en Knowledge

1. Instalar `knowledge_transfer` en la base (repo `devzinapsia/knowledge`).
2. **Knowledge › Transfer › Import**, subir el ZIP y pulsar *Import*.
3. El árbol queda en la sección privada de quien importa, dentro de
   "Artículos importados Zinapsia", con la fecha y hora agregadas al nombre
   del artículo raíz. Moverlo a *Workspace*, renombrarlo si hace falta y
   compartirlo con los usuarios de Seguros.

Sin `knowledge_transfer`, también se puede crear cada artículo a mano en
Knowledge y pegar el contenido del HTML correspondiente abierto en un
navegador.

## Pendiente para próximas versiones

- Más capturas de pantalla (ya se admiten: ver *Imágenes*).
