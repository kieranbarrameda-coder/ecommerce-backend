# E-Commerce App — Backend Plan (Python + Android Client)

A backend blueprint for your Android e-commerce portfolio project. Built to run entirely on free tiers: **Render** (API hosting) + **Neon** (Postgres database).

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | You already chose this |
| Framework | **FastAPI** | Async, auto-generates OpenAPI/Swagger docs (huge win when building the Android client separately), built-in request validation via Pydantic |
| Database | **PostgreSQL (Neon free tier)** | Free 0.5GB storage, serverless, sleeps when idle (fine for a portfolio project) |
| ORM | **SQLAlchemy 2.0 (async) + Alembic** | Alembic gives you migrations, which looks professional in your repo history |
| Auth | **JWT (access + refresh tokens)** via `python-jose` or `PyJWT` | Standard for mobile apps — no cookies/sessions needed |
| Password hashing | **bcrypt via `passlib`** | Never store plain text passwords |
| Image storage | **Cloudinary free tier** (25GB) or **Supabase Storage free tier** | Render's free tier has an ephemeral filesystem — uploaded images get wiped on redeploy, so don't store images locally |
| Payments | **Stripe (test mode)** | Free for testing, has a clean SDK, and "integrated Stripe" is a strong resume line even in test mode |
| Deployment | **Render (Web Service, free tier)** | Auto-deploys from GitHub |
| Rate limiting | `slowapi` (FastAPI wrapper for `limits`) | Protects free-tier resources from abuse |
| Docs | Auto-generated at `/docs` (Swagger UI) | You'll use this directly while building the Android networking layer |

> Note: free-tier limits (storage caps, sleep behavior, request quotas) change over time — worth double-checking current numbers on Render's and Neon's pricing pages before you commit.

---

## 2. Project Structure

```
ecommerce-backend/
├── app/
│   ├── main.py                # FastAPI app entrypoint
│   ├── config.py              # Settings from env vars (pydantic-settings)
│   ├── database.py            # Async SQLAlchemy engine/session
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── product.py
│   │   ├── order.py
│   │   └── cart.py
│   ├── schemas/                # Pydantic request/response schemas
│   │   ├── user.py
│   │   ├── product.py
│   │   └── order.py
│   ├── routers/                 # API route handlers
│   │   ├── auth.py
│   │   ├── products.py
│   │   ├── cart.py
│   │   ├── orders.py
│   │   └── users.py
│   ├── core/
│   │   ├── security.py         # JWT creation/verification, password hashing
│   │   ├── deps.py             # Dependency-injected "get_current_user"
│   │   └── rate_limit.py
│   └── services/
│       └── payment.py          # Stripe integration
├── alembic/                    # DB migrations
├── requirements.txt
├── .env.example
└── render.yaml                 # Render deployment config
```

---

## 3. Database Structure (PostgreSQL / Neon)

### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| email | VARCHAR, UNIQUE, NOT NULL | |
| password_hash | VARCHAR, NOT NULL | bcrypt hash, never plain text |
| full_name | VARCHAR | |
| phone | VARCHAR, NULLABLE | |
| role | ENUM('customer', 'admin') | default `customer` |
| is_active | BOOLEAN | default `true` |
| created_at | TIMESTAMP | default now() |

### `addresses`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id) | |
| label | VARCHAR | "Home", "Work" |
| line1, line2 | VARCHAR | |
| city, province, postal_code, country | VARCHAR | |
| is_default | BOOLEAN | |

### `categories`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | VARCHAR, UNIQUE | |
| slug | VARCHAR, UNIQUE | for URL-friendly filtering |

### `products`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| category_id | UUID (FK → categories.id) | |
| name | VARCHAR, NOT NULL | |
| description | TEXT | |
| price | NUMERIC(10,2), NOT NULL | store as decimal, not float |
| stock_quantity | INTEGER, default 0 | |
| sku | VARCHAR, UNIQUE | |
| image_urls | JSONB or TEXT[] | array of Cloudinary URLs |
| is_active | BOOLEAN | soft "delete"/hide instead of hard delete |
| created_at | TIMESTAMP | |

### `carts`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id), UNIQUE | one active cart per user |
| updated_at | TIMESTAMP | |

