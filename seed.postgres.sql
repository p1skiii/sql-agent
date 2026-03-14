INSERT INTO users (email, full_name, city, created_at) VALUES
    ('olivia.chen@example.com', 'Olivia Chen', 'Shanghai', '2025-01-05 09:00:00'),
    ('liam.wang@example.com', 'Liam Wang', 'Shenzhen', '2025-01-10 10:30:00'),
    ('emma.li@example.com', 'Emma Li', 'Hangzhou', '2025-01-15 11:45:00');

INSERT INTO categories (name) VALUES
    ('Laptops'),
    ('Accessories'),
    ('Home Office');

INSERT INTO products (category_id, sku, name, price, status) VALUES
    (1, 'LAP-001', 'Aurora Pro 14', 1299.00, 'active'),
    (1, 'LAP-002', 'Nimbus Air 13', 999.00, 'active'),
    (2, 'ACC-001', 'Orbit Mouse', 49.00, 'active'),
    (2, 'ACC-002', 'Pulse Keyboard', 89.00, 'active'),
    (3, 'HOF-001', 'Lift Desk Mini', 399.00, 'active');

INSERT INTO inventory (product_id, quantity, reserved_quantity, updated_at) VALUES
    (1, 12, 2, '2025-02-20 09:00:00'),
    (2, 7, 1, '2025-02-20 09:05:00'),
    (3, 42, 5, '2025-02-20 09:10:00'),
    (4, 18, 3, '2025-02-20 09:15:00'),
    (5, 9, 1, '2025-02-20 09:20:00');

INSERT INTO orders (user_id, order_number, status, total_amount, created_at) VALUES
    (1, 'ORD-1001', 'paid', 1348.00, '2025-02-01 10:00:00'),
    (2, 'ORD-1002', 'pending', 89.00, '2025-02-03 14:30:00'),
    (1, 'ORD-1003', 'shipped', 448.00, '2025-02-08 16:15:00'),
    (3, 'ORD-1004', 'paid', 1048.00, '2025-02-11 19:20:00');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 1, 1299.00),
    (1, 3, 1, 49.00),
    (2, 4, 1, 89.00),
    (3, 5, 1, 399.00),
    (3, 3, 1, 49.00),
    (4, 2, 1, 999.00),
    (4, 3, 1, 49.00);

INSERT INTO payments (order_id, payment_method, status, amount, paid_at) VALUES
    (1, 'credit_card', 'paid', 1348.00, '2025-02-01 10:05:00'),
    (2, 'bank_transfer', 'pending', 89.00, NULL),
    (3, 'wallet', 'paid', 448.00, '2025-02-08 16:20:00'),
    (4, 'credit_card', 'paid', 1048.00, '2025-02-11 19:25:00');
