"""OpenAPI decorators that degrade to no-ops when drf-spectacular is absent.

drf-spectacular lives in the ``dev`` dependency group (see ``pyproject.toml``) and
is only added to ``INSTALLED_APPS`` under ``DEBUG``, so production images do not
ship it. Annotate views and serializer method fields by importing from here — a
direct ``from drf_spectacular.utils import ...`` would crash on boot in prod.
"""

from typing import Any

try:
    from drf_spectacular.types import OpenApiTypes
    from drf_spectacular.utils import (
        OpenApiExample,
        OpenApiParameter,
        OpenApiResponse,
        extend_schema,
        extend_schema_field,
    )
except ImportError:  # pragma: no cover - production path, no schema generation

    def extend_schema(**kwargs: Any):
        def decorator(target):
            return target

        return decorator

    def extend_schema_field(*args: Any, **kwargs: Any):
        def decorator(target):
            return target

        return decorator

    class OpenApiExample:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class OpenApiParameter:
        QUERY = "query"
        PATH = "path"
        HEADER = "header"
        COOKIE = "cookie"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class OpenApiResponse:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class OpenApiTypes:
        BINARY = "binary"
        STR = "string"
        NONE = None


__all__ = [
    "OpenApiExample",
    "OpenApiParameter",
    "OpenApiResponse",
    "OpenApiTypes",
    "extend_schema",
    "extend_schema_field",
]
