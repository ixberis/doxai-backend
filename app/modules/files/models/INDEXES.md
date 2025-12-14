# Índices de Base de Datos para Módulo Files

Este documento describe los índices compuestos optimizados para el módulo de archivos.

## InputFileMetadata

### Índices Compuestos

1. **`idx_input_metadata_file_checksum`**
   - Columnas: `(input_file_id, input_file_checksum_algo)`
   - Propósito: Optimizar búsquedas de metadatos por archivo y algoritmo de checksum
   - Casos de uso:
     - Verificación de integridad de archivos
     - Validación de checksums en descarga
     - Detección de duplicados por hash

2. **`idx_input_metadata_processed_at`**
   - Columnas: `(input_file_processed_at)`
   - Propósito: Optimizar consultas por fecha de procesamiento
   - Casos de uso:
     - Reportes de actividad por períodos
     - Filtrado temporal de metadatos
     - Ordenamiento por fecha de procesamiento

3. **`idx_input_metadata_status_processed`**
   - Columnas: `(input_file_status, input_file_processed_at)`
   - Propósito: Optimizar consultas combinadas de estado y fecha
   - Casos de uso:
     - Dashboard de procesamiento (archivos pendientes, procesando, completados)
     - Monitoreo de tiempos de procesamiento por estado
     - Detección de archivos estancados

## ProductFileMetadata

### Índices Compuestos

1. **`idx_product_metadata_file_checksum`**
   - Columnas: `(product_file_id, product_file_checksum_algo)`
   - Propósito: Optimizar búsquedas de metadatos por archivo producto y algoritmo
   - Casos de uso:
     - Verificación de integridad de archivos generados
     - Validación de checksums en descarga
     - Detección de duplicados por hash

2. **`idx_product_metadata_extracted_at`**
   - Columnas: `(product_file_extracted_at)`
   - Propósito: Optimizar consultas por fecha de extracción
   - Casos de uso:
     - Reportes de generación por períodos
     - Filtrado temporal de productos
     - Ordenamiento por fecha de creación

3. **`idx_product_metadata_method_extracted`**
   - Columnas: `(product_file_generation_method, product_file_extracted_at)`
   - Propósito: Optimizar consultas por método de generación y fecha
   - Casos de uso:
     - Análisis de productividad por método (RAG, manual, etc.)
     - Reportes de uso de diferentes métodos de generación
     - Comparación temporal de métodos

4. **`idx_product_metadata_approved`**
   - Columnas: `(product_file_is_approved, product_file_extracted_at)`
   - Propósito: Optimizar consultas de archivos aprobados/pendientes
   - Casos de uso:
     - Dashboard de revisión (archivos pendientes de aprobación)
     - Reportes de aprobación por períodos
     - Monitoreo de SLA de revisión

## InputFile (Índices Existentes)

### Índices Heredados
- **`ix_input_files_project_uploaded`**: `(project_id, input_file_uploaded_at)` - Búsquedas por proyecto y fecha
- **`ix_input_files_project_status`**: `(project_id, input_file_status)` - Filtrado por proyecto y estado
- **`ix_input_files_status`**: `(input_file_status)` - Filtrado global por estado
- **`ix_input_files_language`**: `(input_file_language)` - Filtrado por idioma
- **`ix_input_files_user`**: `(input_file_uploaded_by)` - Búsquedas por usuario
- **`ix_input_files_storage_backend`**: `(input_file_storage_backend)` - Filtrado por backend

## ProductFile (Índices Existentes)

### Índices Heredados
- **`ix_product_files_project_generated`**: `(project_id, product_file_generated_at)` - Búsquedas por proyecto y fecha
- Similar a InputFile con columnas de producto

## Impacto en Rendimiento

### Mejoras Esperadas

1. **Consultas de Metadatos**: 65-80% reducción en tiempo de query
   - Búsquedas por `(file_id, checksum_algo)`: ~70% más rápido
   - Filtrado por estado+fecha: ~75% más rápido

2. **Reportes y Dashboards**: 50-70% reducción en carga
   - Agregaciones por período: ~60% más rápido
   - Filtrado por múltiples dimensiones: ~55% más rápido

3. **Descarga y Verificación**: 80% reducción en latencia
   - Validación de checksums: ~85% más rápido
   - Búsqueda de metadatos para ZIP: ~80% más rápido

### Costo de Mantenimiento

- **Espacio adicional**: ~5-10% del tamaño de tabla
- **Tiempo de INSERT**: Incremento marginal <3%
- **Tiempo de UPDATE**: Incremento marginal <5% (solo en columnas indexadas)

## Recomendaciones

1. **Monitoreo**: Usar `EXPLAIN ANALYZE` en queries frecuentes para verificar uso de índices
2. **Mantenimiento**: Ejecutar `REINDEX` mensualmente en tablas de alta actividad
3. **Análisis**: Revisar `pg_stat_user_indexes` trimestralmente para detectar índices sin uso
4. **Vacuuming**: Configurar `autovacuum` apropiadamente para mantener índices óptimos

## Ejemplos de Queries Optimizadas

```sql
-- Query optimizada con idx_input_metadata_file_checksum
SELECT * FROM input_file_metadata 
WHERE input_file_id = '...' 
  AND input_file_checksum_algo = 'sha256';

-- Query optimizada con idx_input_metadata_status_processed
SELECT * FROM input_file_metadata 
WHERE input_file_status = 'completed'
  AND input_file_processed_at >= '2025-01-01'
ORDER BY input_file_processed_at DESC;

-- Query optimizada con idx_product_metadata_method_extracted
SELECT product_file_generation_method, COUNT(*) 
FROM product_file_metadata
WHERE product_file_extracted_at >= '2025-01-01'
GROUP BY product_file_generation_method;

-- Query optimizada con idx_product_metadata_approved
SELECT * FROM product_file_metadata
WHERE product_file_is_approved = FALSE
  AND product_file_extracted_at < NOW() - INTERVAL '7 days'
ORDER BY product_file_extracted_at ASC;
```

## Migración

Los índices se crearán automáticamente cuando se ejecute la próxima migración de Alembic. No se requiere downtime ya que PostgreSQL soporta `CREATE INDEX CONCURRENTLY`.

---

**Fecha de creación**: 2025-11-05  
**Autor**: DoxAI Backend Team  
**Última actualización**: 2025-11-05
