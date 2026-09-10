-- قاعدة بيانات نظام نقاط البيع لمحل التموين
-- شغّل الملف ده مرة واحدة بس على جهاز السيرفر (باستخدام MySQL Workbench أو mysql CLI)

CREATE DATABASE IF NOT EXISTS pos_tamween CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pos_tamween;

-- المستخدمين (أدمن / كاشير)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role ENUM('admin','cashier') NOT NULL DEFAULT 'cashier',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- التصنيفات
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

-- وحدات القياس (المستخدم يقدر يضيف وحدات جديدة بنفسه)
CREATE TABLE IF NOT EXISTS units (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL
);
INSERT INTO units (name) VALUES ('قطعة'), ('كيلو'), ('كرتونة'), ('علبة'), ('زجاجة')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- الأصناف: كل صنف له 4 أسعار دايمًا (تموين، حر، عيش، جملة)
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    barcode VARCHAR(64) UNIQUE,
    name VARCHAR(150) NOT NULL,
    category_id INT,
    unit VARCHAR(30) DEFAULT 'قطعة',
    price_tamween DECIMAL(10,2) NOT NULL DEFAULT 0,
    price_free DECIMAL(10,2) NOT NULL DEFAULT 0,
    price_bread DECIMAL(10,2) NOT NULL DEFAULT 0,
    price_wholesale DECIMAL(10,2) NOT NULL DEFAULT 0,
    purchase_price DECIMAL(10,2) NOT NULL DEFAULT 0,
    expiry_date DATE DEFAULT NULL,
    units_per_package INT DEFAULT NULL,
    quantity DECIMAL(10,3) NOT NULL DEFAULT 0,
    min_quantity DECIMAL(10,3) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
) ENGINE=InnoDB;

ALTER TABLE products ADD COLUMN IF NOT EXISTS purchase_price DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS expiry_date DATE DEFAULT NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS units_per_package INT DEFAULT NULL;

-- ترقية قواعد بيانات قديمة كانت بالإصدار الأول (سعرين بس) لإضافة الأعمدة الجديدة من غير ما تبوظ حاجة
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_tamween DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_free DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_bread DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_wholesale DECIMAL(10,2) NOT NULL DEFAULT 0;

-- بطاقات التموين (سجل داخلي للمحل فقط - وليس ربط رسمي بمنظومة الدولة)
CREATE TABLE IF NOT EXISTS ration_cards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    card_number VARCHAR(30) UNIQUE NOT NULL,
    holder_name VARCHAR(150),
    family_members INT DEFAULT 1,
    phone VARCHAR(20),
    monthly_limit DECIMAL(10,2) DEFAULT 0,   -- سقف استرشادي شهري بالجنيه (اختياري)
    bread_value DECIMAL(10,2) NOT NULL DEFAULT 0,   -- قيمة العيش المستحقة للبطاقة (قابلة للتعديل من شاشة البيع)
    pin_code VARCHAR(20) DEFAULT NULL,   -- الرقم السري: بيان محفوظ للمراجعة فقط، مش إجباري
    notes VARCHAR(255)
);

ALTER TABLE ration_cards ADD COLUMN IF NOT EXISTS bread_value DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE ration_cards ADD COLUMN IF NOT EXISTS pin_code VARCHAR(20) DEFAULT NULL;

-- الفواتير (إجمالي كل نوع سعر على حدة + الإجمالي الكلي)
CREATE TABLE IF NOT EXISTS invoices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_number VARCHAR(30) NOT NULL,
    user_id INT,
    ration_card_id INT DEFAULT NULL,
    shift_id INT DEFAULT NULL,
    total_tamween DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_free DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_bread DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_wholesale DECIMAL(10,2) NOT NULL DEFAULT 0,
    card_hit_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    support_tamween DECIMAL(10,2) NOT NULL DEFAULT 0,
    support_bread DECIMAL(10,2) NOT NULL DEFAULT 0,
    net_total DECIMAL(10,2) DEFAULT NULL,
    status ENUM('active','cancelled') NOT NULL DEFAULT 'active',
    cancelled_at TIMESTAMP NULL,
    cancelled_by INT DEFAULT NULL,
    cancel_reason VARCHAR(255),
    customer_id INT DEFAULT NULL,
    payment_method ENUM('cash','credit','visa','instapay','wallet') NOT NULL DEFAULT 'cash',
    grand_total DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (ration_card_id) REFERENCES ration_cards(id)
) ENGINE=InnoDB;

