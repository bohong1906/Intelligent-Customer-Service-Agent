import json
import os
from typing import Any

from tools import MySQLError, get_connection, serialize_row


def get_current_customer_id() -> int | None:
    return _coerce_customer_id(os.getenv("CURRENT_CUSTOMER_ID"))


def lookup_customer_id_by_order_id(order_id: int) -> int | None:
    try:
        with get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT customer_id FROM orders WHERE order_id = %s",
                (order_id,),
            )
            row = cursor.fetchone()
    except (MySQLError, RuntimeError):
        return None

    if row is None:
        return None

    customer_id = row.get("customer_id")
    return int(customer_id) if customer_id is not None else None


def fetch_customer_memory(customer_id: int, limit: int = 5) -> list[dict[str, Any]]:
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT `key`, `value`, created_at
            FROM customer_memory
            WHERE customer_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (customer_id, limit),
        )
        rows = cursor.fetchall()

    return [serialize_row(row) for row in rows if row is not None]


def get_latest_memory_value(
    memories: list[dict[str, Any]],
    key: str,
) -> str | None:
    for memory in memories:
        if memory.get("key") == key:
            value = memory.get("value")
            return str(value) if value is not None else None
    return None


def write_customer_memory(
    *,
    customer_id: int,
    key: str,
    value: str,
) -> dict[str, Any]:
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO customer_memory (customer_id, `key`, `value`)
                VALUES (%s, %s, %s)
                """,
                (customer_id, key, value),
            )
            memory_id = cursor.lastrowid
            connection.commit()
    except (MySQLError, RuntimeError) as exc:
        return {"ok": False, "error": f"LTM write failed: {exc}"}

    return {
        "ok": True,
        "memory_id": memory_id,
        "key": key,
        "value": value,
    }


def extract_customer_id_from_messages(messages: list[Any]) -> int | None:
    for message in reversed(messages):
        content = getattr(message, "content", message)
        customer_id = _extract_customer_id_from_payload(content)
        if customer_id is not None:
            return customer_id
    return None


def _extract_customer_id_from_payload(payload: Any) -> int | None:
    if payload is None:
        return None

    if isinstance(payload, dict):
        direct = payload.get("customer_id")
        if direct is not None:
            return _coerce_customer_id(direct)

        order = payload.get("order")
        if isinstance(order, dict) and order.get("customer_id") is not None:
            return _coerce_customer_id(order.get("customer_id"))

        customer = payload.get("customer")
        if isinstance(customer, dict) and customer.get("customer_id") is not None:
            return _coerce_customer_id(customer.get("customer_id"))

        return None

    if isinstance(payload, list):
        for item in payload:
            customer_id = _extract_customer_id_from_payload(item)
            if customer_id is not None:
                return customer_id
        return None

    if isinstance(payload, str):
        payload_text = payload.strip()
        if not payload_text:
            return None
        try:
            decoded = json.loads(payload_text)
        except json.JSONDecodeError:
            return None
        return _extract_customer_id_from_payload(decoded)

    return None


def _coerce_customer_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_ltm_context(
    *,
    order_id: int | None = None,
    customer_id: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    if customer_id is None and order_id is None:
        return {
            "ok": False,
            "reason": "missing_customer_id_or_order_id",
            "memories": [],
        }

    resolved_customer_id = customer_id
    if resolved_customer_id is None and order_id is not None:
        resolved_customer_id = lookup_customer_id_by_order_id(order_id)

    if resolved_customer_id is None:
        return {
            "ok": False,
            "reason": "customer_not_found",
            "order_id": order_id,
            "memories": [],
        }

    try:
        memories = fetch_customer_memory(resolved_customer_id, limit=limit)
        return {
            "ok": True,
            "customer_id": resolved_customer_id,
            "memories": memories,
        }
    except (MySQLError, RuntimeError) as exc:
        return {
            "ok": False,
            "error": f"LTM read failed: {exc}",
            "customer_id": resolved_customer_id,
            "memories": [],
        }
