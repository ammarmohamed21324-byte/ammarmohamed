# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDoubleSpinBox,
    QGroupBox, QHeaderView, QLabel, QDialog, QCheckBox, QCompleter
)

from database import DatabaseError
import print_utils


class SuppliersTab(QWidget):
    @staticmethod
    def _balance_text(balance):
        if balance > 0:
            return f"الرصيد المستحق عليه حاليًا: {balance:.2f} ج.م (عليك تدفعله)"
        elif balance < 0:
            return f"الرصيد المستحق عليه حاليًا: {abs(balance):.2f} ج.م (هو مديون لك)"
        return "الرصيد المستحق عليه حاليًا: 0.00 ج.م"

    def __init__(self, db, current_user, can_approve=False):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.can_approve = can_approve
        self.pending_items = []  # عناصر فاتورة الاستلام الجاري تجهيزها
        self.matched_product_id = None
        self.matched_units_per_package = None
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_suppliers()
        self.refresh_invoices()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_invoices)
        self.auto_refresh_timer.timeout.connect(self.refresh_suppliers)
        self.auto_refresh_timer.start(2000)

    # ---------------- الواجهة ----------------
    def _build_ui(self):
        layout = QHBoxLayout(self)

        # ------- العمود الأيمن: الموردين -------
        right_col = QVBoxLayout()
        supplier_box = QGroupBox("الموردين")
        supplier_layout = QVBoxLayout()

        form = QFormLayout()
        self.supplier_name_edit = QLineEdit()
        self.supplier_phone_edit = QLineEdit()
        self.supplier_address_edit = QLineEdit()
        self.supplier_notes_edit = QLineEdit()
        form.addRow("اسم المورد:", self.supplier_name_edit)
        form.addRow("التليفون:", self.supplier_phone_edit)
        form.addRow("العنوان:", self.supplier_address_edit)
        form.addRow("ملاحظات:", self.supplier_notes_edit)
        supplier_layout.addLayout(form)

        add_supplier_btn = QPushButton("إضافة مورد")
        add_supplier_btn.setObjectName("primaryButton")
        add_supplier_btn.clicked.connect(self.add_supplier)
        supplier_layout.addWidget(add_supplier_btn)

        self.suppliers_table = QTableWidget(0, 5)
        self.suppliers_table.setHorizontalHeaderLabels(["الاسم", "التليفون", "الرصيد", "", ""])
        self.suppliers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.suppliers_table.setColumnWidth(3, 140)
        self.suppliers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.suppliers_table.setColumnWidth(4, 140)
        self.suppliers_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        supplier_layout.addWidget(self.suppliers_table)

        supplier_box.setLayout(supplier_layout)
        right_col.addWidget(supplier_box)
        layout.addLayout(right_col, 3)

        # ------- العمود الأوسط: تسجيل استلام بضاعة -------
        center_col = QVBoxLayout()
        receive_box = QGroupBox("تسجيل استلام بضاعة جديدة (هتفضل معلّقة لحد ما الأدمن يراجعها)")
        receive_layout = QVBoxLayout()

        top_form = QFormLayout()
        self.supplier_combo = QComboBox()
        self.reference_edit = QLineEdit()
        self.invoice_notes_edit = QLineEdit()
        self.payment_method_combo = QComboBox()
        self.payment_method_combo.addItem("كاش (اتدفعت فورًا)", "cash")
        self.payment_method_combo.addItem("آجل (على حساب المحل عند المورد)", "credit")
        self.payment_method_combo.currentIndexChanged.connect(self._on_supplier_payment_method_changed)

        self.paid_now_spin = QDoubleSpinBox()
        self.paid_now_spin.setMaximum(999999)
        self.paid_now_spin.setDecimals(2)
        self.paid_now_spin.setEnabled(False)

        top_form.addRow("المورد:", self.supplier_combo)
        top_form.addRow("رقم فاتورة المورد (اختياري):", self.reference_edit)
        top_form.addRow("طريقة الدفع للمورد:", self.payment_method_combo)
        top_form.addRow("المبلغ المدفوع الآن (لو آجل):", self.paid_now_spin)
        top_form.addRow("ملاحظات:", self.invoice_notes_edit)
        receive_layout.addLayout(top_form)

        paid_now_hint = QLabel("اكتب أي مبلغ دفعته للمورد فورًا، والباقي بس هو اللي هيتضاف لرصيدك عليه.")
        paid_now_hint.setWordWrap(True)
        paid_now_hint.setStyleSheet("color: gray; font-size: 11px;")
        receive_layout.addWidget(paid_now_hint)

        item_row = QHBoxLayout()
        self.item_name_edit = QLineEdit()
        self.item_name_edit.setPlaceholderText("اسم الصنف (ابحث عن صنف موجود أو اكتب اسم صنف جديد)")
        self.item_name_edit.textChanged.connect(self.on_item_name_changed)
        self._setup_item_name_completer()

        self.item_qty_spin = QDoubleSpinBox()
        self.item_qty_spin.setDecimals(2)
        self.item_qty_spin.setMaximum(999999)
        self.item_qty_spin.setValue(1)
        self.item_qty_spin.setPrefix("الكمية: ")

        self.item_cost_spin = QDoubleSpinBox()
        self.item_cost_spin.setDecimals(2)
        self.item_cost_spin.setMaximum(999999)
        self.item_cost_spin.setPrefix("سعر الشراء: ")

        add_item_btn = QPushButton("+ إضافة للفاتورة")
        add_item_btn.clicked.connect(self.add_item_to_pending)

        item_row.addWidget(self.item_name_edit, 3)
        item_row.addWidget(self.item_qty_spin, 1)
        item_row.addWidget(self.item_cost_spin, 1)
        item_row.addWidget(add_item_btn, 1)
        receive_layout.addLayout(item_row)

        self.package_qty_check = QCheckBox("الكمية دي بالوحدة الكبيرة (هيتحول لعدد القطع تلقائي عند الاعتماد)")
        self.package_qty_check.setVisible(False)
        receive_layout.addWidget(self.package_qty_check)

        prices_row = QHBoxLayout()
        prices_row.addWidget(QLabel("لو صنف جديد، أسعار البيع الأربعة (اختياري):"))
        self.item_price_tamween_spin = QDoubleSpinBox()
        self.item_price_tamween_spin.setMaximum(999999)
        self.item_price_tamween_spin.setPrefix("تموين ")
        self.item_price_free_spin = QDoubleSpinBox()
        self.item_price_free_spin.setMaximum(999999)
        self.item_price_free_spin.setPrefix("حر ")
        self.item_price_bread_spin = QDoubleSpinBox()
        self.item_price_bread_spin.setMaximum(999999)
        self.item_price_bread_spin.setPrefix("عيش ")
        self.item_price_wholesale_spin = QDoubleSpinBox()
        self.item_price_wholesale_spin.setMaximum(999999)
        self.item_price_wholesale_spin.setPrefix("جملة ")
        prices_row.addWidget(self.item_price_tamween_spin)
        prices_row.addWidget(self.item_price_free_spin)
        prices_row.addWidget(self.item_price_bread_spin)
        prices_row.addWidget(self.item_price_wholesale_spin)
        receive_layout.addLayout(prices_row)

        self.update_prices_check = QCheckBox("الصنف ده موجود بالفعل، حدّث أسعار البيع بتاعته بالأرقام دي")
        self.update_prices_check.setVisible(False)
        receive_layout.addWidget(self.update_prices_check)

        hint_label = QLabel("الترتيب: اسم الصنف — الكمية المستلمة — سعر التكلفة (اختياري)")
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        receive_layout.addWidget(hint_label)

        self.pending_table = QTableWidget(0, 4)
        self.pending_table.setHorizontalHeaderLabels(["الصنف", "الكمية", "التكلفة", "مرتبط بصنف؟"])
        self.pending_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        receive_layout.addWidget(self.pending_table)

        remove_item_btn = QPushButton("حذف السطر المحدد")
        remove_item_btn.clicked.connect(self.remove_pending_item)
        receive_layout.addWidget(remove_item_btn)

        save_invoice_btn = QPushButton("حفظ فاتورة الاستلام (معلّقة)")
        save_invoice_btn.setObjectName("primaryButton")
        save_invoice_btn.clicked.connect(self.save_supplier_invoice)
        receive_layout.addWidget(save_invoice_btn)

        receive_box.setLayout(receive_layout)
        center_col.addWidget(receive_box)
        layout.addLayout(center_col, 2)

        # ------- العمود الأيسر: الفواتير المعلّقة -------
        left_col = QVBoxLayout()
        pending_box = QGroupBox("فواتير الاستلام")
        pending_layout = QVBoxLayout()

        refresh_btn = QPushButton("تحديث القائمة")
        refresh_btn.clicked.connect(self.refresh_invoices)
        pending_layout.addWidget(refresh_btn)

        self.invoices_table = QTableWidget(0, 5)
        self.invoices_table.setHorizontalHeaderLabels(["المورد", "التاريخ", "عدد الأصناف", "الحالة", ""])
        self.invoices_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.invoices_table.setColumnWidth(4, 170)
        self.invoices_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        pending_layout.addWidget(self.invoices_table)

        pending_box.setLayout(pending_layout)
        left_col.addWidget(pending_box)
        layout.addLayout(left_col, 2)

    # ---------------- الموردين ----------------
    def _on_supplier_payment_method_changed(self):
        is_credit = self.payment_method_combo.currentData() == "credit"
        self.paid_now_spin.setEnabled(is_credit)
        if not is_credit:
            self.paid_now_spin.setValue(0)

    def _setup_item_name_completer(self):
        try:
            products = self.db.list_products()
        except DatabaseError:
            products = []
        names = [p["name"] for p in products]
        completer = QCompleter(names, self.item_name_edit)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.item_name_edit.setCompleter(completer)

    def refresh_suppliers(self):
        try:
            suppliers = self.db.list_suppliers_with_balance()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.suppliers_table.setRowCount(len(suppliers))
        self.supplier_combo.clear()
        for row, s in enumerate(suppliers):
            self.suppliers_table.setItem(row, 0, QTableWidgetItem(s["name"]))
            self.suppliers_table.setItem(row, 1, QTableWidgetItem(s["phone"] or ""))
            if s["balance"] > 0:
                balance_item = QTableWidgetItem(f"{s['balance']:.2f} ج.م (عليك تدفعله)")
                balance_item.setForeground(Qt.red)
            elif s["balance"] < 0:
                balance_item = QTableWidgetItem(f"{abs(s['balance']):.2f} ج.م (هو مديون لك)")
                balance_item.setForeground(Qt.darkGreen)
            else:
                balance_item = QTableWidgetItem("0.00 ج.م")
            self.suppliers_table.setItem(row, 2, balance_item)

            if self.can_approve:
                pay_btn = QPushButton("دفعة للمورد")
                pay_btn.clicked.connect(lambda _, sid=s["id"], name=s["name"]: self.record_supplier_payment(sid, name))
                self.suppliers_table.setCellWidget(row, 3, pay_btn)

            statement_btn = QPushButton("كشف حساب")
            statement_btn.clicked.connect(lambda _, sid=s["id"], name=s["name"]: self.show_supplier_statement(sid, name))
            self.suppliers_table.setCellWidget(row, 4, statement_btn)

            self.supplier_combo.addItem(s["name"], s["id"])
        self.suppliers_table.resizeRowsToContents()

    def record_supplier_payment(self, supplier_id, name):
        try:
            balance = self.db.supplier_balance(supplier_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"دفعة لمورد: {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)
        form.addRow(QLabel(self._balance_text(balance)))

        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(999999)
        amount_spin.setDecimals(2)
        amount_spin.setValue(balance if balance > 0 else 0)
        notes_edit = QLineEdit()
        form.addRow("المبلغ المدفوع:", amount_spin)
        form.addRow("ملاحظات (اختياري):", notes_edit)

        confirm_btn = QPushButton("تسجيل الدفعة")
        confirm_btn.setObjectName("primaryButton")
        form.addRow(confirm_btn)

        def do_pay():
            if amount_spin.value() <= 0:
                QMessageBox.warning(dialog, "تنبيه", "المبلغ لازم يكون أكبر من صفر")
                return
            try:
                self.db.record_supplier_payment(
                    supplier_id, amount_spin.value(), self.current_user["id"], notes_edit.text().strip()
                )
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل الدفعة بنجاح")
            dialog.accept()
            self.refresh_suppliers()

        confirm_btn.clicked.connect(do_pay)
        dialog.exec_()

    def show_supplier_statement(self, supplier_id, name):
        try:
            invoices = self.db.list_supplier_credit_invoices(supplier_id)
            payments = self.db.list_supplier_payments(supplier_id)
            balance = self.db.supplier_balance(supplier_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"كشف حساب مورد: {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(550, 480)
        layout = QVBoxLayout(dialog)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)

        content_layout.addWidget(QLabel(f"كشف حساب مورد: {name}"))
        content_layout.addWidget(QLabel(self._balance_text(balance)))

        content_layout.addWidget(QLabel("فواتير الاستلام بالآجل:"))
        inv_table = QTableWidget(len(invoices), 3)
        inv_table.setHorizontalHeaderLabels(["رقم الفاتورة", "التاريخ", "التكلفة"])
        inv_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for row, inv in enumerate(invoices):
            inv_table.setItem(row, 0, QTableWidgetItem(inv.get("reference_number") or f"#{inv['id']}"))
            inv_table.setItem(row, 1, QTableWidgetItem(str(inv["created_at"])))
            inv_table.setItem(row, 2, QTableWidgetItem(f"{inv['total_cost']:.2f}"))
        content_layout.addWidget(inv_table)

        content_layout.addWidget(QLabel("سجل الدفعات:"))
        pay_table = QTableWidget(len(payments), 3)
        pay_table.setHorizontalHeaderLabels(["التاريخ", "المبلغ", "دفعها"])
        pay_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, p in enumerate(payments):
            pay_table.setItem(row, 0, QTableWidgetItem(str(p["paid_at"])))
            pay_table.setItem(row, 1, QTableWidgetItem(f"{float(p['amount']):.2f}"))
            pay_table.setItem(row, 2, QTableWidgetItem(p.get("paid_by_name") or "-"))
        content_layout.addWidget(pay_table)

        layout.addWidget(content_widget)
        print_row = QHBoxLayout()

        def build_html():
            inv_rows = [
                [inv.get("reference_number") or f"#{inv['id']}", str(inv["created_at"]), f"{inv['total_cost']:.2f}"]
                for inv in invoices
            ]
            pay_rows = [
                [str(p["paid_at"]), f"{float(p['amount']):.2f}", p.get("paid_by_name") or "-"]
                for p in payments
            ]
            return print_utils.build_report_html(
                f"كشف حساب مورد: {name}",
                meta_lines=[self._balance_text(balance)],
                sections=[
                    {"heading": "فواتير الاستلام بالآجل",
                     "headers": ["رقم الفاتورة", "التاريخ", "التكلفة"], "rows": inv_rows},
                    {"heading": "سجل الدفعات",
                     "headers": ["التاريخ", "المبلغ", "دفعها"], "rows": pay_rows},
                ],
            )

        print_utils.add_html_print_button(print_row, build_html, dialog)
        layout.addLayout(print_row)

        dialog.exec_()

    def add_supplier(self):
        name = self.supplier_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "اسم المورد مطلوب")
            return
        data = {
            "name": name,
            "phone": self.supplier_phone_edit.text().strip(),
            "address": self.supplier_address_edit.text().strip(),
            "notes": self.supplier_notes_edit.text().strip(),
        }
        try:
            self.db.add_supplier(data)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        QMessageBox.information(self, "تم", "تم إضافة المورد بنجاح")
        self.supplier_name_edit.clear()
        self.supplier_phone_edit.clear()
        self.supplier_address_edit.clear()
        self.supplier_notes_edit.clear()
        self.refresh_suppliers()

    # ---------------- بناء فاتورة الاستلام ----------------
    def on_item_name_changed(self, text):
        """يحاول يلاقي صنف موجود بنفس الاسم عشان يربطه أوتوماتيك."""
        self.matched_product_id = None
        self.matched_units_per_package = None
        self.package_qty_check.setVisible(False)
        self.package_qty_check.setChecked(False)
        self.update_prices_check.setVisible(False)
        self.update_prices_check.setChecked(False)
        text = text.strip()
        if not text:
            return
        try:
            results = self.db.search_products(text)
        except DatabaseError:
            return
        for p in results:
            if p["name"].strip() == text:
                self.matched_product_id = p["id"]
                if p.get("units_per_package"):
                    self.matched_units_per_package = int(p["units_per_package"])
                    self.package_qty_check.setText(
                        f"الكمية دي بالوحدة الكبيرة ({p['unit']}) - كل وحدة فيها {self.matched_units_per_package} قطعة، "
                        "وهيتحول لعدد القطع تلقائي عند الاعتماد"
                    )
                    self.package_qty_check.setVisible(True)

                # الصنف موجود بالفعل - نعرض أسعاره الحالية ونديله فرصة يعدلها
                self.item_price_tamween_spin.setValue(float(p.get("price_tamween") or 0))
                self.item_price_free_spin.setValue(float(p.get("price_free") or 0))
                self.item_price_bread_spin.setValue(float(p.get("price_bread") or 0))
                self.item_price_wholesale_spin.setValue(float(p.get("price_wholesale") or 0))
                self.update_prices_check.setVisible(True)
                break

    def add_item_to_pending(self):
        name = self.item_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "اكتب اسم الصنف الأول")
            return
        qty = self.item_qty_spin.value()
        if qty <= 0:
            QMessageBox.warning(self, "تنبيه", "الكمية لازم تكون أكبر من صفر")
            return

        self.pending_items.append({
            "item_name": name,
            "quantity": qty,
            "cost_price": self.item_cost_spin.value() or None,
            "product_id": self.matched_product_id,
            "price_tamween": self.item_price_tamween_spin.value(),
            "price_free": self.item_price_free_spin.value(),
            "price_bread": self.item_price_bread_spin.value(),
            "price_wholesale": self.item_price_wholesale_spin.value(),
            "is_package_quantity": self.package_qty_check.isChecked(),
            "update_prices": self.update_prices_check.isChecked(),
        })
        self.refresh_pending_table()
        self.item_name_edit.clear()
        self.item_qty_spin.setValue(1)
        self.item_cost_spin.setValue(0)
        self.package_qty_check.setChecked(False)
        self.package_qty_check.setVisible(False)
        self.update_prices_check.setChecked(False)
        self.update_prices_check.setVisible(False)
        self.item_price_tamween_spin.setValue(0)
        self.item_price_free_spin.setValue(0)
        self.item_price_bread_spin.setValue(0)
        self.item_price_wholesale_spin.setValue(0)
        self.matched_product_id = None

    def refresh_pending_table(self):
        self.pending_table.setRowCount(len(self.pending_items))
        for row, it in enumerate(self.pending_items):
            tags = []
            if it.get("is_package_quantity"):
                tags.append("بالكرتونة")
            if it.get("update_prices"):
                tags.append("تحديث الأسعار")
            name_display = it["item_name"] + (f" ({' - '.join(tags)})" if tags else "")
            self.pending_table.setItem(row, 0, QTableWidgetItem(name_display))
            self.pending_table.setItem(row, 1, QTableWidgetItem(f"{it['quantity']:g}"))
            self.pending_table.setItem(row, 2, QTableWidgetItem(f"{it['cost_price']:.2f}" if it["cost_price"] else "-"))
            linked_item = QTableWidgetItem("نعم" if it["product_id"] else "لا (صنف جديد)")
            if not it["product_id"]:
                linked_item.setForeground(Qt.darkYellow)
            self.pending_table.setItem(row, 3, linked_item)

    def remove_pending_item(self):
        row = self.pending_table.currentRow()
        if row >= 0:
            del self.pending_items[row]
            self.refresh_pending_table()

    def save_supplier_invoice(self):
        if self.supplier_combo.count() == 0:
            QMessageBox.warning(self, "تنبيه", "ضيف مورد الأول من العمود اللي على اليمين")
            return
        if not self.pending_items:
            QMessageBox.warning(self, "تنبيه", "ضيف صنف واحد على الأقل للفاتورة")
            return

        supplier_id = self.supplier_combo.currentData()
        payment_method = self.payment_method_combo.currentData()
        paid_now = self.paid_now_spin.value()
        try:
            invoice_id = self.db.create_supplier_invoice(
                supplier_id, self.current_user["id"],
                self.reference_edit.text().strip(),
                self.invoice_notes_edit.text().strip(),
                self.pending_items,
                payment_method=payment_method,
            )
            if payment_method == "credit" and paid_now > 0:
                self.db.record_supplier_payment(
                    supplier_id, paid_now, self.current_user["id"],
                    f"دفعة مبدئية وقت تسجيل فاتورة رقم {invoice_id}"
                )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(
            self, "تم الحفظ",
            "تم حفظ فاتورة الاستلام كـ \"معلّقة\". الأدمن هيراجعها ويعتمدها عشان الكميات تتضاف فعليًا للمخزون."
        )
        self.pending_items = []
        self.refresh_pending_table()
        self.reference_edit.clear()
        self.invoice_notes_edit.clear()
        self.paid_now_spin.setValue(0)
        self.refresh_invoices()
        self.refresh_suppliers()

    # ---------------- فواتير الاستلام ----------------
    def refresh_invoices(self):
        try:
            invoices = self.db.list_supplier_invoices()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.invoices_table.setRowCount(len(invoices))
        for row, inv in enumerate(invoices):
            self.invoices_table.setItem(row, 0, QTableWidgetItem(inv["supplier_name"] or "-"))
            self.invoices_table.setItem(row, 1, QTableWidgetItem(str(inv["created_at"])))
            self.invoices_table.setItem(row, 2, QTableWidgetItem(str(inv["item_count"])))
            status_item = QTableWidgetItem("معلّقة" if inv["status"] == "pending" else "معتمدة")
            status_item.setForeground(Qt.darkYellow if inv["status"] == "pending" else Qt.darkGreen)
            self.invoices_table.setItem(row, 3, status_item)

            if inv["status"] == "pending" and not self.can_approve:
                waiting_label = QLabel("بانتظار مراجعة الأدمن")
                waiting_label.setStyleSheet("color: gray; font-size: 11px;")
                self.invoices_table.setCellWidget(row, 4, waiting_label)
            else:
                review_btn = QPushButton("مراجعة واعتماد" if inv["status"] == "pending" else "عرض")
                review_btn.clicked.connect(lambda _, inv_id=inv["id"]: self.open_review_dialog(inv_id))
                self.invoices_table.setCellWidget(row, 4, review_btn)

        self.invoices_table.resizeRowsToContents()

    def open_review_dialog(self, invoice_id):
        try:
            invoice = self.db.get_supplier_invoice(invoice_id)
            items = self.db.get_supplier_invoice_items(invoice_id)
            products = self.db.list_products()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("مراجعة فاتورة الاستلام")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(600, 450)
        layout = QVBoxLayout(dialog)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)

        payment_labels = {"cash": "كاش", "credit": "آجل"}
        header_label = QLabel(
            f"المورد: {invoice.get('supplier_name') or '-'}\n"
            f"رقم فاتورة المورد: {invoice.get('reference_number') or '-'}\n"
            f"التاريخ: {invoice.get('created_at')}\n"
            f"بواسطة: {invoice.get('created_by_name') or '-'}\n"
            f"طريقة الدفع: {payment_labels.get(invoice.get('payment_method'), '-')}\n"
            f"الحالة: {'معتمدة' if invoice.get('status') == 'approved' else 'معلّقة'}"
        )
        content_layout.addWidget(header_label)

        table = QTableWidget(len(items), 4)
        table.setHorizontalHeaderLabels(["الصنف", "الكمية", "التكلفة", "اربطه بصنف في المخزون"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setColumnWidth(3, 220)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        content_layout.addWidget(table)

        combos = {}
        create_btns = {}
        for row, it in enumerate(items):
            table.setItem(row, 0, QTableWidgetItem(it["item_name"]))
            table.setItem(row, 1, QTableWidgetItem(f"{float(it['quantity']):g}"))
            table.setItem(row, 2, QTableWidgetItem(f"{float(it['cost_price']):.2f}" if it["cost_price"] else "-"))

            if self.can_approve:
                if it["product_id"]:
                    combo = QComboBox()
                    combo.addItem("— اختر صنف —", None)
                    for p in products:
                        combo.addItem(p["name"], p["id"])
                    idx = combo.findData(it["product_id"])
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                    combos[it["id"]] = combo
                    table.setCellWidget(row, 3, combo)
                else:
                    cell_widget = QWidget()
                    cell_layout = QHBoxLayout(cell_widget)
                    cell_layout.setContentsMargins(2, 2, 2, 2)
                    combo = QComboBox()
                    combo.addItem("— اربطه بصنف موجود —", None)
                    for p in products:
                        combo.addItem(p["name"], p["id"])
                    combos[it["id"]] = combo
                    create_btn = QPushButton("إنشاء صنف جديد بأسعاره")
                    create_btn.clicked.connect(
                        lambda _, item_id=it["id"]: self._create_product_from_item(item_id, table)
                    )
                    cell_layout.addWidget(combo)
                    cell_layout.addWidget(create_btn)
                    table.setCellWidget(row, 3, cell_widget)
            else:
                table.setItem(row, 3, QTableWidgetItem(it.get("matched_product_name") or "لسه مش مربوط"))

        table.resizeRowsToContents()
        layout.addWidget(content_widget)

        if self.can_approve:
            def build_html():
                rows = [
                    [it["item_name"], f"{float(it['quantity']):g}",
                     f"{float(it['cost_price']):.2f}" if it["cost_price"] else "-"]
                    for it in items
                ]
                total_cost = sum(
                    float(it["quantity"]) * float(it["cost_price"] or 0) for it in items
                )
                return print_utils.build_report_html(
                    "فاتورة استلام بضاعة",
                    meta_lines=[
                        f"المورد: {invoice.get('supplier_name') or '-'}",
                        f"رقم فاتورة المورد: {invoice.get('reference_number') or '-'}",
                        f"التاريخ: {invoice.get('created_at')}",
                        f"بواسطة: {invoice.get('created_by_name') or '-'}",
                        f"طريقة الدفع: {payment_labels.get(invoice.get('payment_method'), '-')}",
                        f"الحالة: {'معتمدة' if invoice.get('status') == 'approved' else 'معلّقة'}",
                    ],
                    sections=[{"headers": ["الصنف", "الكمية", "التكلفة"], "rows": rows}],
                    footer_lines=[f"إجمالي تكلفة الفاتورة: {total_cost:.2f} ج.م"],
                )

            print_row = QHBoxLayout()
            print_utils.add_html_print_button(print_row, build_html, dialog, label="🖶 طباعة فاتورة الاستلام")
            layout.addLayout(print_row)

        if not self.can_approve:
            info_label = QLabel("شاشة عرض بس — المراجعة والاعتماد بيد الأدمن فقط.")
            info_label.setStyleSheet("color: gray;")
            layout.addWidget(info_label)
            close_btn = QPushButton("إغلاق")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            dialog.exec_()
            self.refresh_invoices()
            return

        note_label = QLabel(
            "لو الصنف جديد وملوش صنف مطابق، روح لتبويب \"المخزون والأصناف\" واعمله الأول، "
            "وبعدين ارجع هنا واربطه من القائمة."
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: #a15c00;")
        layout.addWidget(note_label)

        btn_row = QHBoxLayout()
        save_links_btn = QPushButton("حفظ الربط")
        save_links_btn.clicked.connect(lambda: self._save_item_links(combos))
        approve_btn = QPushButton("اعتماد وإضافة للمخزون")
        approve_btn.setObjectName("primaryButton")
        approve_btn.clicked.connect(lambda: self._approve_invoice(invoice_id, combos, dialog))
        btn_row.addWidget(save_links_btn)
        btn_row.addWidget(approve_btn)
        layout.addLayout(btn_row)

        dialog.exec_()
        self.refresh_invoices()

    def _create_product_from_item(self, item_id, table):
        confirm = QMessageBox.question(
            self, "تأكيد", "هيتعمل صنف جديد بنفس الاسم والأسعار اللي كتبتها وقت التسجيل. متأكد؟"
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.create_product_from_invoice_item(item_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        QMessageBox.information(self, "تم", "تم إنشاء الصنف وربطه بالفاتورة بنجاح")
        table.window().close()
        self.refresh_invoices()

    def _save_item_links(self, combos):
        try:
            for item_id, combo in combos.items():
                product_id = combo.currentData()
                if product_id:
                    self.db.link_invoice_item_product(item_id, product_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        QMessageBox.information(self, "تم", "تم حفظ الربط. تقدر تدوس اعتماد دلوقتي لو كل الأصناف مربوطة.")

    def _approve_invoice(self, invoice_id, combos, dialog):
        self._save_item_links(combos)
        try:
            self.db.approve_supplier_invoice(invoice_id, self.current_user["id"])
        except DatabaseError as e:
            QMessageBox.critical(dialog, "تنبيه", str(e))
            return
        QMessageBox.information(dialog, "تم الاعتماد", "تم اعتماد الفاتورة وإضافة الكميات للمخزون بنجاح")
        dialog.accept()
