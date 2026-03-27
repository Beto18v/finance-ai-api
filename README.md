# dinerance-api

API backend para un SaaS de finanzas personales. Este documento esta escrito como mapa tecnico del proyecto: que hace cada capa, donde estan los riesgos, y que revisar cuando vuelvas al repo despues de un tiempo.

## Resumen rapido

- Framework HTTP: FastAPI.
- Persistencia: SQLAlchemy 2.x + PostgreSQL (Supabase).
- Auth: JWT de Supabase Auth, validacion por JWKS (modo recomendado) o secreto legacy.
- Migraciones: Alembic.
- Entorno/dependencias: `uv`.

## Arquitectura por capas (carpeta `app/`)

- `core/`
  - `auth.py`: valida bearer token y extrae claims (`sub`, `email`, metadata).
  - `settings.py`: config de app.
  - `errors.py`: manejo de errores comunes.
- `database/`
  - `connection.py`: crea engine y session factory.
  - `session.py`: dependency `get_db` para FastAPI.
  - `base.py`: base declarativa de SQLAlchemy.
- `models/`
  - `user.py`, `category.py`, `transaction.py`: entidades SQLAlchemy.
- `schemas/`
  - contratos Pydantic para requests/responses.
- `services/`
  - logica de negocio por recurso (usuarios, categorias, transacciones).
  - todas las funciones reciben `user_id: UUID` tipado para consistencia.
  - no llaman `db.add()` en objetos ya rastreados por la sesion; solo `db.commit()`.
  - `list_transactions()` centraliza filtros (categoria, rango de fechas, limit/offset).
- `routes/`
  - endpoints HTTP que acoplan auth + schemas + services.
- `main.py`
  - inicializacion de la app, routers, CORS, health endpoint.

## Flujo de autenticacion y multitenancy

1. El cliente obtiene `access_token` en Supabase Auth.
2. El backend recibe `Authorization: Bearer <token>`.
3. `app/core/auth.py` valida JWT (JWKS o secret legacy).
4. Del claim `sub` sale el `user_id` canonico del sistema.
5. `POST /users/me/bootstrap` crea el perfil local la primera vez (o sincroniza email/nombre si ya existe).
6. `GET /users/me` devuelve el perfil activo y mantiene el email sincronizado con Auth.
7. `categories` y `transactions` siempre operan filtrando por `user_id`.

Idea clave: la aislacion por usuario ya existia a nivel API (filtros en services), y ahora tambien se refuerza a nivel DB con RLS.

## Modelo de datos (alto nivel)

- `users`
  - `id` UUID (coincide con `auth.users.id` via claim `sub`).
  - `email` unico.
  - `name`, `base_currency`, `timezone`, timestamps y `deleted_at`.
- `categories`
  - pertenece a `user_id`.
  - soporte de jerarquia por `parent_id`.
  - `direction`: `income` o `expense`.
  - no se puede borrar si aun tiene subcategorias o transacciones asociadas.
- `transactions`
  - pertenece a `user_id`.
  - referencia `category_id`.
  - `amount`, `currency`, `occurred_at`.
  - snapshot FX persistido: `fx_rate`, `fx_rate_date`, `fx_rate_source`, `base_currency`, `amount_in_base_currency`.
- `exchange_rates`
  - tabla global de tasas historicas entre pares de monedas.
  - lookup por `base_currency`, `quote_currency`, `rate_date`, `source`.

## Perfil monetario y politica FX

- Cada usuario define una sola `base_currency` en su perfil. Esa es la moneda canonica de analytics.
- `timezone` tambien vive en perfil y se usa para cortes mensuales en analytics.
- Si el usuario ya tiene transacciones y su `base_currency` ya estaba definida, no puede cambiarla.
- El producto actual opera monomoneda: las transacciones nuevas deben usar la misma moneda que `user.base_currency`.
- Si el usuario viene de datos legacy sin `base_currency`, la primera asignacion puede disparar backfill de snapshots FX historicos.
- Cada transaccion conserva su `amount` y `currency` originales, pero tambien guarda el snapshot de conversion hacia `user.base_currency`.
- Si la moneda original y la base son iguales, el snapshot usa tasa identidad (`fx_rate = 1`, `fx_rate_source = "identity"`).
- Si son distintas, se busca una tasa historica en `exchange_rates`.
- Fallback por fecha: primero tasa exacta del dia; si no existe, la mas reciente anterior dentro de 7 dias; si tampoco existe, se intenta el par inverso; si sigue faltando, la transaccion queda sin `amount_in_base_currency`.
- Regla dura: ningun agregado mezcla montos crudos de distintas monedas. La arquitectura FX queda preparada, pero el contrato actual de producto evita ese caso obligando transacciones en moneda base.

## Reglas de producto vigentes

- Dinerance opera como producto monomoneda.
- Cada usuario trabaja con una sola `base_currency`.
- Toda transaccion nueva debe usar `user.base_currency`.
- `base_currency` y `timezone` se resuelven en onboarding y luego viven en perfil.
- Ningun agregado puede mezclar montos crudos de distintas monedas.
- Si existen datos legacy no convertibles, se excluyen del agregado y se informa; no se mezclan silenciosamente.
- `exchange_rates` y los snapshots FX son infraestructura interna de compatibilidad y evolucion futura, no un flujo visible de producto.

## Analytics

- `app/analytics/` concentra calculos reutilizables y deja de depender de `SUM(amount)` SQL directo.
- El balance mensual ahora:
  - agrupa por mes usando `user.timezone`.
  - suma solo `amount_in_base_currency`.
  - devuelve la moneda del agregado sin mezclar montos crudos.
  - trata timestamps sin timezone como UTC para mantener consistencia entre SQLite de tests y Postgres.