### `cart_items`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| cart_id | UUID (FK → carts.id) | |
| product_id | UUID (FK → products.id) | |
| quantity | INTEGER, NOT NULL | |
| UNIQUE(cart_id, product_id) | | prevent duplicate rows for same product |

### `orders`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id) | |
| status | ENUM('pending','paid','shipped','delivered','cancelled','refunded','failed') | `failed` = payment attempt didn't go through; `refunded` = paid then refunded |
| total_amount | NUMERIC(10,2) | |
| shipping_address_id | UUID (FK → addresses.id) | |
| payment_intent_id | VARCHAR | Stripe reference |
| estimated_delivery_date | DATE, NULLABLE | set when status moves to `paid`/`shipped` — even a naive "+5 business days" is fine for v1 |
| created_at | TIMESTAMP | |

### `order_items`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| order_id | UUID (FK → orders.id) | |
| product_id | UUID (FK → products.id) | |
| quantity | INTEGER | |
| unit_price | NUMERIC(10,2) | **snapshot the price at purchase time** — don't rely on live product price, since it can change later |

### `refresh_tokens` (for JWT refresh flow)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id) | |
| token_hash | VARCHAR | store hashed, not raw token |
| expires_at | TIMESTAMP | |
| revoked | BOOLEAN | default `false` |

**Relationships:** `users 1—N addresses`, `users 1—1 carts`, `carts 1—N cart_items`, `products N—1 categories`, `users 1—N orders`, `orders 1—N order_items`.

### Scoped out of v1 (deliberately)

Two features that come up constantly in e-commerce apps but add real surface area — call these out explicitly so nobody assumes they're covered:

- **Reviews/ratings** — no `product_reviews` table in v1. If you want to add it in a later phase, it's a clean addition (`product_reviews: id, product_id, user_id, rating, comment, created_at`) that doesn't touch any existing table.
- **Wishlist/favorites** — no `wishlist_items` table in v1, same reasoning. Also a clean bolt-on later (`wishlist_items: user_id, product_id, created_at`).

Both are intentionally deferred rather than accidentally missing — worth saying this explicitly if a reviewer or client asks why they're not there.

---

## 4. Security Plan

This is the part most portfolio projects skip — doing it properly is what makes yours stand out.

### Authentication
- **JWT access tokens** (short-lived, ~15 min) + **refresh tokens** (long-lived, ~7-30 days, stored hashed in DB so they can be revoked).
- Never store the refresh token in `SharedPreferences` on Android in plain text — use **EncryptedSharedPreferences** or the **Android Keystore**.
- On logout, revoke the refresh token server-side (flip `revoked = true`), don't just delete it client-side.

### Password handling
- Hash with **bcrypt** (via `passlib`), cost factor 12+. Never log or return password fields, even hashed ones.
- Enforce minimum password rules server-side too, not just in the Android UI (client-side validation is bypassable).

### Authorization
- Role-based checks (`customer` vs `admin`) via a FastAPI dependency, not scattered `if` checks in each route.
- Every "modify" endpoint (cancel order, edit cart) must verify the resource belongs to the requesting user — don't trust an ID in the request body alone.

### Transport & headers
- **HTTPS only** — Render free tier gives you this automatically, don't disable it.
- Set `CORS` explicitly to your known origins (your Android app doesn't need CORS since it's not browser-based, but keep the Swagger docs/testing tools restricted if you expose an admin web panel later).

### Input validation
- Pydantic schemas validate every request body automatically — reject anything malformed before it touches the DB.
- Use SQLAlchemy's parameterized queries (which you get by default with the ORM) — never string-format raw SQL.

### Rate limiting
- Add `slowapi` on `/auth/login` and `/auth/register` specifically (e.g., 5 requests/minute per IP) to blunt brute-force and signup spam — this matters a lot on a free-tier DB with limited connections.

### Secrets management
- All secrets (`DATABASE_URL`, `JWT_SECRET`, `STRIPE_SECRET_KEY`, `CLOUDINARY_API_KEY`) go in Render's **environment variables** dashboard — never commit a `.env` file. Commit `.env.example` instead with blank values.
- Rotate `JWT_SECRET` capability should exist even if you don't use it during the demo — shows you thought about it.

### Payment safety
- Never handle raw card numbers — use Stripe's client-side SDK (Stripe Payment Sheet on Android) to tokenize, and only pass the resulting token/payment method ID to your backend.
- Verify Stripe webhook signatures (`stripe.Webhook.construct_event`) so nobody can fake a "payment succeeded" call to your API.

