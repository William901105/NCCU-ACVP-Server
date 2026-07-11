from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi.responses import JSONResponse

from .errors import invalid_query_error


DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def parse_paging_params(
    *,
    limit: Any = None,
    offset: Any = None,
    default_limit: int = DEFAULT_LIMIT,
    max_limit: int = MAX_LIMIT,
) -> Any:
    parsed_limit = _parse_integer_query(
        "limit",
        limit,
        default=default_limit,
        minimum=1,
        maximum=max_limit,
        message=f"limit must be an integer between 1 and {max_limit}.",
    )
    if isinstance(parsed_limit, JSONResponse):
        return parsed_limit

    parsed_offset = _parse_integer_query(
        "offset",
        offset,
        default=0,
        minimum=0,
        maximum=None,
        message="offset must be an integer greater than or equal to 0.",
    )
    if isinstance(parsed_offset, JSONResponse):
        return parsed_offset

    return {
        "limit": parsed_limit,
        "offset": parsed_offset,
    }


def apply_paging(items: List[Any], *, limit: int, offset: int) -> Tuple[List[Any], Dict[str, Any]]:
    total = len(items)
    page = items[offset:offset + limit]
    incomplete = offset + len(page) < total
    return page, {
        "offset": offset,
        "limit": limit,
        "total": total,
        "returned": len(page),
        "incomplete": incomplete,
    }


def build_paged_body(
    *,
    items: List[Any],
    key: str,
    limit: int,
    offset: int,
    total: int,
    resource_path: Optional[str] = None,
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    returned = len(items)
    incomplete = offset + returned < total
    pagination = {
        "offset": offset,
        "limit": limit,
        "total": total,
        "returned": returned,
        "incomplete": incomplete,
    }
    body = {
        "totalCount": total,
        "incomplete": incomplete,
        "links": _paging_links(
            resource_path=resource_path,
            limit=limit,
            offset=offset,
            total=total,
            query=query,
        ),
        "data": items,
        key: items,
        "pagination": pagination,
    }
    return body


def _parse_integer_query(
    parameter: str,
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: Optional[int],
    message: str,
) -> Any:
    if value is None:
        return default
    parsed = _to_int(value)
    if parsed is None:
        return invalid_query_error(
            parameter=parameter,
            value=value,
            message=message,
        )
    if parsed < minimum or (maximum is not None and parsed > maximum):
        return invalid_query_error(
            parameter=parameter,
            value=value,
            message=message,
        )
    return parsed


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped, 10)
        except ValueError:
            return None
    return None


def _paging_links(
    *,
    resource_path: Optional[str],
    limit: int,
    offset: int,
    total: int,
    query: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    if resource_path is None:
        return {
            "first": None,
            "previous": None,
            "next": None,
            "last": None,
        }

    last_offset = 0 if total == 0 else ((total - 1) // limit) * limit
    next_offset = offset + limit if offset + limit < total else None
    previous_offset = max(offset - limit, 0) if offset > 0 else None
    return {
        "first": _link(resource_path, limit=limit, offset=0, query=query),
        "previous": (
            _link(resource_path, limit=limit, offset=previous_offset, query=query)
            if previous_offset is not None
            else None
        ),
        "next": (
            _link(resource_path, limit=limit, offset=next_offset, query=query)
            if next_offset is not None
            else None
        ),
        "last": _link(resource_path, limit=limit, offset=last_offset, query=query),
    }


def _link(
    resource_path: str,
    *,
    limit: int,
    offset: int,
    query: Optional[Dict[str, Any]],
) -> str:
    params: Dict[str, Any] = {
        key: value
        for key, value in (query or {}).items()
        if value is not None
    }
    params["limit"] = limit
    params["offset"] = offset
    return f"{resource_path}?{urlencode(params)}"
