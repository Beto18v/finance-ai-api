import os


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def cors_origins() -> list[str]:
    # Safe defaults for local frontend development (Next.js)
    return env_csv(
        "CORS_ORIGINS",
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )


def cors_allow_credentials() -> bool:
    return env_bool("CORS_ALLOW_CREDENTIALS", default=True)


def cors_origin_regex() -> str | None:
    value = os.getenv("CORS_ORIGIN_REGEX")
    if value is None:
        return None
    value = value.strip()
    return value or None


def cors_allow_methods() -> list[str]:
    return env_csv(
        "CORS_ALLOW_METHODS",
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )


def cors_allow_headers() -> list[str]:
    return env_csv(
        "CORS_ALLOW_HEADERS",
        default=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    )
