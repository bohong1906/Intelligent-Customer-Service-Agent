CREATE DATABASE IF NOT EXISTS intelligent_customer_service
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE intelligent_customer_service;

CREATE TABLE IF NOT EXISTS customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivery_date TIMESTAMP NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    order_id INT NULL,
    issue TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_complaints_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_complaints_order
        FOREIGN KEY (order_id) REFERENCES orders(order_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS customer_memory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    `key` TEXT NOT NULL,
    `value` TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_memory_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_complaints_customer_id ON complaints(customer_id);
CREATE INDEX idx_complaints_order_id ON complaints(order_id);
CREATE INDEX idx_memory_customer_id ON customer_memory(customer_id);

INSERT INTO customers (name, email)
VALUES
    ('Alice Chen', 'alice@example.com'),
    ('Bob Lin', 'bob@example.com')
ON DUPLICATE KEY UPDATE
    name = VALUES(name);

INSERT INTO orders (order_id, customer_id, product_name, status, order_date, delivery_date)
VALUES
    (1001, 1, 'Keyboard', 'shipped', NOW(), NOW()),
    (2222, 2, 'Monitor', 'processing', NOW(), NULL)
ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    delivery_date = VALUES(delivery_date);

