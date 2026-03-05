# finance-ai-api

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
- `routes/`
  - endpoints HTTP que acoplan auth + schemas + services.
- `main.py`
  - inicializacion de la app, routers, CORS, health endpoint.

## Flujo de autenticacion y multitenancy

1. El cliente obtiene `access_token` en Supabase Auth.
2. El backend recibe `Authorization: Bearer <token>`.
3. `app/core/auth.py` valida JWT (JWKS o secret legacy).
4. Del claim `sub` sale el `user_id` canonico del sistema.
5. `GET /users/me` crea/actualiza la fila local en `public.users` y sincroniza email/nombre.
6. `categories` y `transactions` siempre operan filtrando por `user_id`.

Idea clave: la aislacion por usuario ya existia a nivel API (filtros en services), y ahora tambien se refuerza a nivel DB con RLS.

## Modelo de datos (alto nivel)

- `users`
  - `id` UUID (coincide con `auth.users.id` via claim `sub`).
  - `email` unico.
  - `name`, timestamps y `deleted_at`.
- `categories`
  - pertenece a `user_id`.
  - soporte de jerarquia por `parent_id`.
  - `direction`: `income` o `expense`.
- `transactions`
  - pertenece a `user_id`.
  - referencia `category_id`.
  - `amount`, `currency`, `occurred_at`, `status`.

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

Base de datos:

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
# Opcional si DATABASE_URL no incluye sslmode
DB_SSLMODE=require
```

Auth JWT (recomendado JWKS):

```env
SUPABASE_URL=https://<project-ref>.supabase.co
# o explicito:
# SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
```

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

Checks utiles:

```bash
curl http://127.0.0.1:8000/healthz
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8000/users/me
```

## Migrations (Alembic)

- Crear: `uv run alembic revision --autogenerate -m "mensaje"`
- Aplicar: `uv run alembic upgrade head`
- Alinear version si tablas ya existen: `uv run alembic stamp head`

Revisiones actuales:

- `bfc04dbb3e27_init_schema.py` -> esquema inicial.
- `9c2df3d91a7a_enable_rls_on_public_tables.py` -> seguridad RLS/policies.
- `31f4e8d7c2ab_enable_rls_on_alembic_version.py` -> activa RLS en `public.alembic_version` para evitar warning de Supabase.

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
