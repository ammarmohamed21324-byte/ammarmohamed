# -*- coding: utf-8 -*-
import datetime
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QDoubleSpinBox, QGroupBox,
    QHeaderView, QLabel, QDialog, QSpinBox
)

from database import DatabaseError
import print_utils


class CustomersTab(QWidget):
    def __init__(self, db, current_user):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_table()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_table)
        self.auto_refresh_timer.start(2000)

    def _build_ui(self):
        layout = QHBoxLayout(self)

        right_col = QVBoxLayout()
        form_box = QGroupBox("إضافة عميل آجل")
        form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.notes_edit = QLineEdit()
        form_layout.addRow("اسم العميل:", self.name_edit)
        form_layout.addRow("التليفون:", self.phone_edit)
        form_layout.addRow("العنوان:", self.address_edit)
        form_layout.addRow("ملاحظات:", self.notes_edit)

        add_btn = QPushButton("إضافة عميل")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self.add_customer)

        form_container = QVBoxLayout()
        form_container.addLayout(form_layout)
        form_container.addWidget(add_btn)
        form_box.setLayout(form_container)
        right_col.addWidget(form_box)
        right_col.addStretch()
        layout.addLayout(right_col, 1)

        left_col = QVBoxLayout()
        list_box = QGroupBox("العملاء وأرصدتهم")
        list_layout = QVBoxLayout()

        refresh_btn = QPushButton("تحديث القائمة")
        refresh_btn.clicked.connect(self.refresh_table)
        list_layout.addWidget(refresh_btn)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["الاسم", "التليفون", "الرصيد المستحق", "", "", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(3, 130)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 130)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 100)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        list_layout.addWidget(self.table)

        list_box.setLayout(list_layout)
        left_col.addWidget(list_box)
        layout.addLayout(left_col, 2)

    def refresh_table(self):
        try:
            customers = self.db.list_customers_with_balance()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.table.setRowCount(len(customers))
        for row, c in enumerate(customers):
            self.table.setItem(row, 0, QTableWidgetItem(c["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(c["phone"] or ""))
            balance_item = QTableWidgetItem(f"{c['balance']:.2f} ج.م")
            if c["balance"] > 0:
                balance_item.setForeground(Qt.red)
            self.table.setItem(row, 2, balance_item)

            pay_btn = QPushButton("تحصيل دفعة")
            pay_btn.clicked.connect(lambda _, cid=c["id"], name=c["name"]: self.record_payment(cid, name))
            self.table.setCellWidget(row, 3, pay_btn)

            history_btn = QPushButton("كشف الحساب")
            history_btn.clicked.connect(lambda _, cid=c["id"], name=c["name"]: self.show_statement(cid, name))
            self.table.setCellWidget(row, 4, history_btn)

            edit_btn = QPushButton("تعديل")
            edit_btn.clicked.connect(lambda _, cid=c["id"]: self.edit_customer(cid))
            self.table.setCellWidget(row, 5, edit_btn)

        self.table.resizeRowsToContents()

    def edit_customer(self, customer_id):
        try:
            c = self.db.get_customer(customer_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        if not c:
            QMessageBox.warning(self, "تنبيه", "لم يتم العثور على العميل")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"تعديل بيانات العميل — {c['name']}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(350, 220)
        form = QFormLayout(dialog)

        name_edit = QLineEdit(c["name"] or "")
        phone_edit = QLineEdit(c["phone"] or "")
        address_edit = QLineEdit(c["address"] or "")
        notes_edit = QLineEdit(c["notes"] or "")

        form.addRow("اسم العميل:", name_edit)
        form.addRow("التليفون:", phone_edit)
        form.addRow("العنوان:", address_edit)
        form.addRow("ملاحظات:", notes_edit)

        save_btn = QPushButton("حفظ التعديلات")
        save_btn.setObjectName("primaryButton")
        form.addRow(save_btn)

        def do_save():
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(dialog, "تنبيه", "اسم العميل مطلوب")
                return
            data = {
                "name": name,
                "phone": phone_edit.text().strip(),
                "address": address_edit.text().strip(),
                "notes": notes_edit.text().strip(),
            }
            try:
                self.db.update_customer(customer_id, data)
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تعديل بيانات العميل بنجاح")
            dialog.accept()
            self.refresh_table()

        save_btn.clicked.connect(do_save)
        dialog.exec_()

    def add_customer(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "اسم العميل مطلوب")
            return
        data = {
            "name": name,
            "phone": self.phone_edit.text().strip(),
            "address": self.address_edit.text().strip(),
            "notes": self.notes_edit.text().strip(),
        }
        try:
            self.db.add_customer(data)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        QMessageBox.information(self, "تم", "تم إضافة العميل بنجاح")
        self.name_edit.clear()
        self.phone_edit.clear()
        self.address_edit.clear()
        self.notes_edit.clear()
        self.refresh_table()

    def record_payment(self, customer_id, name):
        try:
            balance = self.db.customer_balance(customer_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"تحصيل دفعة من {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)

        balance_label = QLabel(f"الرصيد المستحق حاليًا: {balance:.2f} ج.م")
        form.addRow(balance_label)

        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(999999)
        amount_spin.setDecimals(2)
        amount_spin.setValue(balance if balance > 0 else 0)
        notes_edit = QLineEdit()
        form.addRow("المبلغ المحصّل:", amount_spin)
        form.addRow("ملاحظات (اختياري):", notes_edit)

        confirm_btn = QPushButton("تسجيل التحصيل")
        confirm_btn.setObjectName("primaryButton")
        form.addRow(confirm_btn)

        def do_pay():
            if amount_spin.value() <= 0:
                QMessageBox.warning(dialog, "تنبيه", "المبلغ لازم يكون أكبر من صفر")
                return
            try:
                self.db.record_customer_payment(
                    customer_id, amount_spin.value(), self.current_user["id"], notes_edit.text().strip()
                )
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل التحصيل بنجاح")
            dialog.accept()
            self.refresh_table()

        confirm_btn.clicked.connect(do_pay)
        dialog.exec_()

    def show_statement(self, customer_id, name):
        self._current_statement_customer = (customer_id, name)
        self._render_statement(customer_id, name, datetime.date.today().year)

    def _render_statement(self, customer_id, name, year, existing_dialog=None):
        try:
            invoices = self.db.list_customer_credit_invoices(customer_id, year)
            payments = self.db.list_customer_payments(customer_id, year)
            balance = self.db.customer_balance(customer_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        if existing_dialog:
            existing_dialog.close()

        dialog = QDialog(self)
        dialog.setWindowTitle(f"كشف حساب سنوي {year} — {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(600, 520)
        layout = QVBoxLayout(dialog)

        year_row = QHBoxLayout()
        year_row.addWidget(QLabel("السنة:"))
        year_spin = QSpinBox()
        year_spin.setRange(2020, 2100)
        year_spin.setValue(year)
        year_row.addWidget(year_spin)
        refresh_year_btn = QPushButton("عرض")
        refresh_year_btn.clicked.connect(
            lambda: self._render_statement(customer_id, name, year_spin.value(), dialog)
        )
        year_row.addWidget(refresh_year_btn)
        year_row.addStretch()
        layout.addLayout(year_row)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)

        content_layout.addWidget(QLabel(f"كشف حساب سنوي — {name} — سنة {year}"))
        content_layout.addWidget(QLabel(f"الرصيد المستحق حاليًا (كل السنوات): {balance:.2f} ج.م"))

        year_total = sum(float(inv["net_total"] if inv["net_total"] is not None else inv["grand_total"]) for inv in invoices)
        content_layout.addWidget(QLabel(f"إجمالي مشتريات آجلة في {year}: {year_total:.2f} ج.م ({len(invoices)} فاتورة)"))

        content_layout.addWidget(QLabel("الفواتير الآجلة خلال السنة:"))
        inv_table = QTableWidget(len(invoices), 3)
        inv_table.setHorizontalHeaderLabels(["رقم الفاتورة", "التاريخ", "المبلغ"])
        inv_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for row, inv in enumerate(invoices):
            inv_table.setItem(row, 0, QTableWidgetItem(inv["invoice_number"]))
            inv_table.setItem(row, 1, QTableWidgetItem(str(inv["created_at"])))
            net = inv["net_total"] if inv["net_total"] is not None else inv["grand_total"]
            inv_table.setItem(row, 2, QTableWidgetItem(f"{float(net):.2f}"))
        content_layout.addWidget(inv_table)

        content_layout.addWidget(QLabel("سجل التحصيلات خلال السنة:"))
        pay_table = QTableWidget(len(payments), 3)
        pay_table.setHorizontalHeaderLabels(["التاريخ", "المبلغ", "استلمها"])
        pay_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, p in enumerate(payments):
            pay_table.setItem(row, 0, QTableWidgetItem(str(p["paid_at"])))
            pay_table.setItem(row, 1, QTableWidgetItem(f"{float(p['amount']):.2f}"))
            pay_table.setItem(row, 2, QTableWidgetItem(p.get("received_by_name") or "-"))
        content_layout.addWidget(pay_table)

        layout.addWidget(content_widget)
        print_row = QHBoxLayout()

        def build_html():
            inv_rows = [
                [inv["invoice_number"], str(inv["created_at"]),
                 f"{float(inv['net_total'] if inv['net_total'] is not None else inv['grand_total']):.2f}"]
                for inv in invoices
            ]
            pay_rows = [
                [str(p["paid_at"]), f"{float(p['amount']):.2f}", p.get("received_by_name") or "-"]
                for p in payments
            ]
            return print_utils.build_report_html(
                f"كشف حساب سنوي — {name} — سنة {year}",
                meta_lines=[
                    f"الرصيد المستحق حاليًا (كل السنوات): {balance:.2f} ج.م",
                    f"إجمالي مشتريات آجلة في {year}: {year_total:.2f} ج.م ({len(invoices)} فاتورة)",
                ],
                sections=[
                    {"heading": "الفواتير الآجلة خلال السنة",
                     "headers": ["رقم الفاتورة", "التاريخ", "المبلغ"], "rows": inv_rows},
                    {"heading": "سجل التحصيلات خلال السنة",
                     "headers": ["التاريخ", "المبلغ", "استلمها"], "rows": pay_rows},
                ],
            )

        print_utils.add_html_print_button(print_row, build_html, dialog)
        layout.addLayout(print_row)

        dialog.exec_()
