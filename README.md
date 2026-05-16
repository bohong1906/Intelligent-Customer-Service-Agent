# Intelligent-Customer-Service-Agent

This project implements an Intelligent Customer Service Agent with:

- LangGraph workflow
- ReAct-style tool calling
- MySQL-backed customer/order/complaint data
- Short-term memory through LangGraph checkpointer
- Long-term memory through MySQL
- Verifier loop for tool outputs and final responses

Current runtime flow:

```text
User Input
-> Planner Node
-> ReAct Agent Node
-> Tool Node? 
   yes -> Verifier Node -> ReAct Agent Node
   no  -> Verifier Node -> Long-Term Memory Write Node -> END
```

The `ReAct Agent Node` is responsible for both tool decisions and final customer-facing
responses. There is no separate final-response node.

## MySQL Installation

This project uses MySQL as the structured database for customer profiles, orders,
complaints, and long-term memory.

Reference: [在 Ubuntu 22.04 上安裝 MySQL Server](https://ui-code.com/archives/627)

### 1. Install MySQL Server

Update apt packages and install MySQL Server:

```bash
sudo apt update
sudo apt install mysql-server
```

Check whether the MySQL service is running:

```bash
sudo service mysql status
```

### 2. Run MySQL Security Setup

Run the security configuration script:

```bash
sudo mysql_secure_installation
```

Recommended choices:

- Set a root password.
- Remove anonymous users.
- Disable remote root login.
- Remove the test database.
- Reload privilege tables.

### 3. Verify MySQL Installation

Check the MySQL server version:

```bash
sudo mysqladmin -p -u root version
```

Current local setup:

```text
Server version: 8.0.45-0ubuntu0.22.04.1
Connection: Localhost via UNIX socket
UNIX socket: /var/run/mysqld/mysqld.sock
```

### 4. Create Project Database and User

Log in to MySQL as root:

```bash
sudo mysql -u root -p
```

Create the project database and a dedicated user:

```sql
CREATE DATABASE IF NOT EXISTS intelligent_customer_service;

CREATE USER IF NOT EXISTS 'ics_agent'@'localhost' IDENTIFIED BY 'your_password';
CREATE USER IF NOT EXISTS 'ics_agent'@'127.0.0.1' IDENTIFIED BY 'your_password';

ALTER USER 'ics_agent'@'localhost' IDENTIFIED BY 'your_password';
ALTER USER 'ics_agent'@'127.0.0.1' IDENTIFIED BY 'your_password';

GRANT ALL PRIVILEGES ON intelligent_customer_service.* TO 'ics_agent'@'localhost';
GRANT ALL PRIVILEGES ON intelligent_customer_service.* TO 'ics_agent'@'127.0.0.1';

FLUSH PRIVILEGES;
```

Replace `your_password` with the actual password used for local development.

Test the project user connection:

```bash
mysql -h 127.0.0.1 -P 3306 -u ics_agent -p intelligent_customer_service
```

### 5. VS Code MySQL Connection

For the MySQL Shell for VS Code extension, use:

```text
Host: 127.0.0.1
Port: 3306
User Name: ics_agent
Default Schema: intelligent_customer_service
```

## Environment Setup

This part performs the project environment setup.

### 1. Create a Conda Environment

First we create a conda env:

```bash
conda create -n ics-agent python==3.12
conda activate ics-agent
```

Then install dependencies:

```bash
cd Intelligent-Customer-Service-Agent
pip install -r requirements.txt
```

### 2. Configure `.env`

Create `.env` in the project root:

```env
OPENAI_KEY=your_openai_or_azure_openai_key
OPENAI_BASE=https://your-resource.openai.azure.com/openai/v1
OPENAI_MODEL=gpt-4o
OPENAI_VERIFIER_MODEL=gpt-4o

DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=ics_agent
DB_PASSWORD=your_mysql_password
DB_NAME=intelligent_customer_service

CURRENT_CUSTOMER_ID=1
MAX_TOOL_ITERATIONS=4
MAX_RESPONSE_REVISIONS=2
```

Notes:

- `OPENAI_MODEL` is used by planner and ReAct agent.
- `OPENAI_VERIFIER_MODEL` is used by verifier.
- `CURRENT_CUSTOMER_ID` is the active customer for demo queries like `Show my profile`.
- `MAX_TOOL_ITERATIONS` prevents infinite tool loops.
- `MAX_RESPONSE_REVISIONS` prevents infinite response-revision loops.
- Do not commit a real `.env` with actual keys or passwords.

### 3. Rebuild MySQL Data

If the database is empty, this is enough:

```bash
mysql -h 127.0.0.1 -P 3306 -u ics_agent -p intelligent_customer_service < schema.sql
```

If the tables already exist, the easiest way is to use the reset script in this repo root:

```bash
chmod +x scripts/reset_db.sh
./scripts/reset_db.sh
```

The script:

- reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` from `.env`
- drops the project tables in the correct order
- rebuilds the schema using the local `schema.sql` path derived from the script location

To inspect the current database contents, run:

```bash
./scripts/show_db_state.sh
```

This prints:

- `SHOW TABLES;`
- `SELECT * FROM customers;`
- `SELECT * FROM orders;`
- `SELECT * FROM complaints;`
- `SELECT * FROM customer_memory;`

If you prefer to run the commands manually, first open MySQL:

```bash
cd Intelligent-Customer-Service-Agent
mysql -h 127.0.0.1 -P 3306 -u ics_agent -p intelligent_customer_service
```

Then run:

```sql
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS customer_memory, complaints, orders, customers;
SET FOREIGN_KEY_CHECKS=1;
SOURCE schema.sql;
```

Check the seed data:

```sql
SELECT * FROM customers;
SELECT * FROM orders;
```

Expected seed orders:

```text
1001 -> Alice Chen -> Keyboard -> shipped
2222 -> Bob Lin    -> Monitor  -> processing
```

### 4. Run the Planner + ReAct Agent

After MySQL and `.env` are configured, run:

```bash
conda activate ics-agent
python main.py
```

Example query:

```text
Check status of order 1001
```

## Demo Test Flow

Run these in the same `python main.py` session so STM can carry context across turns.

```text
Where is my order 12345?
Check status of order 1001
Show my profile
Refund order 1001
I want to complain about order 2222 because the monitor delivery is taking too long
Refund order 2222 if delivered
Cancel it
What issues have I had before?
Remember I prefer refunds
My order is late again
Refund order 0000
```

Mapping to the project specification:

| # | Function | Demo query |
|---|---|---|
| 1 | Intent Parsing | `Where is my order 12345?` |
| 2 | OrderLookupTool | `Check status of order 1001` |
| 3 | CustomerProfileTool | `Show my profile` |
| 4 | RefundTool | `Refund order 1001` |
| 5 | ComplaintLoggerTool | `I want to complain about order 2222...` |
| 6 | Multi-step Reasoning | `Refund order 2222 if delivered` |
| 7 | Short-Term Memory | `Cancel it` |
| 8 | Long-Term Memory Read | `What issues have I had before?` |
| 9 | Long-Term Memory Write | `Remember I prefer refunds` |
| 10 | Personalization | `My order is late again` |
| 11 | Verifier / invalid order | `Refund order 0000` |

Useful MySQL checks after the demo:

```sql
SELECT * FROM complaints ORDER BY created_at DESC;
SELECT * FROM customer_memory ORDER BY created_at DESC;
SELECT * FROM orders ORDER BY order_id;
```
