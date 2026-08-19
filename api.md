# E-Commerce Backend API

REST API for the E-Commerce Backend. All endpoints are served under the `/api/v1` prefix.

- **Base URL:** `http://localhost:8000/api/v1`
- **Content type:** `application/json` (except the image upload and webhook endpoints)
- **Interactive docs (OpenAPI):** `http://localhost:8000/docs`

## Authentication

Most endpoints require a bearer token issued by `POST /auth/login` (after email verification) or `POST /auth/verify-email`.

```
Authorization: Bearer <access_token>
```

Access tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15 minutes). Use `POST /auth/refresh` to get a fresh access token from the refresh token. Refresh tokens expire after `REFRESH_TOKEN_EXPIRE_DAYS` (default 7 days) and are revoked on logout or password reset.

Roles:
- `customer` — default role on registration. Can use cart, orders, addresses.
- `admin` — required for product create/update/image-upload. Non-admin calls to admin routes return `403`.

## Common Error Responses

| Status | Meaning |
| --- | --- |
| `400` | Bad request / invalid or expired token / cart empty |
| `401` | Missing/invalid bearer token, or bad login/refresh credentials |
| `403` | Authenticated but not an admin |
| `404` | Resource not found |
| `409` | Conflict (duplicate email, duplicate SKU, insufficient stock) |
| `422` | Validation error (missing/invalid fields) |
| `429` | Rate limit exceeded |

Most errors use the shape:

```json
{
  "detail": "Human-readable message"
}
```

`422` uses FastAPI's standard validation shape:

```json
{
  "detail": [
    {
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "type": "string_too_short"
    }
  ]
}
```

## Health

### GET /health, HEAD /health

Accept both `GET` and `HEAD`. `GET` returns the body; `HEAD` returns headers only (no body).

- Auth: None

Response `200`:

```json
{
  "status": "ok"
}
```

## Auth

### POST /auth/register

Create an account and receive tokens immediately.

- Auth: None
- Rate limit: `5/minute`

Request body:

```json
{
  "email": "juan@example.com",
  "password": "strongpass123",
  "full_name": "Juan Dela Cruz"
}
```

`full_name` is optional. `password` must be at least 8 characters.

Response `201`:

```json
{
  "detail": "Registration successful. Please check your email for a verification code."
}
```

A 6-digit OTP is sent to the email address. The user must verify via `POST /auth/verify-email` before they can log in.

Errors: `409` `{"detail": "An account with this email already exists"}`.

### POST /auth/verify-email

Verify an email address using the OTP sent during registration. On success, returns tokens so the user can start using the API immediately.

- Auth: None
- Rate limit: `5/minute`

Request body:

```json
{
  "email": "juan@example.com",
  "otp": "123456"
}
```

Response `200`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "v8x3LmQa...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "email": "juan@example.com",
    "full_name": "Juan Dela Cruz",
    "role": "customer"
  }
}
```

Errors: `400` `{"detail": "Invalid or expired verification code"}`.

### POST /auth/resend-verification

Resend a new OTP to the given email address. Always returns the same response whether or not the email exists or is already verified, to avoid leaking account presence.

- Auth: None
- Rate limit: `3/minute`

Request body:

```json
{
  "email": "juan@example.com"
}
```

Response `200`:

```json
{
  "detail": "If that email exists and is unverified, a new code has been sent."
}
```

### POST /auth/login

Authenticate with email and password.

- Auth: None
- Rate limit: `5/minute`

Request body:

```json
{
  "email": "juan@example.com",
  "password": "strongpass123"
}
```

Response `200`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "v8x3LmQa...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "email": "juan@example.com",
    "full_name": "Juan Dela Cruz",
    "role": "customer"
  }
}
```

Errors: `401` `{"detail": "Invalid email or password"}`, `403` `{"detail": "Please verify your email before logging in"}`.

### POST /auth/refresh

Get a new access token using a valid refresh token. The same refresh token is returned.

- Auth: None

Request body:

```json
{
  "refresh_token": "v8x3LmQa..."
}
```

