# Session 1 — Auth-Only Backend Plan (FastAPI)

Scope: **auth only**. Users / addresses / refresh_tokens tables, register / login / refresh / logout,
rate limiting, health check, Alembic migration. NO products, cart, orders, or Stripe in this session.
Routes are mounted under `/api/v1`.

## 0. Environment setup (one-time)
1. Install Python 3.12: `winget install Python.Python.3.12`
2. In `ecommerce-backend/`: `py -3.12 -m venv .venv` → activate → `pip install -r requirements.txt`
3. No migration, no live DB, no package install without explicit go-ahead.

## 1. Files to create (under `ecommerce-backend/`)

### `app/config.py`
`Settings(BaseSettings)` reading `.env`:
- `DATABASE_URL` (required)
- `JWT_SECRET` (required)
- `JWT_ALGORITHM = "HS256"`
- `ACCESS_TOKEN_EXPIRE_MINUTES = 15`
- `REFRESH_TOKEN_EXPIRE_DAYS = 7`
Module-level `settings = Settings()`.

### `app/database.py`
- `Base(DeclarativeBase)`
- `create_async_engine` with `_async_url()` helper rewriting
  `postgres://` / `postgresql://` → `postgresql+asyncpg://` (Neon strings)
- `async_sessionmaker(expire_on_commit=False)`
- `get_db()` async dependency yielding a session

### `app/models/` (__init__.py imports all three)
- `user.py`, `address.py`, `refresh_token.py` — **byte-for-byte as pasted by the user**,
  only `Base` sourced from `app.database`. No edits to the user's models.

### `app/core/security.py`
- `hash_password` / `verify_password` via `passlib.CryptContext(schemes=["bcrypt"], deprecated="auto")`
- `create_access_token(user_id)` → PyJWT HS256 JWT
  (`sub`=str(uuid), `type="access"`, `iat`, `exp` = now + ACCESS_TOKEN_EXPIRE_MINUTES)
- `decode_token(token)` → payload, raises on expired/invalid
- `generate_refresh_token()` → `secrets.token_urlsafe(64)` raw + `hash_refresh_token(raw)`
  → sha256 hexdigest (only the hash is stored in the DB)

### `app/core/deps.py`
- `HTTPBearer(auto_error=False)`
- `get_current_user` — decodes Bearer token, loads user by `sub` via `get_db`,
  checks `is_active`, raises `401 "Not authenticated"` for missing/expired/invalid/no-user

### `app/schemas/user.py`
- `RegisterRequest` — `email: EmailStr`, `password: str` (min 8), `full_name: str|None`
- `LoginRequest` — `email`, `password`
- `RefreshRequest` — `refresh_token`
- `LogoutRequest` — `refresh_token`
- `UserOut` — `id: UUID, email, full_name, role`, `from_attributes=True`
- `TokenResponse` — `access_token, refresh_token, token_type="bearer", expires_in: int, user: UserOut`

### `app/core/rate_limit.py`
- `limiter = Limiter(key_func=get_remote_address)`
- 429 handler returning `{"detail": "Rate limit exceeded"}`

### `app/routers/auth.py` (APIRouter, prefix `/auth`)
- `POST /register` — 409 if email exists; hash pw; create user; issue tokens;
  insert hashed refresh row; return `TokenResponse` (auto-login). Rate-limited `5/minute`.
- `POST /login` — lookup + verify; any failure → `401 "Invalid email or password"`
  (no email-existence leak); issue tokens; return `TokenResponse`. Rate-limited `5/minute`.
- `POST /refresh` — hash incoming refresh token, look up row;
  401 if missing/`revoked`/expired; issue new access token; return `TokenResponse`.
- `POST /logout` — hash incoming token, set `revoked=True`, commit; return `{"detail": "Logged out"}`. Never deletes.

### `app/main.py`
- FastAPI app; `app.state.limiter = limiter` + 429 exception handler
- CORS `allow_origins=["*"]` (locked down later)
- Include auth router under `/api/v1`
- `GET /api/v1/health` → `{"status": "ok"}` (no DB call)

### Root files
- `requirements.txt` — `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]>=2.0`, `asyncpg`,
  `alembic`, `pydantic-settings`, `email-validator`, `PyJWT`, `passlib[bcrypt]`,
  `bcrypt==4.0.1` (pinned — passlib 1.7.4 breaks on bcrypt >=4.1), `slowapi`
- `.env.example` — the 5 vars with placeholders
- `.env` — copy of `.env.example` with throwaway `JWT_SECRET` (not committed)
- `.gitignore` — `.venv/`, `.env`, `__pycache__/`
- `render.yaml` — web service: build `pip install -r requirements.txt`,
  start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, env-vars block

## 2. Alembic (scaffold + migration, NO live DB)
1. `alembic init alembic`; set `prepend_sys_path = .` in `alembic.ini`
2. Rewrite `env.py` for async: import `settings` + `Base` + all three models;
   reuse `postgresql+asyncpg` URL conversion; `target_metadata = Base.metadata`;
   `asyncio.run()` online runner with `async_engine_from_config` + `NullPool`
3. `alembic revision -m "create users, addresses, refresh_tokens"` then **hand-write**
   upgrade()/downgrade() (autogenerate needs a live DB).
   Tables: `users` (UUID pk, unique email, `userrole` PG enum), `addresses`, `refresh_tokens`
   with FKs + indexes (email, user_id, token_hash). Downgrade drops tables then `DROP TYPE userrole`.
   Python-side `default=` values (uuid4, `is_active`, `created_at`) are NOT server defaults — mirror models.

## 3. Verification (no live DB)
- `python -c "import app.main"` and `python -m compileall app alembic`
- Boot uvicorn briefly: confirm `/docs` and `/api/v1/health` respond (engine is lazy — no DB needed at startup)
- Stop. **User** runs `alembic upgrade head` against their Neon string later.

## 4. Decisions / notes
- `expires_in` = `ACCESS_TOKEN_EXPIRE_MINUTES * 60` (900 default) — matches sample response
- Refresh tokens are NOT rotated on refresh (per spec — "issue new access token"); rotation is a later add
- Passwords enforce min 8 chars server-side
- No email verification / account lockout this session (rate limiting covers brute-force for now)
