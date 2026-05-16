#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${DB_HOST:?DB_HOST is required in .env}"
: "${DB_PORT:?DB_PORT is required in .env}"
: "${DB_USER:?DB_USER is required in .env}"
: "${DB_PASSWORD:?DB_PASSWORD is required in .env}"
: "${DB_NAME:?DB_NAME is required in .env}"

run_query() {
  local title="$1"
  local sql="$2"

  printf '\n==================== %s ====================\n\n' "$title"

  MYSQL_PWD="$DB_PASSWORD" mysql \
    --table \
    -h "$DB_HOST" \
    -P "$DB_PORT" \
    -u "$DB_USER" \
    "$DB_NAME" \
    -e "$sql"
}

run_query "TABLES" "SHOW TABLES;"
run_query "CUSTOMERS" "SELECT * FROM customers;"
run_query "ORDERS" "SELECT * FROM orders;"
run_query "COMPLAINTS" "SELECT * FROM complaints;"
run_query "CUSTOMER MEMORY" "SELECT * FROM customer_memory;"