-- إزالة القيد الفريد القديم على رقم الفاتورة (بقى رقم الفاتورة بيتصفّر لكل وردية، مش فريد عالميًا)
SET @idx_exists := (
    SELECT COUNT(1) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='invoices' AND INDEX_NAME='invoice_number'
);
SET @drop_idx_sql := IF(@idx_exists > 0, 'ALTER TABLE invoices DROP INDEX invoice_number', 'SELECT 1');
PREPARE stmt FROM @drop_idx_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE invoices ADD COLUMN IF NOT EXISTS total_tamween DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS total_free DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS total_bread DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS total_wholesale DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS shift_id INT DEFAULT NULL;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS card_hit_amount DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS support_tamween DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS support_bread DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS net_total DECIMAL(10,2) DEFAULT NULL;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS status ENUM('active','cancelled') NOT NULL DEFAULT 'active';
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP NULL;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS cancelled_by INT DEFAULT NULL;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(255);

-- بنود الفاتورة (نوع البيع بقى 4 اختيارات بدل اتنين)
CREATE TABLE IF NOT EXISTS invoice_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id INT NOT NULL,
    product_id INT NOT NULL,
    sale_type ENUM('tamween','free','bread','wholesale') NOT NULL DEFAULT 'free',
    quantity DECIMAL(10,3) NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(10,2) NOT NULL,
    status ENUM('active','cancelled') NOT NULL DEFAULT 'active',
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB;

ALTER TABLE invoice_items ADD COLUMN IF NOT EXISTS status ENUM('active','cancelled') NOT NULL DEFAULT 'active';

ALTER TABLE invoice_items MODIFY COLUMN sale_type ENUM('tamween','free','bread','wholesale') NOT NULL DEFAULT 'free';

-- مستخدم أدمن افتراضي (اسم المستخدم: admin / الباسورد: admin123)
-- الهاش ده لكلمة admin123 بخوارزمية sha256 (البرنامج بيتأكد بنفس الطريقة)
INSERT INTO users (username, password_hash, full_name, role)
SELECT 'admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'مدير النظام', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='admin');

-- قائمة الصلاحيات المتاحة في البرنامج
CREATE TABLE IF NOT EXISTS permissions (
    permission_key VARCHAR(50) PRIMARY KEY,
    label VARCHAR(100) NOT NULL
);

INSERT INTO permissions (permission_key, label) VALUES
    ('pos_sell', 'شاشة البيع'),
    ('manage_inventory', 'إدارة المخزون والأصناف'),
    ('manage_ration_cards', 'إدارة بطاقات التموين'),
    ('view_reports', 'عرض التقارير'),
    ('manage_users', 'إدارة المستخدمين والصلاحيات'),
    ('manage_settings', 'إعدادات البرنامج')
ON DUPLICATE KEY UPDATE label = VALUES(label);

-- الورديات (تقفيل نهائي بيصفّر ترقيم الفواتير، والتسليم لموظف تاني بيسجل بس من غير تصفير)
CREATE TABLE IF NOT EXISTS shifts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    opened_by INT,
    closed_at TIMESTAMP NULL,
    closed_by INT NULL,
    status ENUM('open','closed') NOT NULL DEFAULT 'open',
    starting_cash DECIMAL(10,2) NOT NULL DEFAULT 0,
    expected_cash DECIMAL(10,2) DEFAULT NULL,
    actual_cash DECIMAL(10,2) DEFAULT NULL,
    notes VARCHAR(255),
    FOREIGN KEY (opened_by) REFERENCES users(id),
    FOREIGN KEY (closed_by) REFERENCES users(id)
) ENGINE=InnoDB;

ALTER TABLE shifts ADD COLUMN IF NOT EXISTS starting_cash DECIMAL(10,2) NOT NULL DEFAULT 0;

-- سجل تسليم الورديات بين الموظفين (من غير تقفيل نهائي ولا تصفير ترقيم)
CREATE TABLE IF NOT EXISTS shift_handovers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    shift_id INT NOT NULL,
    from_user INT,
    to_user INT,
    drawer_amount DECIMAL(10,2) DEFAULT NULL,
    handover_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(255),
    FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
    FOREIGN KEY (from_user) REFERENCES users(id),
    FOREIGN KEY (to_user) REFERENCES users(id)
) ENGINE=InnoDB;

