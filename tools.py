import os
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator

import dotenv
from langchain_core.tools import tool

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None
    MySQLError = Exception


dotenv.load_dotenv()


def get_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "ics_agent"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "intelligent_customer_service"),
    }


@contextmanager
def get_connection() -> Iterator[Any]:
    if mysql is None:
        raise RuntimeError(
            "mysql-connector-python is not installed. "
            "Install it with: pip install mysql-connector-python"
        )

    connection = mysql.connector.connect(**get_db_config())
    try:
        yield connection
    finally:
        connection.close()


def serialize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None

    result = {}
    for key, value in row.items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def error_result(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def get_current_customer_id() -> int | None:
    value = os.getenv("CURRENT_CUSTOMER_ID")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def get_current_customer_id_or_error() -> tuple[int | None, dict[str, Any] | None]:
    customer_id = get_current_customer_id()
    if customer_id is None:
        return None, error_result("Current customer context is unavailable.")
    return customer_id, None


def lookup_order_record(order_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                o.order_id,
                o.customer_id,
                c.name AS customer_name,
                c.email AS customer_email,
                o.product_name,
                o.status,
                o.order_date,
                o.delivery_date
            FROM orders o
            JOIN customers c ON c.customer_id = o.customer_id
            WHERE o.order_id = %s
            """,
            (order_id,),
        )
        return serialize_row(cursor.fetchone())


def validate_customer_access(requested_customer_id: int) -> dict[str, Any] | None:
    current_customer_id, access_error = get_current_customer_id_or_error()
    if access_error is not None:
        return access_error

    if requested_customer_id != current_customer_id:
        return error_result(
            f"Access denied: customer {requested_customer_id} is not the active customer."
        )

    return None


def validate_order_access(order_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_customer_id, access_error = get_current_customer_id_or_error()
    if access_error is not None:
        return None, access_error

    order = lookup_order_record(order_id)
    if order is None:
        return None, error_result(f"Order {order_id} was not found.")

    order_customer_id = order.get("customer_id")
    if order_customer_id is None or int(order_customer_id) != current_customer_id:
        return None, error_result(
            f"Access denied: order {order_id} does not belong to the active customer."
        )

    return order, None


def order_lookup_tool(order_id: int) -> dict[str, Any]:
    try:
        order, access_error = validate_order_access(order_id)
        if access_error is not None:
            return access_error
        return {"ok": True, "tool": "OrderLookupTool", "order": order}
    except (MySQLError, RuntimeError) as exc:
        return error_result(f"Order lookup failed: {exc}")


def customer_profile_tool(customer_id: int) -> dict[str, Any]:
    try:
        access_error = validate_customer_access(customer_id)
        if access_error is not None:
            return access_error

        with get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT customer_id, name, email, created_at
                FROM customers
                WHERE customer_id = %s
                """,
                (customer_id,),
            )
            customer = serialize_row(cursor.fetchone())

        if customer is None:
            return error_result(f"Customer {customer_id} was not found.")

        return {"ok": True, "tool": "CustomerProfileTool", "customer": customer}
    except (MySQLError, RuntimeError) as exc:
        return error_result(f"Customer profile lookup failed: {exc}")


def refund_tool(order_id: int) -> dict[str, Any]:
    try:
        order, access_error = validate_order_access(order_id)
        if access_error is not None:
            return access_error

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                ("refund_requested", order_id),
            )
            connection.commit()

        return {
            "ok": True,
            "tool": "RefundTool",
            "message": f"Refund request for order {order_id} has been initiated.",
            "order": order,
        }
    except (MySQLError, RuntimeError) as exc:
        return error_result(f"Refund update failed: {exc}")


def complaint_logger_tool(
    customer_id: int | None,
    order_id: int | None,
    issue: str,
) -> dict[str, Any]:
    current_customer_id, access_error = get_current_customer_id_or_error()
    if access_error is not None:
        return access_error

    if customer_id is not None and customer_id != current_customer_id:
        return error_result(
            f"Access denied: complaint customer {customer_id} is not the active customer."
        )

    resolved_customer_id = current_customer_id

    if order_id is not None:
        order, order_access_error = validate_order_access(order_id)
        if order_access_error is not None:
            return order_access_error
        resolved_customer_id = int(order["customer_id"])

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO complaints (customer_id, order_id, issue, status)
                VALUES (%s, %s, %s, %s)
                """,
                (resolved_customer_id, order_id, issue, "open"),
            )
            complaint_id = cursor.lastrowid
            connection.commit()

        return {
            "ok": True,
            "tool": "ComplaintLoggerTool",
            "complaint_id": complaint_id,
            "message": "Complaint has been logged.",
            "customer_id": resolved_customer_id,
        }
    except (MySQLError, RuntimeError) as exc:
        return error_result(f"Complaint logging failed: {exc}")


def execute_tool(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent")
    order_id = state.get("order_id")
    customer_id = state.get("customer_id")
    user_input = str(state.get("input", ""))

    if intent == "track_order":
        if order_id is None:
            return error_result("Order lookup needs an order_id.")
        return order_lookup_tool(int(order_id))

    if intent == "customer_profile":
        if customer_id is None:
            return error_result("Customer profile lookup needs a customer_id.")
        return customer_profile_tool(int(customer_id))

    if intent == "refund_order":
        if order_id is None:
            return error_result("Refund request needs an order_id.")
        return refund_tool(int(order_id))

    if intent == "log_complaint":
        return complaint_logger_tool(
            int(customer_id) if customer_id is not None else None,
            int(order_id) if order_id is not None else None,
            user_input,
        )

    return {
        "ok": True,
        "tool": None,
        "message": "No external tool is needed for this intent.",
    }


@tool("OrderLookupTool")
def order_lookup_langchain_tool(order_id: int) -> dict[str, Any]:
    """Retrieve order details from MySQL by order_id for the active customer only."""
    return order_lookup_tool(order_id)


@tool("CustomerProfileTool")
def customer_profile_langchain_tool(customer_id: int) -> dict[str, Any]:
    """Retrieve customer profile details for the active customer only."""
    return customer_profile_tool(customer_id)


@tool("RefundTool")
def refund_langchain_tool(order_id: int) -> dict[str, Any]:
    """Request a refund for an order owned by the active customer."""
    return refund_tool(order_id)


@tool("ComplaintLoggerTool")
def complaint_logger_langchain_tool(
    issue: str,
    customer_id: int | None = None,
    order_id: int | None = None,
) -> dict[str, Any]:
    """Log a complaint for the active customer. Use order_id only for the active customer's order."""
    return complaint_logger_tool(customer_id=customer_id, order_id=order_id, issue=issue)


CUSTOMER_SERVICE_TOOLS = [
    order_lookup_langchain_tool,
    customer_profile_langchain_tool,
    refund_langchain_tool,
    complaint_logger_langchain_tool,
]
