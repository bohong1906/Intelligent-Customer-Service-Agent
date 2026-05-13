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


def order_lookup_tool(order_id: int) -> dict[str, Any]:
    try:
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
            order = serialize_row(cursor.fetchone())

        if order is None:
            return error_result(f"Order {order_id} was not found.")

        return {"ok": True, "tool": "OrderLookupTool", "order": order}
    except MySQLError as exc:
        return error_result(f"Order lookup failed: {exc}")


def customer_profile_tool(customer_id: int) -> dict[str, Any]:
    try:
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
    except MySQLError as exc:
        return error_result(f"Customer profile lookup failed: {exc}")


def refund_tool(order_id: int) -> dict[str, Any]:
    order_result = order_lookup_tool(order_id)
    if not order_result.get("ok"):
        return order_result

    try:
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
            "order": order_result["order"],
        }
    except MySQLError as exc:
        return error_result(f"Refund update failed: {exc}")


def complaint_logger_tool(
    customer_id: int | None,
    order_id: int | None,
    issue: str,
) -> dict[str, Any]:
    if customer_id is None and order_id is not None:
        order_result = order_lookup_tool(order_id)
        if not order_result.get("ok"):
            return order_result
        customer_id = int(order_result["order"]["customer_id"])

    if customer_id is None:
        return error_result("Complaint logging needs a customer_id or a valid order_id.")

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO complaints (customer_id, order_id, issue, status)
                VALUES (%s, %s, %s, %s)
                """,
                (customer_id, order_id, issue, "open"),
            )
            complaint_id = cursor.lastrowid
            connection.commit()

        return {
            "ok": True,
            "tool": "ComplaintLoggerTool",
            "complaint_id": complaint_id,
            "message": "Complaint has been logged.",
        }
    except MySQLError as exc:
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
    """Retrieve order details from MySQL by order_id."""
    return order_lookup_tool(order_id)


@tool("CustomerProfileTool")
def customer_profile_langchain_tool(customer_id: int) -> dict[str, Any]:
    """Retrieve customer profile details from MySQL by customer_id."""
    return customer_profile_tool(customer_id)


@tool("RefundTool")
def refund_langchain_tool(order_id: int) -> dict[str, Any]:
    """Request a refund by updating an order status to refund_requested."""
    return refund_tool(order_id)


@tool("ComplaintLoggerTool")
def complaint_logger_langchain_tool(
    issue: str,
    customer_id: int | None = None,
    order_id: int | None = None,
) -> dict[str, Any]:
    """Log a customer complaint in MySQL. Use order_id when the complaint is about an order."""
    return complaint_logger_tool(customer_id=customer_id, order_id=order_id, issue=issue)


CUSTOMER_SERVICE_TOOLS = [
    order_lookup_langchain_tool,
    customer_profile_langchain_tool,
    refund_langchain_tool,
    complaint_logger_langchain_tool,
]