Response `200`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "v8x3LmQa...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "email": "juan@example.com",
    "full_name": "Juan Dela Cruz",
    "role": "customer"
  }
}
```

Errors: `401` `{"detail": "Invalid refresh token"}` (unknown, revoked, or expired refresh token, or inactive user).

### POST /auth/logout

Revoke the given refresh token.

- Auth: None

Request body:

```json
{
  "refresh_token": "v8x3LmQa..."
}
```

Response `200`:

```json
{
  "detail": "Logged out"
}
```

### POST /auth/forgot-password

Send a password reset email to the given address (if an account exists). Always returns the same response whether or not the email exists, to avoid leaking account presence.

- Auth: None
- Rate limit: `3/minute`

Request body:

```json
{
  "email": "juan@example.com"
}
```

Response `200`:

```json
{
  "detail": "If that email exists, a reset link has been sent"
}
```

The email contains a one-time reset link built from `FRONTEND_RESET_URL` plus a `?token=...` query parameter. The token expires in 30 minutes.

### POST /auth/reset-password

Set a new password using the token from the reset email. Revokes all of the user's refresh tokens.

- Auth: None

Request body:

```json
{
  "token": "8fJ...reset-token-from-email...",
  "new_password": "newstrongpass456"
}
```

`new_password` must be at least 8 characters.

Response `200`:

```json
{
  "detail": "Password reset successfully"
}
```

Errors: `400` `{"detail": "Invalid or expired token"}`.

## Categories

### GET /categories

List all categories ordered by name.

- Auth: None

Response `200`:

```json
[
  {
    "id": "1f8e9d2a-b3c4-4d5e-8f6a-7b8c9d0e1f2a",
    "name": "Electronics",
    "slug": "electronics"
  },
  {
    "id": "2f9e0d3b-c4d5-4e6f-9a7b-8c9d0e1f2a3b",
    "name": "Fashion",
    "slug": "fashion"
  }
]
```

## Products

### GET /products

List active products, newest first. Supports pagination, category, search, and price filtering.

- Auth: None
- Query parameters:

| Param | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int | `1` | Page number, `>= 1` |
| `limit` | int | `20` | Items per page, `1..100` |
| `category` | str | — | Category slug |
| `search` | str | — | Case-insensitive match on name or description |
| `min_price` | decimal | — | Minimum price |
| `max_price` | decimal | — | Maximum price |

Response `200`:

```json
{
  "items": [
    {
      "id": "3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c",
      "category_id": "1f8e9d2a-b3c4-4d5e-8f6a-7b8c9d0e1f2a",
      "name": "Wireless Headphones",
      "description": "Over-ear Bluetooth headphones with noise cancellation.",
      "price": "2499.99",
      "stock_quantity": 50,
      "sku": "AUD-001",
      "image_urls": [
        "https://res.cloudinary.com/ixzydpqv/image/upload/v1700000000/products/3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c/headphones.jpg"
      ],
      "is_active": true,
      "created_at": "2026-08-10T14:30:00"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

### GET /products/{product_id}

Get a single active product.

- Auth: None

Response `200`:

```json
{
  "id": "3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c",
  "category_id": "1f8e9d2a-b3c4-4d5e-8f6a-7b8c9d0e1f2a",
  "name": "Wireless Headphones",
  "description": "Over-ear Bluetooth headphones with noise cancellation.",
  "price": "2499.99",
  "stock_quantity": 50,
  "sku": "AUD-001",
  "image_urls": [
    "https://res.cloudinary.com/ixzydpqv/image/upload/v1700000000/products/3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c/headphones.jpg"
  ],
  "is_active": true,
  "created_at": "2026-08-10T14:30:00"
}
```

Errors: `404` `{"detail": "Product not found"}`.

### POST /products

Create a product.

- Auth: **Admin required**
- Content type: `application/json`

Request body:

```json
{
  "category_id": "1f8e9d2a-b3c4-4d5e-8f6a-7b8c9d0e1f2a",
  "name": "Mechanical Keyboard",
  "description": "TKL mechanical keyboard with hot-swappable switches.",
  "price": "3999.00",
  "stock_quantity": 25,
  "sku": "KB-001",
  "image_urls": [],
  "is_active": true
}
```

`category_id`, `description`, `sku`, `image_urls`, `is_active` are optional (`category_id` defaults to `null`, `stock_quantity` to `0`, `image_urls` to `[]`, `is_active` to `true`).

Response `201`:

```json
{
  "id": "4b1a2f5d-e6f7-4a8b-9c9d-0e1f2a3b4c5d",
  "category_id": "1f8e9d2a-b3c4-4d5e-8f6a-7b8c9d0e1f2a",
  "name": "Mechanical Keyboard",
  "description": "TKL mechanical keyboard with hot-swappable switches.",
  "price": "3999.00",
  "stock_quantity": 25,
  "sku": "KB-001",
  "image_urls": [],
  "is_active": true,
  "created_at": "2026-08-17T09:15:00"
}
```

Errors: `404` `{"detail": "Category not found"}` (when `category_id` is provided and unknown), `409` `{"detail": "Product with this SKU already exists"}`, `403` `{"detail": "Admin access required"}`.

### PATCH /products/{product_id}

Update one or more product fields. Only provided fields are changed.

- Auth: **Admin required**

Request body (all fields optional):

```json
{
  "price": "3799.00",
  "stock_quantity": 30,
  "is_active": true
}
```

Response `200` — same shape as `POST /products`, with the updated fields applied.

Errors: `404` `{"detail": "Product not found"}` or `{"detail": "Category not found"}`, `409` `{"detail": "Product with this SKU already exists"}`, `403`.

### POST /products/{product_id}/images

Upload one or more images to Cloudinary and append their URLs to the product's `image_urls`.

- Auth: **Admin required**
- Content type: `multipart/form-data`
- Field name: `files` (can repeat for multiple files; all must have an `image/*` content type)

Response `200`:

```json
{
  "image_urls": [
    "https://res.cloudinary.com/ixzydpqv/image/upload/v1700000000/products/4b1a2f5d-e6f7-4a8b-9c9d-0e1f2a3b4c5d/keyboard-top.jpg",
    "https://res.cloudinary.com/ixzydpqv/image/upload/v1700000000/products/4b1a2f5d-e6f7-4a8b-9c9d-0e1f2a3b4c5d/keyboard-side.jpg"
  ]
}
```

Errors: `400` `{"detail": "Only image files are allowed"}`, `404` `{"detail": "Product not found"}`, `502` `{"detail": "Image upload failed"}`, `403`.

## Cart

All cart endpoints require authentication.

### GET /cart

Get the current user's cart. Creates an empty cart if none exists.

- Auth: Bearer

Response `200`:

```json
{
  "id": "5c2b3a6e-f7a8-4b9c-ad0e-1f2a3b4c5d6e",
  "items": [
    {
      "id": "6d3c4b7f-a8b9-4cad-be1f-2a3b4c5d6e7f",
      "product_id": "3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c",
      "quantity": 2,
      "product": {
        "id": "3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c",
        "category_id": "1f8e9d2a-b3c4-4d5e-8f6a-7b8c9d0e1f2a",
        "name": "Wireless Headphones",
        "description": "Over-ear Bluetooth headphones with noise cancellation.",
        "price": "2499.99",
        "stock_quantity": 50,
        "sku": "AUD-001",
        "image_urls": [
          "https://res.cloudinary.com/ixzydpqv/image/upload/v1700000000/products/3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c/headphones.jpg"
        ],
        "is_active": true,
        "created_at": "2026-08-10T14:30:00"
      }
    }
  ],
  "total_items": 2,
  "subtotal": "4999.98"
}
```

### POST /cart/items

Add an item to the cart. If the product is already in the cart, the quantities are summed.

- Auth: Bearer

Request body:

```json
{
  "product_id": "3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c",
  "quantity": 2
}
```

`quantity` must be `>= 1`.

Response `200` — a `CartOut` object (same shape as `GET /cart`).

Errors: `404` `{"detail": "Product not found"}`.

### PATCH /cart/items/{item_id}

Set the quantity of an existing cart item.

- Auth: Bearer

Request body:

```json
{
  "quantity": 5
}
```

`quantity` must be `>= 1`.

Response `200` — a `CartOut` object.

Errors: `404` `{"detail": "Cart item not found"}`.

### DELETE /cart/items/{item_id}

Remove an item from the cart.

- Auth: Bearer

Response `200` — a `CartOut` object reflecting the cart after removal.

Errors: `404` `{"detail": "Cart item not found"}`.

## Orders

All order endpoints require authentication.

Order statuses: `pending`, `paid`, `shipped`, `delivered`, `cancelled`, `refunded`, `failed`.

### POST /orders

Create an order from the current user's cart (emptying the cart) and decrement product stock atomically.

- Auth: Bearer

Request body:

```json
{
  "shipping_address_id": "7e4d5c8a-b9ca-4dbe-cf2a-3b4c5d6e7f80"
}
```

Response `201`:

```json
{
  "id": "8f5e6d9b-cadb-4ecf-df3a-4b5c6d7e8f91",
  "status": "pending",
  "total_amount": "4999.98",
  "shipping_address_id": "7e4d5c8a-b9ca-4dbe-cf2a-3b4c5d6e7f80",
  "payment_intent_id": null,
  "estimated_delivery_date": "2026-08-24",
  "created_at": "2026-08-17T09:30:00",
  "items": [
    {
      "id": "9a6f7eac-dbdc-4fd0-ef4a-5b6c7d8e9fa2",
      "product_id": "3a0f1e4c-d5e6-4f7a-9b8c-9d0e1f2a3b4c",
      "quantity": 2,
      "unit_price": "2499.99"
    }
  ]
}
```

`estimated_delivery_date` is 5 business days from creation.

Errors: `400` `{"detail": "Cart is empty"}`, `404` `{"detail": "Shipping address not found"}`, `409` `{"detail": "Not enough stock for '<product name>'"}`.

### GET /orders

List the current user's orders, newest first.

- Auth: Bearer
- Query parameters:

| Param | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int | `1` | Page number, `>= 1` |
| `limit` | int | `20` | Items per page, `1..100` |

Response `200`:

```json
{
  "items": [
    {
      "id": "8f5e6d9b-cadb-4ecf-df3a-4b5c6d7e8f91",
      "status": "pending",
      "total_amount": "4999.98",
      "shipping_address_id": "7e4d5c8a-b9ca-4dbe-cf2a-3b4c5d6e7f80",
      "payment_intent_id": null,
      "estimated_delivery_date": "2026-08-24",
      "created_at": "2026-08-17T09:30:00",
      "items": []
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

### GET /orders/{order_id}

Get one of the current user's orders.

- Auth: Bearer

Response `200` — an `OrderOut` object (same shape as `POST /orders`).

Errors: `404` `{"detail": "Order not found"}` (including orders owned by another user).

### POST /orders/{order_id}/cancel

Cancel a pending order and restore the product stock.

- Auth: Bearer

Response `200` — the order with `status` set to `"cancelled"`.

Errors: `400` `{"detail": "Only pending orders can be cancelled"}`, `404` `{"detail": "Order not found"}`.

### POST /orders/{order_id}/pay

Create (or reuse) a Stripe PaymentIntent for the order and return its client secret. Amount is charged in PHP (PHP).

- Auth: Bearer

Response `200`:

```json
{
  "client_secret": "pi_3Oxyz..._secret_AbCdEfGhIjKlMnOpQrStUvWx",
  "order_id": "8f5e6d9b-cadb-4ecf-df3a-4b5c6d7e8f91",
  "amount": "4999.98"
}
```

Errors: `400` `{"detail": "Only pending orders can be paid"}`, `404` `{"detail": "Order not found"}`.

The order status is advanced from `pending` via the Stripe webhook (see below), not here.

## Webhooks

### POST /webhooks/stripe

Stripe webhook endpoint. Verifies the `stripe-signature` header against `STRIPE_WEBHOOK_SECRET`, then updates order status.

- Auth: None (signed payload required)
- Content type: `application/json` (raw Stripe event body)

Handled events:

| Event | Effect |
| --- | --- |
| `payment_intent.succeeded` | Order → `paid` |
| `payment_intent.payment_failed` | Order → `failed` |

The `order_id` is read from the PaymentIntent's `metadata.order_id`.

Response `200`:

```json
{
  "status": "ok"
}
```

Errors: `400` `{"detail": "Invalid signature"}`.

## Addresses

All address endpoints require authentication. The first address created is automatically set as the default.

### GET /users/me/addresses

List the current user's addresses, default first.

- Auth: Bearer

Response `200`:

```json
[
  {
    "id": "7e4d5c8a-b9ca-4dbe-cf2a-3b4c5d6e7f80",
    "label": "Home",
    "line1": "123 Mabini St",
    "line2": "Brgy. Poblacion",
    "city": "Makati",
    "province": "Metro Manila",
    "postal_code": "1234",
    "country": "PH",
    "is_default": true
  }
]
```

### POST /users/me/addresses

Create an address. The first address is forced to default; creating another default clears the previous default.

- Auth: Bearer

Request body:

```json
{
  "label": "Home",
  "line1": "123 Mabini St",
  "line2": "Brgy. Poblacion",
  "city": "Makati",
  "province": "Metro Manila",
  "postal_code": "1234",
  "country": "PH",
  "is_default": true
}
```

`label`, `line2`, `is_default` are optional (`label`/`line2` default to `null`, `is_default` to `false`).

Response `201` — an `AddressOut` object (same shape as a list item above).

### PATCH /users/me/addresses/{address_id}

Update address fields. Setting `is_default: true` clears other defaults. Cannot unset the default on the only default address.

- Auth: Bearer

Request body (all fields optional):

```json
{
  "line1": "456 Rizal Ave",
  "city": "Quezon City",
  "is_default": true
}
```

Response `200` — an `AddressOut` object.

Errors: `400` `{"detail": "Cannot unset the only default address"}`, `404` `{"detail": "Address not found"}`.

### DELETE /users/me/addresses/{address_id}

Delete an address. If the deleted address was the default, the next address becomes default.

- Auth: Bearer

Response `204 No Content` (no body).

Errors: `404` `{"detail": "Address not found"}`.

## Rate Limits

| Endpoint | Limit |
| --- | --- |
| `POST /auth/register` | 5 per minute |
| `POST /auth/login` | 5 per minute |
| `POST /auth/verify-email` | 5 per minute |
| `POST /auth/resend-verification` | 3 per minute |
| `POST /auth/forgot-password` | 3 per minute |

Exceeding a limit returns `429`:

```json
{
  "detail": "Rate limit exceeded"
}
```
