"""Analytics + data quality sobre snapshots de la tabla `jobs`.

Submódulos:
- `schema`: modelo pydantic con invariantes de calidad por fila.
- `export`: dump Postgres → Parquet (snapshot inmutable, fácil de compartir).
- `quality`: valida cada fila del Parquet contra `JobRow` y reporta diferencias.
- `analyze`: queries DuckDB sobre el Parquet (fit rate, distribución, top companies).

Diseño:
- El Parquet es el contrato. Una vez exportado, schema y queries operan
  sobre archivo, sin tocar la DB. Esto permite compartir snapshots con
  cualquiera sin credenciales y re-correr análisis sin costo de DB.
- DuckDB lee Parquet en place, sin importar a tabla. Cero pipeline.
- pydantic v2 valida fila por fila — es más portable y debuggeable
  que Great Expectations para una tabla de este tamaño.
"""
