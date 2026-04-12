"""Authentication via Databricks App proxy headers.

In Databricks Apps, the platform injects X-Forwarded-Email and
X-Forwarded-Preferred-Username headers. In local dev, falls back
to dev@localhost.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request


@dataclass
class User:
    email: str
    username: str


def get_current_user(request: Request) -> User:
    """Extract user from proxy headers or use dev fallback."""
    email = request.headers.get("X-Forwarded-Email", "dev@localhost")
    username = request.headers.get(
        "X-Forwarded-Preferred-Username",
        email.split("@")[0],
    )
    return User(email=email, username=username)
