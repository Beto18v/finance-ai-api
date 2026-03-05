import os
import uuid
import json
import time
from urllib.request import urlopen

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from jose import JWTError, jwt
    from jose import jwk
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "python-jose is required for JWT verification. Install with: uv add python-jose[cryptography]"
    ) from exc

security = HTTPBearer(auto_error=False)

_JWKS_CACHE: dict[str, object] = {"jwks": None, "ts": 0.0}
_JWKS_TTL_SECONDS = 300


def _get_jwt_secret() -> str:
    secret = os.getenv("SUPABASE_JWT_SECRET") or os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "Missing SUPABASE_JWT_SECRET (or JWT_SECRET). "
            "For Supabase Auth, copy the JWT secret from Project Settings -> API."
        )
    return secret


def _get_supabase_jwks_url() -> str:
    explicit = os.getenv("SUPABASE_JWKS_URL")
    if explicit:
        return explicit

    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        raise RuntimeError(
            "Missing SUPABASE_URL (or SUPABASE_JWKS_URL). "
            "SUPABASE_URL looks like: https://<project-ref>.supabase.co"
        )

    return supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"


def _fetch_jwks() -> dict:
    now = time.time()
    cached = _JWKS_CACHE.get("jwks")
    ts = float(_JWKS_CACHE.get("ts") or 0.0)
    if cached and (now - ts) < _JWKS_TTL_SECONDS:
        return cached  # type: ignore[return-value]

    url = _get_supabase_jwks_url()
    try:
        with urlopen(url, timeout=10) as resp:
            data = resp.read().decode("utf-8")
        jwks = json.loads(data)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to fetch JWKS from {url}") from exc

    _JWKS_CACHE["jwks"] = jwks
    _JWKS_CACHE["ts"] = now
    return jwks


def _get_public_key_from_jwks(token: str):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing kid")

    jwks = _fetch_jwks()
    keys = jwks.get("keys") or []
    for key in keys:
        if key.get("kid") == kid:
            return jwk.construct(key)

    raise HTTPException(status_code=401, detail="Unknown token kid")


def _decode_jwt(token: str) -> dict:
    # Mode 1: Legacy secret (HS256)
    if os.getenv("SUPABASE_JWT_SECRET") or os.getenv("JWT_SECRET"):
        secret = _get_jwt_secret()

        algorithms_env = os.getenv("JWT_ALGORITHMS", "HS256")
        algorithms = [a.strip() for a in algorithms_env.split(",") if a.strip()]

        options = {"verify_aud": bool(os.getenv("JWT_VERIFY_AUD"))}
        audience = os.getenv("JWT_AUDIENCE")

        try:
            return jwt.decode(
                token,
                secret,
                algorithms=algorithms,
                audience=audience,
                options=options,
            )
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    # Mode 2: Supabase JWT Signing Keys (JWKS)
    header = jwt.get_unverified_header(token)
    alg = header.get("alg") or "RS256"
    if alg not in {"RS256", "ES256"}:
        raise HTTPException(status_code=401, detail="Unsupported token alg")

    try:
        key = _get_public_key_from_jwks(token)
        pem = key.to_pem().decode("utf-8")
    except HTTPException:
        raise
    except RuntimeError as exc:  # config/fetch errors
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    options = {"verify_aud": bool(os.getenv("JWT_VERIFY_AUD"))}
    audience = os.getenv("JWT_AUDIENCE")

    try:
        return jwt.decode(
            token,
            pem,
            algorithms=[alg],
            audience=audience,
            options=options,
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    return _decode_jwt(credentials.credentials)


def get_current_user_id(claims: dict = Depends(get_current_user_claims)) -> uuid.UUID:
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub")

    try:
        return uuid.UUID(str(sub))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid sub in token")


def get_current_user_email(claims: dict = Depends(get_current_user_claims)) -> str | None:
    return claims.get("email")
