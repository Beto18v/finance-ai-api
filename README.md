# dinerance-api

Backend REST de Dinerance. Expone autenticacion por token de Supabase, dominio monetario, analytics, obligaciones, caja futura e importacion CSV.

## Estado actual

Hoy esta API ya resuelve:

- bootstrap y sincronizacion del perfil local del usuario autenticado
- perfil financiero con `base_currency` y `timezone`
- cuentas financieras con una cuenta default obligatoria
- transacciones normales de `income` y `expense`
- ledger operativo con transferencias, ajustes, saldos actuales y actividad reciente
- analytics mensuales, breakdown por categoria y candidatos recurrentes
- obligaciones con pago atomico al ledger
- forecast de caja y safe-to-spend
- importacion CSV con preview, deduplicacion basica, reconciliacion y commit seguro

## Stack

- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Supabase Auth con validacion JWT
- `uv` para entorno y dependencias

## Estructura actual

```text
app/
  analytics/   calculos reutilizables para balance mensual, breakdown y recurrencias
  core/        auth, settings, errores y helpers financieros
  database/    engine, base declarativa y dependency de sesion
  models/      user, category, financial_account, transaction, obligation, ingestion, exchange_rate
  routes/      contratos HTTP por modulo
  schemas/     request y response models
  services/    logica de dominio
  main.py      inicializacion de FastAPI y registro de routers
alembic/
  versions/    migraciones de esquema
tests/
  suite de backend
```

## Reglas de dominio vigentes

- El contexto actual es una sola cuenta personal por usuario autenticado.
- Cada usuario tiene una `base_currency` y una `timezone`.
- Toda cuenta financiera usa la misma moneda base del usuario.
- `POST /transactions` y `PUT /transactions/{id}` operan solo sobre `income` y `expense`.
- Todo movimiento monetario se persiste con `amount > 0`.
- Transferencias y ajustes usan endpoints propios y no entran en los analytics mensuales.
- El ledger es la fuente de verdad de la caja actual observada.
- Las obligaciones viven separadas del ledger hasta que el usuario marca un pago.
- La importacion CSV vive en sesiones de ingesta separadas del ledger hasta el commit.

## Modulos y endpoints actuales

### Salud y configuracion

- `GET /healthz`

### Usuarios

- `POST /users/`
- `GET /users/me`
- `POST /users/me/bootstrap`
- `PUT /users/me`
- `DELETE /users/me`

### Categorias

- `POST /categories/`
- `GET /categories/`
- `GET /categories/{category_id}`
- `PUT /categories/{category_id}`
- `DELETE /categories/{category_id}`

### Cuentas financieras

- `POST /financial-accounts/`
- `GET /financial-accounts/`
- `GET /financial-accounts/{account_id}`
- `PUT /financial-accounts/{account_id}`
- `DELETE /financial-accounts/{account_id}`

### Transacciones normales

- `POST /transactions/`
- `GET /transactions/`
- `GET /transactions/{transaction_id}`
- `PUT /transactions/{transaction_id}`
- `DELETE /transactions/{transaction_id}`

`GET /transactions/` responde con pagina, `total_count`, `limit`, `offset` y `summary`.

### Ledger operativo

- `POST /transfers/`
- `DELETE /transfers/{transfer_group_id}`
- `POST /adjustments/`
- `DELETE /adjustments/{adjustment_id}`
- `GET /ledger/balances`
- `GET /ledger/activity`

### Analytics y caja futura

- `GET /balance/monthly`
- `GET /analytics/summary`
- `GET /analytics/category-breakdown`
- `GET /analytics/recurring-candidates`
- `GET /cashflow/forecast`
- `GET /cashflow/safe-to-spend`

### Obligaciones

- `POST /obligations/`
- `GET /obligations/upcoming`
- `GET /obligations/`
- `PATCH /obligations/{obligation_id}`
- `DELETE /obligations/{obligation_id}`
- `POST /obligations/{obligation_id}/mark-paid`

### Ingesta CSV

- `GET /ingestion/import-capabilities`
- `GET /ingestion/imports`
- `GET /ingestion/imports/{import_session_id}`
- `POST /ingestion/imports/csv`
- `PATCH /ingestion/imports/{import_session_id}/items/{item_id}`
- `POST /ingestion/imports/{import_session_id}/commit`

## Persistencia actual

Las tablas principales del dominio son:

- `users`
- `categories`
- `financial_accounts`
- `transactions`
- `obligations`
- `import_sessions`
- `import_items`
- `exchange_rates`

La carpeta `alembic/versions/` ya contiene migraciones para:

- esquema base
- RLS y politicas
- perfil monetario y snapshots FX
- cuentas financieras y tipos de transaccion
- `balance_direction` del ledger
- obligaciones
- importacion CSV y metadata de analisis

## Variables de entorno

Desarrollo local:

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
DB_SSLMODE=require
SUPABASE_URL=https://<project-ref>.supabase.co
CORS_ORIGINS=http://localhost:3000
```

Fallback legacy para JWT, solo si no usas JWKS:

```env
SUPABASE_JWT_SECRET=<legacy_jwt_secret>
JWT_ALGORITHMS=HS256
JWT_VERIFY_AUD=false
JWT_AUDIENCE=authenticated
```

## Arranque local

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Checks utiles:

```bash
curl http://127.0.0.1:8000/healthz
curl -X POST -H "Authorization: Bearer <access_token>" http://127.0.0.1:8000/users/me/bootstrap
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8000/users/me
```

## Tests

La suite vive en `tests/` y cubre:

- usuarios y perfil
- categorias y transacciones
- cuentas financieras
- ledger, transferencias y ajustes
- analytics y FX
- obligaciones
- cashflow
- ingesta CSV
- health checks y configuracion

Comando:

```bash
uv run pytest
```
