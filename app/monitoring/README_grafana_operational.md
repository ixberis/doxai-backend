# Grafana Operational Dashboard (UID: adpk75m)

Este documento describe el dashboard operacional embebido en el Admin Panel de DoxAI.

## SSOT

El archivo `grafana_operational_dashboard_adpk75m.json` es la fuente de verdad (SSOT) para el dashboard con UID `adpk75m` que se embebe en `/admin/projects-files/operacion`.

### Configuración Frontend

**Archivo:** `src/config/grafana.ts`  
**Línea 31:**
```typescript
const projectsFilesOpsUid = getEnvVar('VITE_GRAFANA_DASHBOARD_UID_PROJECTS_FILES_OPS');
```

**Variable de entorno en producción:**
```env
VITE_GRAFANA_DASHBOARD_UID_PROJECTS_FILES_OPS=adpk75m
```

---

## Panel IDs (numéricos, estables)

| ID | Título | Métrica Principal | Tipo |
|----|--------|-------------------|------|
| 2 | Ghost Files | `doxai_ghost_files_count` | stat |
| 3 | Storage Delta (últimas 24h) | `doxai_storage_delta_bytes` | stat |
| 4 | Freshness (tiempo desde refresh) | `doxai_db_metrics_last_refresh_timestamp` | stat |
| 5 | Tendencia de Deletes (ops/hr) | `files_delete_total` | timeseries |
| 6 | Latencia de Deletes (p50/p95) | `files_delete_latency_seconds_bucket` | timeseries |
| 7 | Redis Debounce Health | `touch_debounced_*` | timeseries |

---

## Fallback "No data" → 0

Los paneles usan métricas Prometheus que **no precrean labels** (decisión de cardinalidad).
Cuando no hay actividad, estas métricas no existen y Grafana muestra "No data".

### Solución: `OR vector(0)`

Todas las queries usan `OR vector(0)` (sin `on()`) para devolver 0 cuando no hay series.

---

## Queries Finales Exactas (Paneles 2–7)

### Panel 2 — Ghost Files (stat)

```promql
doxai_ghost_files_count OR vector(0)
```

### Panel 3 — Storage Delta (stat)

```promql
doxai_storage_delta_total OR vector(0)
```

### Panel 4 — Freshness (stat)

```promql
time() - doxai_db_metrics_last_refresh_timestamp OR vector(0)
```

### Panel 5 — Tendencia de Deletes (timeseries, ops/hr)

| Target | Expr |
|--------|------|
| A (success) | `sum(rate(files_delete_total{result="success"}[5m])) * 3600 OR vector(0)` |
| B (partial) | `sum(rate(files_delete_total{result="partial"}[5m])) * 3600 OR vector(0)` |
| C (failure) | `sum(rate(files_delete_total{result="failure"}[5m])) * 3600 OR vector(0)` |

### Panel 6 — Latencia de Deletes (timeseries, segundos)

| Target | Expr |
|--------|------|
| A (p50) | `histogram_quantile(0.50, sum(rate(files_delete_latency_seconds_bucket{op="bulk_delete"}[5m])) by (le)) OR vector(0)` |
| B (p95) | `histogram_quantile(0.95, sum(rate(files_delete_latency_seconds_bucket{op="bulk_delete"}[5m])) by (le)) OR vector(0)` |

### Panel 7 — Redis Debounce Health (timeseries, ops/hr)

| Target | Expr |
|--------|------|
| A (allowed) | `sum(rate(touch_debounced_allowed_total[5m])) * 3600 OR vector(0)` |
| B (skipped) | `sum(rate(touch_debounced_skipped_total[5m])) * 3600 OR vector(0)` |
| C (redis_error) | `sum(rate(touch_debounced_redis_error_total[5m])) * 3600 OR vector(0)` |
| D (redis_unavailable) | `sum(rate(touch_debounced_redis_unavailable_total[5m])) * 3600 OR vector(0)` |

---

## Checklist de Validación

| Escenario | Esperado |
|-----------|----------|
| **Sin actividad real** | Paneles 2–7 muestran **0** (no "No data") |
| **Con actividad real** | Paneles muestran **valores reales** (no quedan en 0) |
| Panel IDs en Inspect → JSON | Numéricos: `2`, `3`, `4`, `5`, `6`, `7` |
| UID del dashboard | `adpk75m` |
| Embeds en Admin | Cargan correctamente en `/admin/projects-files/operacion` |

---

## Procedimiento: Aplicar cambios en Grafana Cloud

### Opción A: Editar queries manualmente

1. Abrir Grafana → Dashboards → buscar UID `adpk75m`
2. Para cada panel (2–7):
   - Click en panel → **Edit**
   - Copiar el `expr` de la sección "Queries Finales Exactas"
   - Click **Apply**
3. **Save dashboard** (guardar cambios)

### Opción B: Importar JSON vía API

#### 1. Exportar backup actual

```bash
curl -H "Authorization: Bearer $GRAFANA_API_KEY" \
     "$GRAFANA_URL/api/dashboards/uid/adpk75m" \
     -o backup_adpk75m_$(date +%Y%m%d).json
```

#### 2. Preparar payload de importación

```bash
jq '{dashboard: ., overwrite: true, folderId: 0}' \
   grafana_operational_dashboard_adpk75m.json \
   > import_payload.json
```

#### 3. Importar

```bash
curl -X POST \
     -H "Authorization: Bearer $GRAFANA_API_KEY" \
     -H "Content-Type: application/json" \
     -d @import_payload.json \
     "$GRAFANA_URL/api/dashboards/db"
```

#### 4. Verificar

- UID debe seguir siendo `adpk75m`
- Panel IDs deben ser numéricos (2, 3, 4, 5, 6, 7)
- Iframes en Admin deben cargar sin cambios

---

## Notas de arquitectura

- **No precrear labels:** Por decisión de cardinalidad, el backend NO inicializa métricas con labels vacíos
- **Fallback en PromQL:** La responsabilidad de mostrar 0 es del dashboard, no del backend
- **Panel IDs estables:** Los embeds usan `panelId` numérico para evitar Scene-mode issues
- **Units:**
  - Panel 2/3: `short`/`bytes`
  - Panel 4: `s` (segundos)
  - Panel 5/7: `ops` (ops/hr con multiplicador ×3600)
  - Panel 6: `s` (segundos)