### Misc hardening
- Return generic error messages for auth failures ("Invalid email or password") — don't reveal whether the email exists.
- Add request size limits and pagination on list endpoints (`/products?page=1&limit=20`) so nobody can DoS your free-tier DB with an unbounded query.

### Concurrency & stock safety
- **Stock decrement and order creation must happen in the same DB transaction.** Don't read `stock_quantity`, check it in Python, then write separately — that's a race condition where two users checking out at the same moment can both "succeed" against the last unit of stock.
- Guard the update itself, not just the check:
  ```sql
  UPDATE products
  SET stock_quantity = stock_quantity - :qty
  WHERE id = :product_id AND stock_quantity >= :qty
  RETURNING stock_quantity;
  ```
  If this returns no row, the transaction rolls back and the checkout fails with a clear "out of stock" error — the database enforces the invariant, not application code.
- **Restore stock on cancel/refund.** `POST /orders/{id}/cancel` and the refund path must increment `stock_quantity` back for each `order_item`, inside a transaction, symmetric to the decrement above.

---

## 5. API Endpoints

Base URL (once deployed): `https://your-app-name.onrender.com/api/v1`

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get access + refresh token |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| POST | `/auth/logout` | Revoke refresh token |
| POST | `/auth/forgot-password` | Send password reset email (via Brevo or similar transactional email API) |
| POST | `/auth/reset-password` | Consume a reset token, set new password |

### Products
| Method | Endpoint | Description |
|---|---|---|
| GET | `/products` | List — supports `page`, `limit`, `category`, `search` (name/description `ILIKE`), `min_price`, `max_price` |
| GET | `/products/{id}` | Single product detail |
| GET | `/categories` | List categories |
| POST | `/products` | Admin only — create |
| PATCH | `/products/{id}` | Admin only — update |
| POST | `/products/{id}/images` | Admin only — upload image(s) to Cloudinary, append URLs to `image_urls` |

### Cart
| Method | Endpoint | Description |
|---|---|---|
| GET | `/cart` | Get current user's cart |
| POST | `/cart/items` | Add item |
| PATCH | `/cart/items/{id}` | Update quantity |
| DELETE | `/cart/items/{id}` | Remove item |

### Orders
| Method | Endpoint | Description |
|---|---|---|
| POST | `/orders` | Checkout — creates order from cart (stock-safe, see section 4) |
| GET | `/orders` | List current user's orders — paginated (`page`, `limit`) |
| GET | `/orders/{id}` | Order detail, including status timeline |
| POST | `/orders/{id}/cancel` | Cancel (if still pending) — restores stock |
| POST | `/webhooks/stripe` | Stripe webhook receiver — verifies signature, transitions `pending` → `paid` or `failed` |

### Users & addresses
| Method | Endpoint | Description |
|---|---|---|
| GET | `/users/me` | Current profile |
| PATCH | `/users/me` | Update profile |
| GET | `/users/me/addresses` | List saved addresses |
| POST | `/users/me/addresses` | Add a new address |
| PATCH | `/users/me/addresses/{id}` | Edit an address |
| DELETE | `/users/me/addresses/{id}` | Remove an address |
| PATCH | `/users/me/addresses/{id}/default` | Set as default shipping address |

### System
| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Lightweight liveness check — no DB call. Ping this before a live demo to wake Render's free tier from a cold start |

---

## 6. Sample API Responses

### `POST /auth/login`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "3f9a1c2e-4b7d-4a1e-9c3f-1a2b3c4d5e6f",
    "email": "juan@example.com",
    "full_name": "Juan Dela Cruz",
    "role": "customer"
  }
}
```

### `GET /products?page=1&limit=20&category=electronics`
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Wireless Earbuds Pro",
      "description": "Noise-cancelling wireless earbuds with 30hr battery life.",
      "price": 1499.00,
      "stock_quantity": 42,
      "category": { "id": "c1...", "name": "Electronics", "slug": "electronics" },
      "image_urls": [
        "https://res.cloudinary.com/demo/earbuds_1.jpg",
        "https://res.cloudinary.com/demo/earbuds_2.jpg"
      ],
      "is_active": true
    }
  ],
  "page": 1,
  "limit": 20,
  "total_items": 87,
  "total_pages": 5
}
```