ALTER TABLE shift_handovers ADD COLUMN IF NOT EXISTS drawer_amount DECIMAL(10,2) DEFAULT NULL;

INSERT INTO permissions (permission_key, label) VALUES
    ('manage_shift', 'تسليم/تقفيل الورديات')
ON DUPLICATE KEY UPDATE label = VALUES(label);
CREATE TABLE IF NOT EXISTS user_permissions (
    user_id INT NOT NULL,
    permission_key VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, permission_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_key) REFERENCES permissions(permission_key) ON DELETE CASCADE
);

-- سجل الحركة: مين عمل إيه وإمتى (لأغراض المراجعة والمتابعة)
CREATE TABLE IF NOT EXISTS activity_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    action VARCHAR(100) NOT NULL,
    details VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- الموردين
CREATE TABLE IF NOT EXISTS suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(20),
    address VARCHAR(255),
    notes VARCHAR(255)
);

-- فواتير استلام البضاعة (معلّقة لحد ما الأدمن يراجعها ويعتمدها)
CREATE TABLE IF NOT EXISTS supplier_invoices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT,
    reference_number VARCHAR(50),
    status ENUM('pending','approved') NOT NULL DEFAULT 'pending',
    payment_method ENUM('cash','credit') NOT NULL DEFAULT 'cash',
    created_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by INT,
    approved_at TIMESTAMP NULL,
    notes VARCHAR(255),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (approved_by) REFERENCES users(id)
) ENGINE=InnoDB;

ALTER TABLE supplier_invoices ADD COLUMN IF NOT EXISTS payment_method ENUM('cash','credit') NOT NULL DEFAULT 'cash';

-- دفعات المحل للمورد (لتقليل رصيد الآجل المستحق عليه)
CREATE TABLE IF NOT EXISTS supplier_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    paid_by INT,
    paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(255),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
    FOREIGN KEY (paid_by) REFERENCES users(id)
) ENGINE=InnoDB;

-- بنود فاتورة الاستلام (product_id ممكن يكون فاضي لو الصنف لسه مش موجود في المخزون)
CREATE TABLE IF NOT EXISTS supplier_invoice_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_invoice_id INT NOT NULL,
    product_id INT DEFAULT NULL,
    item_name VARCHAR(150) NOT NULL,
    quantity DECIMAL(10,3) NOT NULL,
    cost_price DECIMAL(10,2) DEFAULT NULL,
    price_tamween DECIMAL(10,2) NOT NULL DEFAULT 0,
    price_free DECIMAL(10,2) NOT NULL DEFAULT 0,
    price_bread DECIMAL(10,2) NOT NULL DEFAULT 0,
    price_wholesale DECIMAL(10,2) NOT NULL DEFAULT 0,
    is_package_quantity TINYINT(1) NOT NULL DEFAULT 0,
    update_prices TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (supplier_invoice_id) REFERENCES supplier_invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB;

ALTER TABLE supplier_invoice_items ADD COLUMN IF NOT EXISTS price_tamween DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE supplier_invoice_items ADD COLUMN IF NOT EXISTS price_free DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE supplier_invoice_items ADD COLUMN IF NOT EXISTS price_bread DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE supplier_invoice_items ADD COLUMN IF NOT EXISTS price_wholesale DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE supplier_invoice_items ADD COLUMN IF NOT EXISTS is_package_quantity TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE supplier_invoice_items ADD COLUMN IF NOT EXISTS update_prices TINYINT(1) NOT NULL DEFAULT 0;

INSERT INTO permissions (permission_key, label) VALUES
    ('manage_suppliers', 'تسجيل استلام بضاعة من الموردين'),
    ('approve_supplier_invoices', 'مراجعة واعتماد فواتير الموردين')
ON DUPLICATE KEY UPDATE label = VALUES(label);

