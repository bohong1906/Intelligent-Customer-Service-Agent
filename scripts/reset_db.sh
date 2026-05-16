#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
SCHEMA_FILE="$PROJECT_ROOT/schema.sql"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "Error: schema.sql not found at $SCHEMA_FILE" >&2
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

{
  printf '%s\n' \
    'SET FOREIGN_KEY_CHECKS=0;' \
    'DROP TABLE IF EXISTS customer_memory, complaints, orders, customers;' \
    'SET FOREIGN_KEY_CHECKS=1;'
  cat "$SCHEMA_FILE"
} | MYSQL_PWD="$DB_PASSWORD" mysql \
  -h "$DB_HOST" \
  -P "$DB_PORT" \
  -u "$DB_USER" \
  "$DB_NAME"

echo "Database rebuilt successfully from $SCHEMA_FILE"
