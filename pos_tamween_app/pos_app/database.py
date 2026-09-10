# -*- coding: utf-8 -*-
"""
طبقة الاتصال بقاعدة البيانات (MySQL).
كل الأجهزة في المحل (الكاشير، جهاز المكتب، فرع تاني... إلخ) تتصل بنفس
السيرفر عن طريق الـ IP المكتوب في config.json، وبالتالي المخزون والمبيعات
بتتحدث لحظيًا لكل الأجهزة.
"""
import hashlib
import datetime
import json
import mysql.connector
from mysql.connector import Error as MySQLError

import config


class DatabaseError(Exception):
    pass


class Database:
    def __init__(self):
        self.cfg = config.load_config()
        self.conn = None

    # ---------- الاتصال ----------
    def connect(self):
        try:
            self.conn = mysql.connector.connect(
                host=self.cfg["db_host"],
                port=int(self.cfg["db_port"]),
                user=self.cfg["db_user"],
                password=self.cfg["db_password"],
                database=self.cfg["db_name"],
                autocommit=True,
            )
            # autocommit=True مهم جدًا: بدونه، أي قراءة (SELECT) كانت بتفضل فاتحة
            # "معاملة" (transaction) لحد ما حد يعمل commit، وده كان بيعمل قفل (lock)
            # على الجداول يمنع أي تعديل على قاعدة البيانات (زي ALTER TABLE) لحد ما
            # تقفل البرنامج تمامًا. دلوقتي كل قراءة بتتقفل فورًا فمفيش قفل معلّق.
            # العمليات اللي فيها أكتر من خطوة (زي إنشاء فاتورة) بتستخدم
            # start_transaction() صراحة عشان تفضل كلها تتنفذ مع بعض أو ولا حاجة خالص.
        except MySQLError as e:
            raise DatabaseError(
                f"تعذّر الاتصال بقاعدة البيانات على {self.cfg['db_host']}:{self.cfg['db_port']}\n"
                f"تأكد إن جهاز السيرفر شغال ومتصل بنفس الشبكة.\nتفاصيل: {e}"
            )
        return self.conn

    def ensure_connected(self):
        if self.conn is None or not self.conn.is_connected():
            self.connect()
        self._ensure_schema()

    def _ensure_schema(self):
        """
        يضيف أي أعمدة جديدة ناقصة في الجداول تلقائياً.
        بيحصل إن النسخة الاحتياطية القديمة مش بتحتوي على الأعمدة الجديدة،
        فلما البيانات بترجع من نسخة قديمة الجداول بتكون ناقصة.
        الحل: نتحقق من وجود كل عمود جديد ونضيفه لو ناقص.
        """
        try:
            cur = self.conn.cursor()
            migrations = [
                # held_sales: أعمدة الدعم
                ("held_sales", "support_tamween",
                 "ALTER TABLE held_sales ADD COLUMN support_tamween DECIMAL(10,2) DEFAULT 0"),
                ("held_sales", "support_bread",
                 "ALTER TABLE held_sales ADD COLUMN support_bread DECIMAL(10,2) DEFAULT 0"),
                # inventory_waste: عمود supplier_id
                ("inventory_waste", "supplier_id",
                 "ALTER TABLE inventory_waste ADD COLUMN supplier_id INT DEFAULT NULL"),
                # invoices: أعمدة الدعم لو ناقصة
                ("invoices", "support_tamween",
                 "ALTER TABLE invoices ADD COLUMN support_tamween DECIMAL(10,2) DEFAULT 0"),
                ("invoices", "support_bread",
                 "ALTER TABLE invoices ADD COLUMN support_bread DECIMAL(10,2) DEFAULT 0"),
                ("invoices", "customer_id",
                 "ALTER TABLE invoices ADD COLUMN customer_id INT DEFAULT NULL"),
                ("invoices", "payment_method",
                 "ALTER TABLE invoices ADD COLUMN payment_method VARCHAR(20) DEFAULT 'cash'"),
            ]
            for table, column, alter_sql in migrations:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
                    (table, column)
                )
                if cur.fetchone()[0] == 0:
                    cur.execute(alter_sql)
            cur.close()
        except Exception:
            # لو فشلت الـ migration مش هنوقف البرنامج
            pass

    def _cursor(self, dictionary=True):
        self.ensure_connected()
        return self.conn.cursor(dictionary=dictionary)

    # ---------- المستخدمين ----------
    @staticmethod
    def hash_password(raw_password: str) -> str:
        return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()

    def authenticate(self, username: str, password: str):
        cur = self._cursor()
        cur.execute(
            "SELECT id, username, full_name, role FROM users "
            "WHERE username=%s AND password_hash=%s AND is_active=1",
            (username, self.hash_password(password)),
        )
        row = cur.fetchone()
        cur.close()
        if row:
            if row["role"] == "admin":
                row["permissions"] = {p["permission_key"] for p in self.list_permissions()}
            else:
                row["permissions"] = self.get_user_permissions(row["id"])
            self.log_activity(row["id"], "login", f"تسجيل دخول: {row['username']}")
        return row

    def add_user(self, username, password, full_name, role="cashier", permission_keys=None):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s,%s,%s,%s)",
            (username, self.hash_password(password), full_name, role),
        )
        user_id = cur.lastrowid
        self.conn.commit()
        cur.close()
        if permission_keys:
            self.set_user_permissions(user_id, permission_keys)
        return user_id

    def update_user(self, user_id, full_name, role, is_active, permission_keys, new_password=None):
        cur = self._cursor()
        if new_password:
            cur.execute(
                "UPDATE users SET full_name=%s, role=%s, is_active=%s, password_hash=%s WHERE id=%s",
                (full_name, role, is_active, self.hash_password(new_password), user_id),
            )
        else:
            cur.execute(
                "UPDATE users SET full_name=%s, role=%s, is_active=%s WHERE id=%s",
                (full_name, role, is_active, user_id),
            )
        self.conn.commit()
        cur.close()
        self.set_user_permissions(user_id, permission_keys or [])

    def list_users(self):
        cur = self._cursor()
        cur.execute("SELECT id, username, full_name, role, is_active FROM users ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        for row in rows:
            row["permissions"] = self.get_user_permissions(row["id"]) if row["role"] != "admin" else set()
        return rows

    def get_user_by_id(self, user_id):
        cur = self._cursor()
        cur.execute("SELECT id, username, full_name, role, is_active FROM users WHERE id=%s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return row

    def username_exists(self, username):
        cur = self._cursor()
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        row = cur.fetchone()
        cur.close()
        return row is not None

    def delete_user(self, user_id):
        try:
            cur = self._cursor(dictionary=False)
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            if getattr(e, "errno", None) == 1451:
                raise DatabaseError(
                    "الموظف ده ليه فواتير أو سجلات تانية مرتبطة بيه، فمينفعش يتمسح نهائي "
                    "(عشان السجلات القديمة متتأثرش). استخدم زرار \"تعطيل\" بدل الحذف."
                )
            raise DatabaseError(f"فشل حذف المستخدم: {e}")

    # ---------- الصلاحيات ----------
    def list_permissions(self):
        cur = self._cursor()
        cur.execute("SELECT permission_key, label FROM permissions ORDER BY label")
        rows = cur.fetchall()
        cur.close()
        return rows

    def get_user_permissions(self, user_id):
        cur = self._cursor()
        cur.execute("SELECT permission_key FROM user_permissions WHERE user_id=%s", (user_id,))
        rows = cur.fetchall()
        cur.close()
        return {r["permission_key"] for r in rows}

    def set_user_permissions(self, user_id, permission_keys):
        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor()
        try:
            cur.execute("DELETE FROM user_permissions WHERE user_id=%s", (user_id,))
            for key in permission_keys:
                cur.execute(
                    "INSERT INTO user_permissions (user_id, permission_key) VALUES (%s,%s)",
                    (user_id, key),
                )
            self.conn.commit()
        except MySQLError as e:
            self.conn.rollback()
            raise DatabaseError(f"فشل حفظ الصلاحيات: {e}")
        finally:
            cur.close()

    # ---------- سجل الحركة ----------
    def log_activity(self, user_id, action, details=""):
        try:
            cur = self._cursor(dictionary=False)
            cur.execute(
                "INSERT INTO activity_log (user_id, action, details) VALUES (%s,%s,%s)",
                (user_id, action, details),
            )
            self.conn.commit()
            cur.close()
        except MySQLError:
            pass  # تسجيل الحركة مش لازم يوقف عملية أساسية لو فشل

    def list_activity_log(self, limit=200):
        cur = self._cursor()
        cur.execute(
            """SELECT al.*, u.full_name AS user_full_name FROM activity_log al
               LEFT JOIN users u ON u.id = al.user_id
               ORDER BY al.created_at DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    # ---------- الرواتب والسلف ----------
    def get_employee_salary(self, user_id):
        cur = self._cursor()
        cur.execute("SELECT monthly_salary FROM employee_salaries WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return float(row["monthly_salary"]) if row else 0.0

    def set_employee_salary(self, user_id, amount):
        cur = self._cursor()
        cur.execute(
            """INSERT INTO employee_salaries (user_id, monthly_salary) VALUES (%s,%s)
               ON DUPLICATE KEY UPDATE monthly_salary=%s""",
            (user_id, amount, amount),
        )
        self.conn.commit()
        cur.close()

    def add_advance(self, user_id, amount, given_by, notes=""):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO employee_advances (user_id, amount, given_by, notes) VALUES (%s,%s,%s,%s)",
            (user_id, amount, given_by, notes),
        )
        self.conn.commit()
        cur.close()
        self.log_activity(given_by, "add_advance", f"صرف سلفة {amount:.2f} ج.م لمستخدم رقم {user_id}")

    def get_outstanding_advances_total(self, user_id):
        cur = self._cursor()
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM employee_advances WHERE user_id=%s AND settled_at IS NULL",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
        return float(row["total"])

    def list_advances(self, user_id, only_outstanding=False):
        cur = self._cursor()
        if only_outstanding:
            cur.execute(
                "SELECT * FROM employee_advances WHERE user_id=%s AND settled_at IS NULL ORDER BY given_at DESC",
                (user_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM employee_advances WHERE user_id=%s ORDER BY given_at DESC",
                (user_id,),
            )
        rows = cur.fetchall()
        cur.close()
        return rows

    # ---------- الجزاءات ----------
    def add_penalty(self, user_id, amount, given_by, reason=""):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO employee_penalties (user_id, amount, reason, given_by) VALUES (%s,%s,%s,%s)",
            (user_id, amount, reason, given_by),
        )
        self.conn.commit()
        cur.close()
        self.log_activity(given_by, "add_penalty", f"جزاء {amount:.2f} ج.م لمستخدم رقم {user_id} - السبب: {reason}")

    def get_outstanding_penalties_total(self, user_id):
        cur = self._cursor()
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM employee_penalties WHERE user_id=%s AND settled_at IS NULL",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
        return float(row["total"])

    def list_penalties(self, user_id, only_outstanding=False):
        cur = self._cursor()
        if only_outstanding:
            cur.execute(
                "SELECT * FROM employee_penalties WHERE user_id=%s AND settled_at IS NULL ORDER BY given_at DESC",
                (user_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM employee_penalties WHERE user_id=%s ORDER BY given_at DESC",
                (user_id,),
            )
        rows = cur.fetchall()
        cur.close()
        return rows

    # ---------- الغيابات ----------
    def add_absence(self, user_id, absence_date, deduction_amount, given_by, notes=""):
        cur = self._cursor()
        cur.execute(
            """INSERT INTO employee_absences (user_id, absence_date, deduction_amount, notes, given_by)
               VALUES (%s,%s,%s,%s,%s)""",
            (user_id, absence_date, deduction_amount, notes, given_by),
        )
        self.conn.commit()
        cur.close()
        self.log_activity(
            given_by, "add_absence",
            f"تسجيل غياب لمستخدم رقم {user_id} يوم {absence_date} - خصم {deduction_amount:.2f} ج.م"
        )

    def get_outstanding_absences_total(self, user_id):
        cur = self._cursor()
        cur.execute(
            "SELECT COALESCE(SUM(deduction_amount),0) AS total FROM employee_absences WHERE user_id=%s AND settled_at IS NULL",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
        return float(row["total"])

    def list_absences(self, user_id, only_outstanding=False):
        cur = self._cursor()
        if only_outstanding:
            cur.execute(
                "SELECT * FROM employee_absences WHERE user_id=%s AND settled_at IS NULL ORDER BY absence_date DESC",
                (user_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM employee_absences WHERE user_id=%s ORDER BY absence_date DESC",
                (user_id,),
            )
        rows = cur.fetchall()
        cur.close()
        return rows

    def list_payroll_summary(self):
        """قائمة كل موظف نشط مع راتبه والخصومات المستحقة عليه (سلف + جزاءات + غيابات) والصافي المتبقي."""
        cur = self._cursor()
        cur.execute(
            """SELECT u.id, u.username, u.full_name, u.role,
                      COALESCE(es.monthly_salary,0) AS monthly_salary,
                      COALESCE((SELECT SUM(amount) FROM employee_advances
                                WHERE user_id=u.id AND settled_at IS NULL),0) AS outstanding_advances,
                      COALESCE((SELECT SUM(amount) FROM employee_penalties
                                WHERE user_id=u.id AND settled_at IS NULL),0) AS outstanding_penalties,
                      COALESCE((SELECT SUM(deduction_amount) FROM employee_absences
                                WHERE user_id=u.id AND settled_at IS NULL),0) AS outstanding_absences
               FROM users u
               LEFT JOIN employee_salaries es ON es.user_id = u.id
               WHERE u.is_active=1
               ORDER BY u.full_name"""
        )
        rows = cur.fetchall()
        cur.close()
        for r in rows:
            r["monthly_salary"] = float(r["monthly_salary"])
            r["outstanding_advances"] = float(r["outstanding_advances"])
            r["outstanding_penalties"] = float(r["outstanding_penalties"])
            r["outstanding_absences"] = float(r["outstanding_absences"])
            total_deductions = r["outstanding_advances"] + r["outstanding_penalties"] + r["outstanding_absences"]
            r["total_deductions"] = round(total_deductions, 2)
            r["net_due"] = round(r["monthly_salary"] - total_deductions, 2)
        return rows

    def pay_salary(self, user_id, paid_by, notes=""):
        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor(dictionary=True)
        try:
            base_salary = self.get_employee_salary(user_id)
            outstanding_advances = self.get_outstanding_advances_total(user_id)
            outstanding_penalties = self.get_outstanding_penalties_total(user_id)
            outstanding_absences = self.get_outstanding_absences_total(user_id)
            total_deductions = outstanding_advances + outstanding_penalties + outstanding_absences
            net_paid = round(base_salary - total_deductions, 2)

            cur.execute(
                """INSERT INTO salary_payments
                   (user_id, base_salary, total_advances, total_penalties, total_absences, net_paid, paid_by, notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (user_id, base_salary, outstanding_advances, outstanding_penalties,
                 outstanding_absences, net_paid, paid_by, notes),
            )
            cur.execute(
                "UPDATE employee_advances SET settled_at=NOW() WHERE user_id=%s AND settled_at IS NULL",
                (user_id,),
            )
            cur.execute(
                "UPDATE employee_penalties SET settled_at=NOW() WHERE user_id=%s AND settled_at IS NULL",
                (user_id,),
            )
            cur.execute(
                "UPDATE employee_absences SET settled_at=NOW() WHERE user_id=%s AND settled_at IS NULL",
                (user_id,),
            )
            self.conn.commit()
            cur.close()
            self.log_activity(
                paid_by, "pay_salary",
                f"صرف راتب لمستخدم رقم {user_id}: أساسي {base_salary:.2f} - "
                f"سلف {outstanding_advances:.2f} - جزاءات {outstanding_penalties:.2f} - "
                f"غيابات {outstanding_absences:.2f} = صافي {net_paid:.2f}"
            )
            return {
                "base_salary": base_salary,
                "total_advances": outstanding_advances,
                "total_penalties": outstanding_penalties,
                "total_absences": outstanding_absences,
                "net_paid": net_paid,
            }
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل صرف الراتب: {e}")

    def list_salary_payments(self, user_id):
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM salary_payments WHERE user_id=%s ORDER BY paid_at DESC",
            (user_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    # ---------- الموردين وفواتير الاستلام ----------
    def list_suppliers(self):
        cur = self._cursor()
        cur.execute("SELECT * FROM suppliers ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        return rows

    def add_supplier(self, data: dict):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO suppliers (name, phone, address, notes) VALUES (%(name)s, %(phone)s, %(address)s, %(notes)s)",
            data,
        )
        self.conn.commit()
        cur.close()

    def supplier_invoice_total_cost(self, invoice_id):
        cur = self._cursor()
        cur.execute(
            "SELECT COALESCE(SUM(quantity * COALESCE(cost_price,0)),0) AS total FROM supplier_invoice_items WHERE supplier_invoice_id=%s",
            (invoice_id,),
        )
        row = cur.fetchone()
        cur.close()
        return float(row["total"])

    def supplier_balance(self, supplier_id):
        cur = self._cursor()
        cur.execute(
            """SELECT si.id FROM supplier_invoices si
               WHERE si.supplier_id=%s AND si.payment_method='credit'""",
            (supplier_id,),
        )
        invoice_ids = [r["id"] for r in cur.fetchall()]
        owed_total = sum(self.supplier_invoice_total_cost(iid) for iid in invoice_ids)

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM supplier_payments WHERE supplier_id=%s",
            (supplier_id,),
        )
        paid_total = float(cur.fetchone()["total"])

        # نتحقق إن عمود supplier_id موجود في inventory_waste قبل ما نستخدمه
        try:
            cur.execute(
                """SELECT COALESCE(SUM(w.quantity * COALESCE(p.purchase_price,0)),0) AS total
                   FROM inventory_waste w JOIN products p ON p.id = w.product_id
                   WHERE w.supplier_id=%s""",
                (supplier_id,),
            )
            waste_total = float(cur.fetchone()["total"])
        except Exception:
            waste_total = 0.0
        cur.close()
        # لو الرقم طلع بالسالب، معناه المورد ده بقى عليه فلوس لينا (تعويض هالك أكتر من المستحق له)
        return round(owed_total - paid_total - waste_total, 2)

    def list_suppliers_with_balance(self):
        suppliers = self.list_suppliers()
        for s in suppliers:
            s["balance"] = self.supplier_balance(s["id"])
        return suppliers

    def record_supplier_payment(self, supplier_id, amount, paid_by, notes=""):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO supplier_payments (supplier_id, amount, paid_by, notes) VALUES (%s,%s,%s,%s)",
            (supplier_id, amount, paid_by, notes),
        )
        self.conn.commit()
        cur.close()
        self.log_activity(paid_by, "supplier_payment", f"دفع {amount:.2f} ج.م لمورد رقم {supplier_id}")

    def list_supplier_payments(self, supplier_id):
        cur = self._cursor()
        cur.execute(
            """SELECT sp.*, u.full_name AS paid_by_name FROM supplier_payments sp
               LEFT JOIN users u ON u.id = sp.paid_by
               WHERE sp.supplier_id=%s ORDER BY sp.paid_at DESC""",
            (supplier_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def list_supplier_credit_invoices(self, supplier_id):
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM supplier_invoices WHERE supplier_id=%s AND payment_method='credit' ORDER BY created_at DESC",
            (supplier_id,),
        )
        rows = cur.fetchall()
        for r in rows:
            r["total_cost"] = self.supplier_invoice_total_cost(r["id"])
        cur.close()
        return rows

    def create_supplier_invoice(self, supplier_id, created_by, reference_number, notes, items, payment_method="cash"):
        """items: [{product_id (ممكن None), item_name, quantity, cost_price (ممكن None)}, ...]"""
        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor(dictionary=True)
        try:
            cur.execute(
                """INSERT INTO supplier_invoices (supplier_id, reference_number, created_by, notes, status, payment_method)
                   VALUES (%s,%s,%s,%s,'pending',%s)""",
                (supplier_id, reference_number, created_by, notes, payment_method),
            )
            invoice_id = cur.lastrowid
            for item in items:
                cur.execute(
                    """INSERT INTO supplier_invoice_items
                       (supplier_invoice_id, product_id, item_name, quantity, cost_price,
                        price_tamween, price_free, price_bread, price_wholesale, is_package_quantity, update_prices)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (invoice_id, item.get("product_id"), item["item_name"], item["quantity"], item.get("cost_price"),
                     item.get("price_tamween", 0), item.get("price_free", 0),
                     item.get("price_bread", 0), item.get("price_wholesale", 0),
                     int(bool(item.get("is_package_quantity"))), int(bool(item.get("update_prices")))),
                )
            self.conn.commit()
            cur.close()
            self.log_activity(created_by, "create_supplier_invoice", f"تسجيل فاتورة استلام رقم {invoice_id}")
            return invoice_id
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل حفظ فاتورة الاستلام: {e}")

    def list_supplier_invoices(self, status=None):
        cur = self._cursor()
        if status:
            cur.execute(
                """SELECT si.*, s.name AS supplier_name, u.full_name AS created_by_name,
                          (SELECT COUNT(*) FROM supplier_invoice_items WHERE supplier_invoice_id=si.id) AS item_count
                   FROM supplier_invoices si
                   LEFT JOIN suppliers s ON s.id = si.supplier_id
                   LEFT JOIN users u ON u.id = si.created_by
                   WHERE si.status=%s ORDER BY si.created_at DESC""",
                (status,),
            )
        else:
            cur.execute(
                """SELECT si.*, s.name AS supplier_name, u.full_name AS created_by_name,
                          (SELECT COUNT(*) FROM supplier_invoice_items WHERE supplier_invoice_id=si.id) AS item_count
                   FROM supplier_invoices si
                   LEFT JOIN suppliers s ON s.id = si.supplier_id
                   LEFT JOIN users u ON u.id = si.created_by
                   ORDER BY si.created_at DESC"""
            )
        rows = cur.fetchall()
        cur.close()
        return rows

    def get_supplier_invoice(self, invoice_id):
        cur = self._cursor()
        cur.execute(
            """SELECT si.*, s.name AS supplier_name, u.full_name AS created_by_name
               FROM supplier_invoices si
               LEFT JOIN suppliers s ON s.id = si.supplier_id
               LEFT JOIN users u ON u.id = si.created_by
               WHERE si.id=%s""",
            (invoice_id,),
        )
        row = cur.fetchone()
        cur.close()
        return row

    def get_supplier_invoice_items(self, invoice_id):
        cur = self._cursor()
        cur.execute(
            """SELECT sii.*, p.name AS matched_product_name FROM supplier_invoice_items sii
               LEFT JOIN products p ON p.id = sii.product_id
               WHERE sii.supplier_invoice_id=%s""",
            (invoice_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def create_product_from_invoice_item(self, item_id, unit="قطعة"):
        cur = self._cursor()
        cur.execute("SELECT * FROM supplier_invoice_items WHERE id=%s", (item_id,))
        item = cur.fetchone()
        if not item:
            cur.close()
            raise DatabaseError("بند الفاتورة غير موجود")

        cur.execute(
            """INSERT INTO products (name, unit, price_tamween, price_free, price_bread,
               price_wholesale, quantity, min_quantity)
               VALUES (%s,%s,%s,%s,%s,%s,0,0)""",
            (item["item_name"], unit, item["price_tamween"], item["price_free"],
             item["price_bread"], item["price_wholesale"]),
        )
        product_id = cur.lastrowid
        cur.execute("UPDATE supplier_invoice_items SET product_id=%s WHERE id=%s", (product_id, item_id))
        self.conn.commit()
        cur.close()
        return product_id

    def link_invoice_item_product(self, item_id, product_id):
        cur = self._cursor()
        cur.execute("UPDATE supplier_invoice_items SET product_id=%s WHERE id=%s", (product_id, item_id))
        self.conn.commit()
        cur.close()

    def approve_supplier_invoice(self, invoice_id, user_id):
        items = self.get_supplier_invoice_items(invoice_id)
        unlinked = [it["item_name"] for it in items if not it["product_id"]]
        if unlinked:
            raise DatabaseError(
                "فيه أصناف لسه مش مربوطة بمنتج في المخزون: " + "، ".join(unlinked) +
                "\nاربطها الأول من قائمة المراجعة قبل الاعتماد."
            )

        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor(dictionary=True)
        try:
            for it in items:
                effective_qty = float(it["quantity"])
                if it.get("is_package_quantity"):
                    cur.execute("SELECT units_per_package FROM products WHERE id=%s", (it["product_id"],))
                    row = cur.fetchone()
                    units_per_package = float(row["units_per_package"]) if row and row["units_per_package"] else 1
                    effective_qty = effective_qty * units_per_package

                cur.execute(
                    "UPDATE products SET quantity = quantity + %s WHERE id=%s",
                    (effective_qty, it["product_id"]),
                )
                if it.get("cost_price"):
                    cur.execute(
                        "UPDATE products SET purchase_price=%s WHERE id=%s",
                        (it["cost_price"], it["product_id"]),
                    )
                if it.get("update_prices"):
                    cur.execute(
                        """UPDATE products SET price_tamween=%s, price_free=%s,
                           price_bread=%s, price_wholesale=%s WHERE id=%s""",
                        (it["price_tamween"], it["price_free"], it["price_bread"],
                         it["price_wholesale"], it["product_id"]),
                    )
            cur.execute(
                "UPDATE supplier_invoices SET status='approved', approved_by=%s, approved_at=NOW() WHERE id=%s",
                (user_id, invoice_id),
            )
            self.conn.commit()
            cur.close()
            self.log_activity(user_id, "approve_supplier_invoice", f"اعتماد فاتورة استلام رقم {invoice_id}")
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل اعتماد الفاتورة: {e}")

    # ---------- الفواتير المعلّقة ----------
    def hold_sale(self, user_id, cart, ration_card_id, card_hit_amount, label="", support_tamween=0, support_bread=0):
        cur = self._cursor()
        cur.execute(
            """INSERT INTO held_sales (held_by, ration_card_id, card_hit_amount, support_tamween, support_bread, label, cart_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (user_id, ration_card_id, card_hit_amount, support_tamween, support_bread, label, json.dumps(cart, ensure_ascii=False)),
        )
        self.conn.commit()
        cur.close()
        self.log_activity(user_id, "hold_sale", f"تعليق فاتورة: {label or '(بدون اسم)'}")

    def list_held_sales(self):
        cur = self._cursor()
        cur.execute(
            """SELECT hs.*, u.full_name AS held_by_name, rc.card_number, rc.holder_name
               FROM held_sales hs
               LEFT JOIN users u ON u.id = hs.held_by
               LEFT JOIN ration_cards rc ON rc.id = hs.ration_card_id
               ORDER BY hs.held_at DESC"""
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def delete_held_sale(self, held_id):
        cur = self._cursor()
        cur.execute("DELETE FROM held_sales WHERE id=%s", (held_id,))
        self.conn.commit()
        cur.close()

    # ---------- عملاء الآجل ----------
    def list_customers(self):
        cur = self._cursor()
        cur.execute("SELECT * FROM customers ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        return rows

    def get_customer(self, customer_id):
        cur = self._cursor()
        cur.execute("SELECT * FROM customers WHERE id=%s", (customer_id,))
        row = cur.fetchone()
        cur.close()
        return row

    def update_customer(self, customer_id, data: dict):
        cur = self._cursor()
        cur.execute(
            "UPDATE customers SET name=%(name)s, phone=%(phone)s, address=%(address)s, notes=%(notes)s WHERE id=%(id)s",
            {**data, "id": customer_id},
        )
        self.conn.commit()
        cur.close()

    def add_customer(self, data: dict):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO customers (name, phone, address, notes) VALUES (%(name)s, %(phone)s, %(address)s, %(notes)s)",
            data,
        )
        self.conn.commit()
        cur.close()

    def search_customers(self, term):
        cur = self._cursor()
        like = f"%{term}%"
        cur.execute("SELECT * FROM customers WHERE name LIKE %s ORDER BY name LIMIT 20", (like,))
        rows = cur.fetchall()
        cur.close()
        return rows

    def customer_balance(self, customer_id):
        cur = self._cursor()
        cur.execute(
            """SELECT COALESCE(SUM(COALESCE(net_total, grand_total)),0) AS total
               FROM invoices WHERE customer_id=%s AND payment_method='credit' AND status='active'""",
            (customer_id,),
        )
        credit_total = float(cur.fetchone()["total"])
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM customer_payments WHERE customer_id=%s",
            (customer_id,),
        )
        paid_total = float(cur.fetchone()["total"])
        cur.close()
        return round(credit_total - paid_total, 2)

    def list_customers_with_balance(self):
        customers = self.list_customers()
        for c in customers:
            c["balance"] = self.customer_balance(c["id"])
        return customers

    def record_customer_payment(self, customer_id, amount, received_by, notes=""):
        cur = self._cursor()
        cur.execute(
            "INSERT INTO customer_payments (customer_id, amount, received_by, notes) VALUES (%s,%s,%s,%s)",
            (customer_id, amount, received_by, notes),
        )
        self.conn.commit()
        cur.close()
        self.log_activity(received_by, "customer_payment", f"تحصيل {amount:.2f} ج.م من عميل رقم {customer_id}")

    def list_customer_payments(self, customer_id, year=None):
        cur = self._cursor()
        if year:
            cur.execute(
                """SELECT cp.*, u.full_name AS received_by_name FROM customer_payments cp
                   LEFT JOIN users u ON u.id = cp.received_by
                   WHERE cp.customer_id=%s AND YEAR(cp.paid_at)=%s ORDER BY cp.paid_at DESC""",
                (customer_id, year),
            )
        else:
            cur.execute(
                """SELECT cp.*, u.full_name AS received_by_name FROM customer_payments cp
                   LEFT JOIN users u ON u.id = cp.received_by
                   WHERE cp.customer_id=%s ORDER BY cp.paid_at DESC""",
                (customer_id,),
            )
        rows = cur.fetchall()
        cur.close()
        return rows

    def list_customer_credit_invoices(self, customer_id, year=None):
        cur = self._cursor()
        if year:
            cur.execute(
                """SELECT * FROM invoices WHERE customer_id=%s AND payment_method='credit'
                   AND YEAR(created_at)=%s ORDER BY created_at DESC""",
                (customer_id, year),
            )
        else:
            cur.execute(
                """SELECT * FROM invoices WHERE customer_id=%s AND payment_method='credit'
                   ORDER BY created_at DESC""",
                (customer_id,),
            )
        rows = cur.fetchall()
        cur.close()
        return rows

    def record_waste(self, product_id, quantity, reason, notes, user_id, supplier_id=None):
        cur = self._cursor()
        cur.execute("SELECT quantity, name FROM products WHERE id=%s", (product_id,))
        product = cur.fetchone()
        cur.close()
        if not product:
            raise DatabaseError("الصنف غير موجود")
        if float(product["quantity"]) < float(quantity):
            raise DatabaseError(
                f"الكمية المتاحة بالمخزون ({float(product['quantity']):g}) أقل من الكمية اللي عايز تسجلها كهالك"
            )

        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor()
        try:
            cur.execute("UPDATE products SET quantity = quantity - %s WHERE id=%s", (quantity, product_id))
            cur.execute(
                """INSERT INTO inventory_waste (product_id, quantity, reason, notes, supplier_id, recorded_by)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (product_id, quantity, reason, notes, supplier_id, user_id),
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل تسجيل الهالك: {e}")

        supplier_note = ""
        if supplier_id:
            cur = self._cursor()
            cur.execute("SELECT name FROM suppliers WHERE id=%s", (supplier_id,))
            s = cur.fetchone()
            cur.close()
            if s:
                supplier_note = f" - محسوبة على المورد: {s['name']}"

        self.log_activity(
            user_id, "record_waste",
            f"تسجيل هالك: {product['name']} - الكمية {quantity} ({reason}){supplier_note}"
        )

    def list_waste(self, date_from=None, date_to=None):
        cur = self._cursor()
        query = """SELECT w.*, p.name AS product_name, p.purchase_price, u.full_name AS recorded_by_name,
                          s.name AS supplier_name
                   FROM inventory_waste w
                   JOIN products p ON p.id = w.product_id
                   LEFT JOIN users u ON u.id = w.recorded_by
                   LEFT JOIN suppliers s ON s.id = w.supplier_id"""
        params = []
        if date_from and date_to:
            query += " WHERE DATE(w.recorded_at) BETWEEN %s AND %s"
            params = [date_from, date_to]
        query += " ORDER BY w.recorded_at DESC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()
        return rows

    # ---------- الأصناف ----------
    def list_categories(self):
        cur = self._cursor()
        cur.execute("SELECT id, name FROM categories ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        return rows

    def add_category(self, name):
        cur = self._cursor()
        cur.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
        self.conn.commit()
        new_id = cur.lastrowid
        cur.close()
        return new_id

    def find_product_by_barcode(self, barcode):
        cur = self._cursor()
        cur.execute("SELECT * FROM products WHERE barcode=%s", (barcode,))
        row = cur.fetchone()
        cur.close()
        return row

    def search_products(self, term):
        cur = self._cursor()
        like = f"%{term}%"
        cur.execute(
            "SELECT * FROM products WHERE name LIKE %s OR barcode LIKE %s ORDER BY name LIMIT 100",
            (like, like),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def list_products(self):
        cur = self._cursor()
        cur.execute("SELECT * FROM products ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        return rows

    def list_units(self):
        cur = self._cursor()
        cur.execute("SELECT * FROM units ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        return rows

    def add_unit(self, name):
        cur = self._cursor()
        cur.execute("INSERT INTO units (name) VALUES (%s)", (name,))
        self.conn.commit()
        cur.close()

    def add_product(self, data: dict):
        data = dict(data)
        data.setdefault("purchase_price", 0)
        data.setdefault("expiry_date", None)
        data.setdefault("units_per_package", None)
        cur = self._cursor()
        cur.execute(
            """INSERT INTO products
               (barcode, name, category_id, unit, price_tamween, price_free,
                price_bread, price_wholesale, purchase_price, expiry_date, units_per_package, quantity, min_quantity)
               VALUES (%(barcode)s, %(name)s, %(category_id)s, %(unit)s,
                       %(price_tamween)s, %(price_free)s, %(price_bread)s,
                       %(price_wholesale)s, %(purchase_price)s, %(expiry_date)s, %(units_per_package)s,
                       %(quantity)s, %(min_quantity)s)""",
            data,
        )
        self.conn.commit()
        cur.close()

    def update_product(self, product_id, data: dict):
        data = dict(data)
        data["id"] = product_id
        data.setdefault("purchase_price", 0)
        data.setdefault("expiry_date", None)
        data.setdefault("units_per_package", None)
        cur = self._cursor()
        cur.execute(
            """UPDATE products SET barcode=%(barcode)s, name=%(name)s,
               category_id=%(category_id)s, unit=%(unit)s,
               price_tamween=%(price_tamween)s, price_free=%(price_free)s,
               price_bread=%(price_bread)s, price_wholesale=%(price_wholesale)s,
               purchase_price=%(purchase_price)s, expiry_date=%(expiry_date)s,
               units_per_package=%(units_per_package)s,
               quantity=%(quantity)s, min_quantity=%(min_quantity)s
               WHERE id=%(id)s""",
            data,
        )
        self.conn.commit()
        cur.close()

    def products_expiring_soon(self, days=30):
        cur = self._cursor()
        cur.execute(
            """SELECT * FROM products
               WHERE expiry_date IS NOT NULL
                 AND expiry_date <= DATE_ADD(CURRENT_DATE(), INTERVAL %s DAY)
               ORDER BY expiry_date ASC""",
            (days,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def delete_product(self, product_id):
        cur = self._cursor()
        try:
            cur.execute("DELETE FROM products WHERE id=%s", (product_id,))
            self.conn.commit()
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            if e.errno == 1451:
                raise DatabaseError(
                    "مينفعش تمسح الصنف ده لأنه مرتبط بفواتير بيع أو استلام أو سجل هوالك سابق. "
                    "تقدر بدل الحذف تخلي الكمية = صفر عشان يفضل التاريخ محفوظ."
                )
            raise DatabaseError(f"فشل حذف الصنف: {e}")
        cur.close()

    def adjust_stock(self, product_id, delta_qty, cursor=None):
        """delta_qty سالب عند البيع وموجب عند التوريد/الإرجاع."""
        own_cursor = cursor is None
        cur = cursor or self._cursor(dictionary=False)
        cur.execute(
            "UPDATE products SET quantity = quantity + %s WHERE id=%s",
            (delta_qty, product_id),
        )
        if own_cursor:
            self.conn.commit()
            cur.close()

    def low_stock_products(self):
        cur = self._cursor()
        cur.execute("SELECT * FROM products WHERE quantity <= min_quantity ORDER BY quantity")
        rows = cur.fetchall()
        cur.close()
        return rows

    # ---------- بطاقات التموين ----------
    def find_ration_card(self, card_number):
        cur = self._cursor()
        cur.execute("SELECT * FROM ration_cards WHERE card_number=%s", (card_number,))
        row = cur.fetchone()
        cur.close()
        return row

    def add_ration_card(self, data: dict):
        data = dict(data)
        data.setdefault("bread_value", 0)
        data.setdefault("pin_code", None)
        cur = self._cursor()
        cur.execute(
            """INSERT INTO ration_cards (card_number, holder_name, family_members, phone, monthly_limit, bread_value, pin_code, notes)
               VALUES (%(card_number)s, %(holder_name)s, %(family_members)s, %(phone)s, %(monthly_limit)s, %(bread_value)s, %(pin_code)s, %(notes)s)""",
            data,
        )
        self.conn.commit()
        cur.close()

    def get_ration_card_by_id(self, card_id):
        cur = self._cursor()
        cur.execute("SELECT * FROM ration_cards WHERE id=%s", (card_id,))
        row = cur.fetchone()
        cur.close()
        return row

    def update_ration_card(self, card_id, data: dict):
        data = dict(data)
        data["id"] = card_id
        data.setdefault("bread_value", 0)
        data.setdefault("pin_code", None)
        try:
            cur = self._cursor()
            cur.execute(
                """UPDATE ration_cards SET card_number=%(card_number)s, holder_name=%(holder_name)s,
                   family_members=%(family_members)s, phone=%(phone)s, monthly_limit=%(monthly_limit)s,
                   bread_value=%(bread_value)s, pin_code=%(pin_code)s, notes=%(notes)s WHERE id=%(id)s""",
                data,
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            raise DatabaseError(f"فشل تعديل بيانات البطاقة: {e}")

    def update_card_quick(self, card_id, family_members, bread_value):
        """تحديث سريع لعدد الأفراد وقيمة العيش من شاشة البيع من غير الحاجة لفتح شاشة البطاقات."""
        try:
            cur = self._cursor()
            cur.execute(
                "UPDATE ration_cards SET family_members=%s, bread_value=%s WHERE id=%s",
                (family_members, bread_value, card_id),
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            raise DatabaseError(f"فشل تحديث بيانات البطاقة: {e}")

    def list_ration_cards(self):
        cur = self._cursor()
        cur.execute("SELECT * FROM ration_cards ORDER BY holder_name")
        rows = cur.fetchall()
        cur.close()
        return rows

    def ration_card_monthly_usage(self, ration_card_id):
        """إجمالي مبيعات صنف التموين لبطاقة معينة خلال الشهر الحالي (سجل داخلي فقط)."""
        cur = self._cursor()
        cur.execute(
            """SELECT COALESCE(SUM(total_tamween),0) AS total
               FROM invoices
               WHERE ration_card_id=%s AND status='active'
                 AND MONTH(created_at)=MONTH(CURRENT_DATE())
                 AND YEAR(created_at)=YEAR(CURRENT_DATE())""",
            (ration_card_id,),
        )
        row = cur.fetchone()
        cur.close()
        return float(row["total"]) if row else 0.0

    # ---------- الورديات ----------
    def get_open_shift(self):
        try:
            cur = self._cursor()
            cur.execute("SELECT * FROM shifts WHERE status='open' ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            cur.close()
            return row
        except MySQLError as e:
            raise DatabaseError(f"فشل قراءة حالة الوردية: {e}")

    def open_shift(self, user_id, starting_cash=0):
        try:
            cur = self._cursor()
            cur.execute(
                "INSERT INTO shifts (opened_by, status, starting_cash) VALUES (%s,'open',%s)",
                (user_id, starting_cash),
            )
            shift_id = cur.lastrowid
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            raise DatabaseError(f"فشل فتح وردية جديدة: {e}")
        self.log_activity(
            user_id, "open_shift",
            f"بدء وردية جديدة رقم {shift_id} برأس مال {starting_cash:.2f} ج.م"
        )
        return shift_id

    def ensure_open_shift(self, user_id):
        """يرجع الوردية المفتوحة الحالية، ولو مفيش، يفتح وردية جديدة تلقائيًا."""
        shift = self.get_open_shift()
        if shift:
            return shift["id"]
        return self.open_shift(user_id)

    def handover_shift(self, shift_id, from_user_id, to_user_id, drawer_amount, notes=""):
        try:
            cur = self._cursor()
            cur.execute(
                "INSERT INTO shift_handovers (shift_id, from_user, to_user, drawer_amount, notes) VALUES (%s,%s,%s,%s,%s)",
                (shift_id, from_user_id, to_user_id, drawer_amount, notes),
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            raise DatabaseError(f"فشل تسجيل تسليم الوردية: {e}")
        self.log_activity(
            from_user_id, "handover_shift",
            f"تسليم الوردية رقم {shift_id} - قيمة الدرج وقت التسليم: {drawer_amount:.2f} ج.م"
        )

    def shift_summary(self, shift_id):
        try:
            cur = self._cursor()
            cur.execute(
                """SELECT COUNT(*) AS invoice_count,
                          COALESCE(SUM(total_tamween),0) AS total_tamween,
                          COALESCE(SUM(total_free),0) AS total_free,
                          COALESCE(SUM(total_bread),0) AS total_bread,
                          COALESCE(SUM(total_wholesale),0) AS total_wholesale,
                          COALESCE(SUM(grand_total),0) AS grand_total
                   FROM invoices WHERE shift_id=%s AND status='active'""",
                (shift_id,),
            )
            row = cur.fetchone()
            cur.close()
            return row
        except MySQLError as e:
            raise DatabaseError(f"فشل حساب ملخص الوردية: {e}")

    def shift_handover_history(self, shift_id):
        try:
            cur = self._cursor()
            cur.execute(
                """SELECT sh.*, u1.full_name AS from_name, u2.full_name AS to_name
                   FROM shift_handovers sh
                   LEFT JOIN users u1 ON u1.id = sh.from_user
                   LEFT JOIN users u2 ON u2.id = sh.to_user
                   WHERE sh.shift_id=%s ORDER BY sh.handover_at""",
                (shift_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return rows
        except MySQLError as e:
            raise DatabaseError(f"فشل قراءة سجل التسليمات: {e}")

    def close_shift(self, shift_id, user_id, actual_cash):
        summary = self.shift_summary(shift_id)
        starting_cash = self.get_shift_starting_cash(shift_id)
        expected_cash = round(starting_cash + float(summary["grand_total"]), 2)
        try:
            cur = self._cursor()
            cur.execute(
                """UPDATE shifts SET status='closed', closed_at=NOW(), closed_by=%s,
                   expected_cash=%s, actual_cash=%s WHERE id=%s""",
                (user_id, expected_cash, actual_cash, shift_id),
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            raise DatabaseError(f"فشل تقفيل الوردية: {e}")
        difference = round(actual_cash - expected_cash, 2)
        self.log_activity(
            user_id, "close_shift",
            f"تقفيل الوردية رقم {shift_id} - رأس مال {starting_cash:.2f} + مبيعات {float(summary['grand_total']):.2f} "
            f"= متوقع {expected_cash:.2f}، والفعلي {actual_cash:.2f} (الفرق {difference:+.2f})"
        )
        result = dict(summary)
        result["starting_cash"] = starting_cash
        result["expected_cash"] = expected_cash
        result["actual_cash"] = actual_cash
        result["difference"] = difference
        return result

    def get_shift_starting_cash(self, shift_id):
        cur = self._cursor()
        cur.execute("SELECT starting_cash FROM shifts WHERE id=%s", (shift_id,))
        row = cur.fetchone()
        cur.close()
        return float(row["starting_cash"]) if row else 0.0

    # ---------- الفواتير ----------
    def next_invoice_number(self, shift_id):
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) AS c FROM invoices WHERE shift_id=%s", (shift_id,))
        row = cur.fetchone()
        cur.close()
        return f"{row['c'] + 1:05d}"

    def create_invoice(self, user_id, ration_card_id, items, shift_id, card_hit_amount=0,
                        customer_id=None, payment_method="cash", support_tamween=0, support_bread=0):
        """
        items: قائمة عناصر [{product_id, sale_type ('tamween'/'free'/'bread'/'wholesale'), quantity, unit_price}, ...]
        بيتم خصم المخزون تلقائيًا وبشكل متزامن (transaction واحدة).
        رقم الفاتورة بيتصفّر تلقائيًا مع كل وردية جديدة (shift_id مختلف).
        card_hit_amount: مبلغ "خدمة" اللي بيتضاف على الفاتورة.
        support_tamween + support_bread = "الدعم"، بيتخصموا من (الإجمالي + الخدمة) عشان يطلع "المطلوب" من العميل.
        customer_id + payment_method='credit': بيع بالآجل، بيتضاف لرصيد العميل بدل التحصيل الفوري.
        """
        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor(dictionary=True)
        try:
            totals = {"tamween": 0.0, "free": 0.0, "bread": 0.0, "wholesale": 0.0}
            invoice_number = self.next_invoice_number(shift_id)

            cur.execute(
                """INSERT INTO invoices (invoice_number, user_id, ration_card_id, shift_id,
                   total_tamween, total_free, total_bread, total_wholesale, card_hit_amount,
                   support_tamween, support_bread, net_total,
                   grand_total, customer_id, payment_method)
                   VALUES (%s, %s, %s, %s, 0, 0, 0, 0, %s, %s, %s, 0, 0, %s, %s)""",
                (invoice_number, user_id, ration_card_id, shift_id, card_hit_amount,
                 support_tamween, support_bread, customer_id, payment_method),
            )
            invoice_id = cur.lastrowid

            for item in items:
                line_total = round(float(item["quantity"]) * float(item["unit_price"]), 2)
                totals[item["sale_type"]] += line_total

                cur.execute(
                    """INSERT INTO invoice_items
                       (invoice_id, product_id, sale_type, quantity, unit_price, line_total)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (invoice_id, item["product_id"], item["sale_type"],
                     item["quantity"], item["unit_price"], line_total),
                )
                # خصم من المخزون بشرط توفر الكمية وقت التنفيذ الفعلي (يمنع بيع نفس القطعة
                # من جهازين في نفس اللحظة حتى لو الاتنين شافوا نفس الكمية المتاحة قبل كده)
                cur.execute(
                    "UPDATE products SET quantity = quantity - %s WHERE id=%s AND quantity >= %s",
                    (item["quantity"], item["product_id"], item["quantity"]),
                )
                if cur.rowcount == 0:
                    raise DatabaseError(
                        f"الكمية المتاحة تغيّرت أو خلصت أثناء إتمام البيع (صنف رقم {item['product_id']}). "
                        "من فضلك راجع الفاتورة وحاول تاني."
                    )

            grand_total = round(sum(totals.values()), 2)
            total_with_service = round(grand_total + float(card_hit_amount), 2)
            net_total = round(total_with_service - float(support_tamween) - float(support_bread), 2)
            cur.execute(
                """UPDATE invoices SET total_tamween=%s, total_free=%s, total_bread=%s,
                   total_wholesale=%s, grand_total=%s, net_total=%s WHERE id=%s""",
                (round(totals["tamween"], 2), round(totals["free"], 2),
                 round(totals["bread"], 2), round(totals["wholesale"], 2),
                 grand_total, net_total, invoice_id),
            )

            self.conn.commit()
            cur.close()
            required_amount = round(net_total, 2) if net_total > 0 else 0.0
            remaining_amount = round(-net_total, 2) if net_total < 0 else 0.0
            return {
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "total_tamween": round(totals["tamween"], 2),
                "total_free": round(totals["free"], 2),
                "total_bread": round(totals["bread"], 2),
                "total_wholesale": round(totals["wholesale"], 2),
                "grand_total": grand_total,
                "card_hit_amount": round(float(card_hit_amount), 2),
                "total_with_service": total_with_service,
                "support_tamween": round(float(support_tamween), 2),
                "support_bread": round(float(support_bread), 2),
                "net_total": net_total,
                "required_amount": required_amount,
                "remaining_amount": remaining_amount,
                "payment_method": payment_method,
                "customer_id": customer_id,
            }
        except DatabaseError:
            self.conn.rollback()
            cur.close()
            raise
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل حفظ الفاتورة: {e}")

    def employee_performance_report(self, user_id, date_from, date_to):
        cur = self._cursor()
        cur.execute(
            """SELECT COUNT(*) AS invoice_count,
                      COUNT(DISTINCT shift_id) AS shifts_worked,
                      COUNT(DISTINCT ration_card_id) AS ration_cards_used,
                      COALESCE(SUM(total_tamween),0) AS total_tamween,
                      COALESCE(SUM(total_free),0) AS total_free,
                      COALESCE(SUM(total_bread),0) AS total_bread,
                      COALESCE(SUM(total_wholesale),0) AS total_wholesale,
                      COALESCE(SUM(grand_total),0) AS grand_total
               FROM invoices
               WHERE user_id=%s AND status='active' AND DATE(created_at) BETWEEN %s AND %s""",
            (user_id, date_from, date_to),
        )
        row = cur.fetchone()
        cur.close()
        return row

    def employee_shifts_breakdown(self, user_id, date_from, date_to):
        cur = self._cursor()
        cur.execute(
            """SELECT i.shift_id, COUNT(*) AS invoice_count, SUM(i.grand_total) AS employee_sales,
                      s.status, s.expected_cash, s.actual_cash, s.opened_at, s.closed_at
               FROM invoices i
               LEFT JOIN shifts s ON s.id = i.shift_id
               WHERE i.user_id=%s AND i.shift_id IS NOT NULL AND i.status='active'
                 AND DATE(i.created_at) BETWEEN %s AND %s
               GROUP BY i.shift_id
               ORDER BY i.shift_id DESC""",
            (user_id, date_from, date_to),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def payment_method_report(self, date_from, date_to):
        cur = self._cursor()
        cur.execute(
            """SELECT payment_method, COUNT(*) AS invoice_count,
                      COALESCE(SUM(COALESCE(net_total, grand_total)),0) AS total
               FROM invoices
               WHERE status='active' AND DATE(created_at) BETWEEN %s AND %s
               GROUP BY payment_method
               ORDER BY total DESC""",
            (date_from, date_to),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def inventory_stocktake_report(self, date_from=None, date_to=None):
        """
        لكل صنف: الكمية المباعة خلال الفترة المحددة (لو اتبعتت)، والكمية المتبقية بالمخزون حاليًا.
        لو مبعتش تواريخ، الكمية المباعة بتطلع صفر لكل الأصناف.
        """
        cur = self._cursor()
        if date_from and date_to:
            cur.execute(
                """SELECT p.id, p.name, p.quantity AS remaining,
                          COALESCE((SELECT SUM(ii.quantity) FROM invoice_items ii
                                    JOIN invoices i ON i.id = ii.invoice_id
                                    WHERE ii.product_id = p.id AND i.status='active' AND ii.status='active'
                                      AND DATE(i.created_at) BETWEEN %s AND %s), 0) AS sold
                   FROM products p
                   ORDER BY p.name""",
                (date_from, date_to),
            )
        else:
            cur.execute("SELECT id, name, quantity AS remaining, 0 AS sold FROM products ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        for r in rows:
            r["remaining"] = float(r["remaining"])
            r["sold"] = float(r["sold"])
        return rows

    def sales_report(self, date_from, date_to):
        cur = self._cursor()
        cur.execute(
            """SELECT DATE(created_at) AS day,
                      SUM(total_tamween) AS total_tamween,
                      SUM(total_free) AS total_free,
                      SUM(total_bread) AS total_bread,
                      SUM(total_wholesale) AS total_wholesale,
                      SUM(grand_total) AS grand_total,
                      COUNT(*) AS invoice_count
               FROM invoices
               WHERE status='active' AND DATE(created_at) BETWEEN %s AND %s
               GROUP BY DATE(created_at)
               ORDER BY day DESC""",
            (date_from, date_to),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def profit_report(self, date_from, date_to):
        """
        لكل صنف اتباع في الفترة دي: سعر الشراء، إجمالي الكمية المباعة، إجمالي سعر البيع الفعلي
        اللي اتباع بيه (مهما كان نوعه تموين/حر/عيش/جملة)، والمكسب = البيع - التكلفة.
        """
        cur = self._cursor()
        cur.execute(
            """SELECT p.name, p.purchase_price, SUM(ii.quantity) AS total_qty,
                      SUM(ii.line_total) AS total_revenue,
                      SUM(ii.quantity * COALESCE(p.purchase_price,0)) AS total_cost
               FROM invoice_items ii
               JOIN invoices i ON i.id = ii.invoice_id
               JOIN products p ON p.id = ii.product_id
               WHERE i.status='active' AND ii.status='active' AND DATE(i.created_at) BETWEEN %s AND %s
               GROUP BY ii.product_id
               ORDER BY (SUM(ii.line_total) - SUM(ii.quantity * COALESCE(p.purchase_price,0))) DESC""",
            (date_from, date_to),
        )
        rows = cur.fetchall()
        cur.close()
        for r in rows:
            r["total_qty"] = float(r["total_qty"])
            r["total_revenue"] = float(r["total_revenue"])
            r["total_cost"] = float(r["total_cost"])
            r["profit"] = round(r["total_revenue"] - r["total_cost"], 2)
        return rows

    def tamween_report(self, date_from, date_to):
        """ملخص بسيط: عدد الفواتير اللي اتباع فيها صنف بسعر تموين، وإجمالي قيمة التموين المباع، خلال الفترة."""
        cur = self._cursor()
        cur.execute(
            """SELECT COUNT(DISTINCT i.id) AS card_count,
                      COALESCE(SUM(ii.line_total), 0) AS total_amount
               FROM invoice_items ii
               JOIN invoices i ON i.id = ii.invoice_id
               WHERE i.status='active' AND ii.status='active' AND ii.sale_type='tamween'
                 AND DATE(i.created_at) BETWEEN %s AND %s""",
            (date_from, date_to),
        )
        row = cur.fetchone()
        cur.close()
        return {"card_count": int(row["card_count"] or 0), "total_amount": float(row["total_amount"] or 0)}

    def tamween_cards_used_count(self, date_from, date_to):
        """عدد بطاقات التموين المميزة اللي اتضربت (اشترت بسعر تموين) خلال الفترة دي."""
        cur = self._cursor()
        cur.execute(
            """SELECT COUNT(DISTINCT i.ration_card_id) AS card_count
               FROM invoices i
               JOIN invoice_items ii ON ii.invoice_id = i.id
               WHERE i.status='active' AND ii.status='active' AND ii.sale_type='tamween'
                 AND i.ration_card_id IS NOT NULL
                 AND DATE(i.created_at) BETWEEN %s AND %s""",
            (date_from, date_to),
        )
        row = cur.fetchone()
        cur.close()
        return int(row["card_count"] or 0)

    def best_selling_products(self, date_from, date_to, limit=20, name_filter=None):
        query = """SELECT p.name, SUM(ii.quantity) AS total_qty, SUM(ii.line_total) AS total_value,
                          SUM(ii.line_total) - SUM(ii.quantity * COALESCE(p.purchase_price,0)) AS estimated_profit
                   FROM invoice_items ii
                   JOIN invoices i ON i.id = ii.invoice_id
                   JOIN products p ON p.id = ii.product_id
                   WHERE i.status='active' AND ii.status='active' AND DATE(i.created_at) BETWEEN %s AND %s"""
        params = [date_from, date_to]
        if name_filter:
            query += " AND p.name LIKE %s"
            params.append(f"%{name_filter}%")
        query += " GROUP BY ii.product_id ORDER BY total_qty DESC LIMIT %s"
        params.append(limit)

        cur = self._cursor()
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()
        return rows

    def search_invoices(self, date_from, date_to, invoice_number=None):
        query = """SELECT i.*, u.full_name AS cashier_name
                   FROM invoices i
                   LEFT JOIN users u ON u.id = i.user_id
                   WHERE DATE(i.created_at) BETWEEN %s AND %s"""
        params = [date_from, date_to]
        if invoice_number:
            query += " AND i.invoice_number LIKE %s"
            params.append(f"%{invoice_number}%")
        query += " ORDER BY i.created_at DESC LIMIT 300"
        cur = self._cursor()
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()
        return rows

    def cancel_invoice(self, invoice_id, user_id, reason=""):
        invoice, items = self.get_invoice_with_items(invoice_id)
        if not invoice:
            raise DatabaseError("الفاتورة غير موجودة")
        if invoice.get("status") == "cancelled":
            raise DatabaseError("الفاتورة ملغاة بالفعل")

        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor()
        try:
            for it in items:
                cur.execute(
                    "UPDATE products SET quantity = quantity + %s WHERE id=%s",
                    (it["quantity"], it["product_id"]),
                )
            cur.execute(
                """UPDATE invoices SET status='cancelled', cancelled_at=NOW(),
                   cancelled_by=%s, cancel_reason=%s WHERE id=%s""",
                (user_id, reason, invoice_id),
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل إلغاء الفاتورة: {e}")

        self.log_activity(
            user_id, "cancel_invoice",
            f"إلغاء الفاتورة رقم {invoice['invoice_number']}" + (f" - السبب: {reason}" if reason else "")
        )

    def list_shift_invoices(self, shift_id):
        cur = self._cursor()
        cur.execute(
            """SELECT i.*, u.full_name AS cashier_name FROM invoices i
               LEFT JOIN users u ON u.id = i.user_id
               WHERE i.shift_id=%s ORDER BY i.created_at DESC""",
            (shift_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def update_invoice_item(self, item_id, new_quantity, new_unit_price, user_id):
        cur = self._cursor()
        cur.execute("SELECT * FROM invoice_items WHERE id=%s", (item_id,))
        item = cur.fetchone()
        cur.close()
        if not item:
            raise DatabaseError("الصنف غير موجود في الفاتورة")
        if item["status"] == "cancelled":
            raise DatabaseError("الصنف ده ملغى بالفعل، مينفعش تعدّل فيه")

        invoice_id = item["invoice_id"]
        qty_diff = round(float(new_quantity) - float(item["quantity"]), 3)
        new_line_total = round(float(new_quantity) * float(new_unit_price), 2)

        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor(dictionary=True)
        try:
            if qty_diff != 0:
                cur.execute(
                    "UPDATE products SET quantity = quantity - %s WHERE id=%s",
                    (qty_diff, item["product_id"]),
                )
            cur.execute(
                "UPDATE invoice_items SET quantity=%s, unit_price=%s, line_total=%s WHERE id=%s",
                (new_quantity, new_unit_price, new_line_total, item_id),
            )

            cur.execute(
                """SELECT sale_type, SUM(line_total) AS total FROM invoice_items
                   WHERE invoice_id=%s AND status='active' GROUP BY sale_type""",
                (invoice_id,),
            )
            totals = {"tamween": 0.0, "free": 0.0, "bread": 0.0, "wholesale": 0.0}
            for row in cur.fetchall():
                totals[row["sale_type"]] = float(row["total"])

            cur.execute("SELECT card_hit_amount, support_tamween, support_bread FROM invoices WHERE id=%s", (invoice_id,))
            row = cur.fetchone()
            card_hit_amount = float(row["card_hit_amount"])
            support_total = float(row["support_tamween"]) + float(row["support_bread"])
            grand_total = round(sum(totals.values()), 2)
            net_total = round(grand_total + card_hit_amount - support_total, 2)

            cur.execute(
                """UPDATE invoices SET total_tamween=%s, total_free=%s, total_bread=%s,
                   total_wholesale=%s, grand_total=%s, net_total=%s WHERE id=%s""",
                (totals["tamween"], totals["free"], totals["bread"], totals["wholesale"],
                 grand_total, net_total, invoice_id),
            )
            self.conn.commit()
            cur.close()
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل تعديل الصنف: {e}")

        self.log_activity(
            user_id, "edit_invoice_item",
            f"تعديل صنف في فاتورة رقم {invoice_id} - الكمية الجديدة {new_quantity}, السعر {new_unit_price:.2f}"
        )

    def cancel_invoice_item(self, item_id, user_id, reason=""):
        cur = self._cursor()
        cur.execute(
            """SELECT ii.*, i.invoice_number FROM invoice_items ii
               JOIN invoices i ON i.id = ii.invoice_id WHERE ii.id=%s""",
            (item_id,),
        )
        item = cur.fetchone()
        cur.close()
        if not item:
            raise DatabaseError("الصنف غير موجود في الفاتورة")
        if item["status"] == "cancelled":
            raise DatabaseError("الصنف ده ملغى بالفعل")

        invoice_id = item["invoice_id"]
        self.ensure_connected()
        self.conn.start_transaction()
        cur = self.conn.cursor(dictionary=True)
        try:
            cur.execute(
                "UPDATE products SET quantity = quantity + %s WHERE id=%s",
                (item["quantity"], item["product_id"]),
            )
            cur.execute("UPDATE invoice_items SET status='cancelled' WHERE id=%s", (item_id,))

            # إعادة حساب إجمالي الفاتورة من الأصناف اللي لسه نشطة بس
            cur.execute(
                """SELECT sale_type, SUM(line_total) AS total FROM invoice_items
                   WHERE invoice_id=%s AND status='active' GROUP BY sale_type""",
                (invoice_id,),
            )
            totals = {"tamween": 0.0, "free": 0.0, "bread": 0.0, "wholesale": 0.0}
            for row in cur.fetchall():
                totals[row["sale_type"]] = float(row["total"])

            cur.execute("SELECT card_hit_amount, support_tamween, support_bread FROM invoices WHERE id=%s", (invoice_id,))
            row = cur.fetchone()
            card_hit_amount = float(row["card_hit_amount"])
            support_total = float(row["support_tamween"]) + float(row["support_bread"])
            grand_total = round(sum(totals.values()), 2)
            net_total = round(grand_total + card_hit_amount - support_total, 2)

            cur.execute(
                """UPDATE invoices SET total_tamween=%s, total_free=%s, total_bread=%s,
                   total_wholesale=%s, grand_total=%s, net_total=%s WHERE id=%s""",
                (totals["tamween"], totals["free"], totals["bread"], totals["wholesale"],
                 grand_total, net_total, invoice_id),
            )

            # لو مفيش أصناف نشطة خالص فضلت في الفاتورة، اعتبرها ملغاة بالكامل
            cur.execute(
                "SELECT COUNT(*) AS c FROM invoice_items WHERE invoice_id=%s AND status='active'",
                (invoice_id,),
            )
            if cur.fetchone()["c"] == 0:
                cur.execute(
                    "UPDATE invoices SET status='cancelled', cancelled_at=NOW(), cancelled_by=%s, cancel_reason=%s WHERE id=%s",
                    (user_id, reason or "كل الأصناف اتلغت", invoice_id),
                )

            self.conn.commit()
            cur.close()
        except MySQLError as e:
            self.conn.rollback()
            cur.close()
            raise DatabaseError(f"فشل إلغاء الصنف: {e}")

        self.log_activity(
            user_id, "cancel_invoice_item",
            f"إلغاء صنف من فاتورة رقم {item['invoice_number']}" + (f" - السبب: {reason}" if reason else "")
        )

    def get_last_invoice_items_for_card(self, ration_card_id):
        """آخر فاتورة نشطة اتباعت لصاحب البطاقة دي، مع كل أصنافها."""
        cur = self._cursor()
        cur.execute(
            """SELECT id FROM invoices WHERE ration_card_id=%s AND status='active'
               ORDER BY created_at DESC LIMIT 1""",
            (ration_card_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None, []

        invoice_id = row["id"]
        cur = self._cursor()
        cur.execute(
            """SELECT ii.*, p.name AS product_name, p.unit
               FROM invoice_items ii
               JOIN products p ON p.id = ii.product_id
               WHERE ii.invoice_id=%s AND ii.status='active'""",
            (invoice_id,),
        )
        items = cur.fetchall()
        cur.close()
        return invoice_id, items

    def get_invoice_with_items(self, invoice_id):
        cur = self._cursor()
        cur.execute("SELECT * FROM invoices WHERE id=%s", (invoice_id,))
        invoice = cur.fetchone()
        cur.execute(
            """SELECT ii.*, p.name AS product_name FROM invoice_items ii
               JOIN products p ON p.id = ii.product_id WHERE ii.invoice_id=%s""",
            (invoice_id,),
        )
        items = cur.fetchall()
        cur.close()
        return invoice, items