### `POST /cart/items`
Request:
```json
{
  "product_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "quantity": 2
}
```
Response:
```json
{
  "id": "cart-item-uuid",
  "product": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Wireless Earbuds Pro",
    "price": 1499.00,
    "image_urls": ["https://res.cloudinary.com/demo/earbuds_1.jpg"]
  },
  "quantity": 2,
  "line_total": 2998.00
}
```

### `POST /orders` (checkout)
Response:
```json
{
  "id": "order-uuid",
  "status": "pending",
  "total_amount": 2998.00,
  "shipping_address": {
    "line1": "123 Rizal St.",
    "city": "Binangonan",
    "province": "Rizal",
    "postal_code": "1940",
    "country": "PH"
  },
  "items": [
    {
      "product_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Wireless Earbuds Pro",
      "quantity": 2,
      "unit_price": 1499.00
    }
  ],
  "payment_client_secret": "pi_3P9x_secret_abcXYZ",
  "created_at": "2026-08-12T09:15:00Z"
}
```
> `payment_client_secret` is what you pass into the Stripe Android SDK's Payment Sheet.

### Error format (consistent across all endpoints)
```json
{
  "detail": "Invalid email or password"
}
```
For validation errors (FastAPI default, keep as-is — it's already well structured):
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## 7. Deployment Plan (Free Tier)

### Neon (Database)
1. Create a free project at neon.tech → note the connection string (`postgresql://user:pass@host/dbname`).
2. Use the **pooled connection string** (Neon gives you both direct and pooled) — pooled is safer for a serverless-style host like Render's free tier where connections can spin up/down.
3. Run Alembic migrations against it once locally before first deploy.

### Render (API)
1. Push your FastAPI repo to GitHub.
2. New → Web Service → connect repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables: `DATABASE_URL`, `JWT_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `CLOUDINARY_URL`.
6. Register the webhook endpoint (`https://your-app-name.onrender.com/api/v1/webhooks/stripe`) in the Stripe dashboard and copy its signing secret into `STRIPE_WEBHOOK_SECRET` — this is what `stripe.Webhook.construct_event` verifies against.
7. Free tier note: the service **spins down after inactivity** and cold-starts on the next request (can take 30-60s). For a demo, either mention this upfront or hit `GET /health` right before you demo it.

### Cloudinary (Images)
1. Free account → get `cloud_name`, `api_key`, `api_secret`.
2. Upload from the backend (not directly from Android) so you control validation (file size/type) before storage.

---

## 8. Suggested Build Order

1. Auth (register/login/refresh) + `users` table — get JWT working end-to-end first, since everything else depends on it.
2. Products + categories (read-only) — lets you start building Android list/detail screens in parallel.
3. Cart — straightforward CRUD tied to the authenticated user.
4. Orders + Stripe checkout — the most involved piece, save for after the rest is stable.
5. Admin endpoints (product management) — nice-to-have, can be Swagger-only, doesn't need an Android screen.

---

## 9. Testing & Operations (kept minimal, on purpose)

- **Tests:** full coverage isn't necessary for a portfolio project, but cover the two flows that actually prove the backend works — auth (register → login → refresh) and checkout (add to cart → order → stock decrement) — with `pytest` + `httpx.AsyncClient` against a throwaway test database. Everything else can stay manual/Swagger-tested.
- **CI:** a single GitHub Actions workflow running `pytest` on pull requests is enough to show you understand the practice — it doesn't need to be elaborate.
- **Logging:** Render's built-in log viewer is sufficient for a project this size — no need for an external logging service.
- **Connection pooling:** use Neon's **pooled** connection string in every environment, not just production — the free tier's connection cap is easy to hit during local development if you're not careful.

---

## 10. What This Demonstrates on Your Resume

- RESTful API design with proper resource modeling
- JWT auth with refresh token rotation (a detail many junior devs skip)
- Relational database design with normalization
- Third-party payment integration (Stripe)
- Deployment on real (if free-tier) cloud infrastructure
- Security-conscious backend practices — worth calling out explicitly in your README

---

*Once this backend is live, share the Swagger docs URL (`/docs`) here and I can help you plan the Android networking layer (Retrofit setup, DTOs matching these schemas, token refresh interceptor, etc.).*