-- رواتب الموظفين
CREATE TABLE IF NOT EXISTS employee_salaries (
    user_id INT PRIMARY KEY,
    monthly_salary DECIMAL(10,2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- سلف الموظفين (خوارج)
CREATE TABLE IF NOT EXISTS employee_advances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    given_by INT,
    given_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(255),
    settled_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (given_by) REFERENCES users(id)
) ENGINE=InnoDB;

-- جزاءات الموظفين (تتخصم من الراتب زي السلف بالظبط)
CREATE TABLE IF NOT EXISTS employee_penalties (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    reason VARCHAR(255),
    given_by INT,
    given_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (given_by) REFERENCES users(id)
) ENGINE=InnoDB;

-- غيابات الموظفين (تتخصم من الراتب زي السلف بالظبط)
CREATE TABLE IF NOT EXISTS employee_absences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    absence_date DATE NOT NULL,
    deduction_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    notes VARCHAR(255),
    given_by INT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (given_by) REFERENCES users(id)
) ENGINE=InnoDB;

-- سجل صرف الرواتب (الراتب الأساسي ناقص السلف = الصافي المدفوع)
CREATE TABLE IF NOT EXISTS salary_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    base_salary DECIMAL(10,2) NOT NULL,
    total_advances DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_penalties DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_absences DECIMAL(10,2) NOT NULL DEFAULT 0,
    net_paid DECIMAL(10,2) NOT NULL,
    paid_by INT,
    paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (paid_by) REFERENCES users(id)
) ENGINE=InnoDB;

ALTER TABLE salary_payments ADD COLUMN IF NOT EXISTS total_penalties DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE salary_payments ADD COLUMN IF NOT EXISTS total_absences DECIMAL(10,2) NOT NULL DEFAULT 0;

INSERT INTO permissions (permission_key, label) VALUES
    ('manage_payroll', 'إدارة الرواتب والسلف'),
    ('cancel_invoices', 'إلغاء الفواتير'),
    ('manage_customers', 'حسابات العملاء الآجلة')
ON DUPLICATE KEY UPDATE label = VALUES(label);

-- عملاء الآجل
CREATE TABLE IF NOT EXISTS customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(20),
    address VARCHAR(255),
    notes VARCHAR(255)
);

-- سداد العملاء (تقليل رصيد الآجل)
CREATE TABLE IF NOT EXISTS customer_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    received_by INT,
    paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(255),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (received_by) REFERENCES users(id)
) ENGINE=InnoDB;

SET @col_exists := (
    SELECT COUNT(1) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='invoices' AND COLUMN_NAME='customer_id'
);
SET @add_customer_id_sql := IF(@col_exists = 0, 'ALTER TABLE invoices ADD COLUMN customer_id INT DEFAULT NULL', 'SELECT 1');
PREPARE stmt FROM @add_customer_id_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE invoices MODIFY COLUMN payment_method ENUM('cash','credit','visa','instapay','wallet') NOT NULL DEFAULT 'cash';

-- هوالك المخزون (تالف/فاقد/منتهي الصلاحية... إلخ) بيتخصم من المخزون من غير بيع
CREATE TABLE IF NOT EXISTS inventory_waste (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    quantity DECIMAL(10,3) NOT NULL,
    reason VARCHAR(100),
    notes VARCHAR(255),
    supplier_id INT DEFAULT NULL,
    recorded_by INT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (recorded_by) REFERENCES users(id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
) ENGINE=InnoDB;

ALTER TABLE inventory_waste ADD COLUMN IF NOT EXISTS supplier_id INT DEFAULT NULL;

-- الفواتير المعلّقة (لو الكاشير عايز يوقف فاتورة عميل ويخدم عميل تاني، ويرجعلها بعدين)
CREATE TABLE IF NOT EXISTS held_sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    held_by INT,
    held_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ration_card_id INT DEFAULT NULL,
    card_hit_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    support_tamween DECIMAL(10,2) NOT NULL DEFAULT 0,
    support_bread DECIMAL(10,2) NOT NULL DEFAULT 0,
    label VARCHAR(100),
    cart_json TEXT NOT NULL,
    FOREIGN KEY (held_by) REFERENCES users(id),
    FOREIGN KEY (ration_card_id) REFERENCES ration_cards(id)
) ENGINE=InnoDB;

ALTER TABLE held_sales ADD COLUMN IF NOT EXISTS support_tamween DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE held_sales ADD COLUMN IF NOT EXISTS support_bread DECIMAL(10,2) NOT NULL DEFAULT 0;
