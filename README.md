# Intelligent-Customer-Service-Agent

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
This part will perform this project environment set-up steps.

### 1. Create a Conda Environmet

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

### 2. Run the Planner + ReAct Agent

After MySQL and `.env` are configured, run:

```bash
python main.py
```

Example query:

```text
Check status of order 1001
```

The runtime flow is:

```text
User Input -> Planner Node -> ReAct Assistant Node -> Tools Node -> ReAct Assistant Node -> Final Response
```