- Esto deja la base preparada para futuros analytics y para reactivar conversiones multi-moneda sin repetir reglas.

## Seguridad y avisos de Supabase

### 1) Leaked password protection desactivado (Auth)

Este aviso es de configuracion en Supabase Auth (no del codigo Python ni de SQLAlchemy).

Que activar en Supabase:

- Dashboard -> Authentication -> Providers/Settings (segun UI actual).
- Password security -> Leaked password protection -> Enable.

Efecto:

- Supabase bloquea passwords comprometidas (HaveIBeenPwned).
- Reduce riesgo de account takeover por reutilizacion de claves filtradas.

### 2) `public.users` sin RLS

Se agrego una migracion para habilitar RLS en tablas publicas del dominio y politicas por usuario autenticado:

- `alembic/versions/9c2df3d91a7a_enable_rls_on_public_tables.py`

La migracion hace:

- `ENABLE ROW LEVEL SECURITY` y `FORCE ROW LEVEL SECURITY` en:
  - `public.users`
  - `public.categories`
  - `public.transactions`
- Crea politicas `SELECT/INSERT/UPDATE/DELETE` para `authenticated`.
- Cada politica compara la fila con el claim JWT `sub` (`request.jwt.claim.sub`).

Nota operativa:

- Si el backend conecta como `postgres` (rol superuser), puede bypassear RLS (propio de Postgres).
- Igual conviene mantener RLS activa para cualquier acceso via PostgREST/SDK y para modelo de seguridad en profundidad.

## Variables de entorno (referencia)

Para separar local de produccion, usa:

- `.env.local` solo en maquina para desarrollo.
- variables del entorno/plataforma en Azure u otro host para produccion.
- `.env.example` y `.env.local.example` solo como plantillas documentadas.

La API solo intenta cargar `.env.local` en desarrollo. En produccion debe leer
sus variables directamente del entorno del proceso.

Base de datos:

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
# Opcional si DATABASE_URL no incluye sslmode
DB_SSLMODE=require
```

Nota operativa:

- La conexion directa `db.<project>.supabase.co:5432` puede requerir IPv6 en algunos entornos.
- Si ves timeouts al conectar desde local en Windows o tu red no tiene salida IPv6 funcional, usa el connection string del `Session pooler` de Supabase en `DATABASE_URL`.
- No requiere migraciones nuevas; es solo cambiar el host/puerto del string de conexion.

Auth JWT (recomendado JWKS):

```env
SUPABASE_URL=https://<project-ref>.supabase.co
# o explicito:
# SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
```

Google OAuth:

- No requiere variables nuevas en el backend.
- El backend solo necesita seguir confiando en los JWT emitidos por Supabase Auth.
- Si despliegas el dashboard fuera de `localhost:3000`, agrega su dominio a `CORS_ORIGINS`.

Fallback legacy (si no usas JWKS):

```env
# SUPABASE_JWT_SECRET=<legacy_jwt_secret>
# JWT_ALGORITHMS=HS256
# JWT_VERIFY_AUD=false
# JWT_AUDIENCE=authenticated
```

CORS:

```env
# CORS_ORIGINS=https://tu-frontend.com,http://localhost:3000
# CORS_ALLOW_CREDENTIALS=true
# CORS_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
# CORS_ALLOW_HEADERS=Authorization,Content-Type,Accept,Origin,X-Requested-With
```

## Arranque local (minimo)

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Recomendacion practica para desarrollo:

1. Crea `dinerance-api/.env.local` a partir de `.env.local.example`.
2. Usa ahi una base y un proyecto Supabase de desarrollo, no el de produccion.
3. En `dinerance-dashboard/.env.local` apunta `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`.

Checks utiles:

```bash
curl http://127.0.0.1:8000/healthz
curl -X POST -H "Authorization: Bearer <access_token>" http://127.0.0.1:8000/users/me/bootstrap
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8000/users/me
```

## Migrations (Alembic)

- Crear: `uv run alembic revision --autogenerate -m "mensaje"`
- Aplicar: `uv run alembic upgrade head`
- Alinear version si tablas ya existen: `uv run alembic stamp head`

- Revisiones actuales:
  - `bfc04dbb3e27_init_schema.py` -> esquema inicial.
  - `6bf0f8578784_drop_status_from_transactions.py` -> elimina columna `status`.
  - `d2f7a1b9c8de_drop_merchant_name_from_transactions.py` -> elimina columna `merchant_name`.
  - `9c2df3d91a7a_enable_rls_on_public_tables.py` -> seguridad RLS/policies.
  - `c1a2d3e4f5a6_add_policy_to_alembic_version.py` -> policy para `alembic_version`.
  - `31f4e8d7c2ab_enable_rls_on_alembic_version.py` -> activa RLS en `public.alembic_version` para evitar warning de Supabase.
  - `a9f1c3d4e5b6_add_user_money_profile_and_fx_snapshots.py` -> agrega `base_currency`, `timezone`, snapshots FX en transacciones y tabla `exchange_rates`.

## Pruebas

- Suite: `tests/`.
- DB de test: SQLite en memoria (`StaticPool`), aislada del Postgres real.
- Comando: `uv run pytest`.

Observacion: como tests usan SQLite sin JWT real de Supabase, validan logica de API/servicios; no validan politicas RLS de Postgres.

## Checklist personal de estado del repo

- `DATABASE_URL` correcto y con SSL.
- JWT config en modo JWKS (preferido) o secret legacy definido.
- `alembic upgrade head` aplicado en entorno objetivo.
- Leaked password protection habilitado en Supabase Auth.
- RLS habilitada y politicas presentes en tablas de dominio.
- Frontend enviando `Authorization: Bearer <access_token>` en cada request protegida.
