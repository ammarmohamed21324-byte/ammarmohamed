# -*- coding: utf-8 -*-
import json
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDoubleSpinBox,
    QGroupBox, QHeaderView, QListWidget, QListWidgetItem, QShortcut,
    QDialog, QInputDialog, QFormLayout, QScrollArea
)

import config
import printer
import print_utils
from database import DatabaseError


class PosTab(QWidget):
    def __init__(self, db, current_user, can_cancel=False):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.can_cancel = can_cancel
        self.cart = []  # كل عنصر: dict(product_id, name, sale_type, quantity, unit_price)
        self.active_ration_card = None
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()

    # ---------------- واجهة ----------------
    def _build_ui(self):
        main_layout = QHBoxLayout()

        # --------- العمود الأيمن: إدخال الصنف والبطاقة ---------
        right_col = QVBoxLayout()

        barcode_box = QGroupBox("بحث / مسح باركود (F1)")
        barcode_layout = QVBoxLayout()
        self.barcode_edit = QLineEdit()
        self.barcode_edit.setPlaceholderText("امسح الباركود أو اكتب اسم الصنف")
        self.barcode_edit.returnPressed.connect(self.on_barcode_enter)
        self.barcode_edit.textChanged.connect(self.on_search_text_changed)
        self.barcode_edit.installEventFilter(self)
        barcode_layout.addWidget(self.barcode_edit)

        self.search_results_list = QListWidget()
        self.search_results_list.setMinimumHeight(220)
        self.search_results_list.setMaximumHeight(260)
        self.search_results_list.itemActivated.connect(self.on_search_item_selected)
        barcode_layout.addWidget(self.search_results_list)

        self.stock_label = QLabel("الكمية المتاحة بالمخزون: -")
        self.stock_label.setStyleSheet("color: #4A5A6B; font-weight: 600;")
        barcode_layout.addWidget(self.stock_label)

        barcode_box.setLayout(barcode_layout)
        right_col.addWidget(barcode_box)

        card_box = QGroupBox("بطاقة التموين (اختياري)")
        card_layout = QVBoxLayout()
        card_row = QHBoxLayout()
        self.card_edit = QLineEdit()
        self.card_edit.setPlaceholderText("رقم البطاقة أو امسح باركود البطاقة")
        self.card_edit.returnPressed.connect(self.attach_ration_card)
        attach_btn = QPushButton("ربط البطاقة بالفاتورة")
        attach_btn.clicked.connect(self.attach_ration_card)
        card_row.addWidget(self.card_edit)
        card_row.addWidget(attach_btn)
        card_layout.addLayout(card_row)
        self.card_status_label = QLabel("لا توجد بطاقة مرتبطة بهذه الفاتورة")
        self.card_status_label.setStyleSheet("color: gray;")
        card_layout.addWidget(self.card_status_label)

        # عدد الأفراد (خاصية دايمة على البطاقة، قابلة للتعديل من هنا)
        card_details_row = QHBoxLayout()
        card_details_row.addWidget(QLabel("عدد الأفراد:"))
        self.family_members_spin = QDoubleSpinBox()
        self.family_members_spin.setDecimals(0)
        self.family_members_spin.setMaximum(50)
        self.family_members_spin.setMinimum(1)
        self.family_members_spin.setEnabled(False)
        card_details_row.addWidget(self.family_members_spin)

        self.save_card_details_btn = QPushButton("تحديث عدد الأفراد")
        self.save_card_details_btn.setEnabled(False)
        self.save_card_details_btn.clicked.connect(self.save_card_details)
        card_details_row.addWidget(self.save_card_details_btn)
        card_layout.addLayout(card_details_row)

        card_box.setLayout(card_layout)
        right_col.addWidget(card_box)

        # الدعم: التموين + العيش، بيتكتبوا في كل عملية بيع، ومجموعهم بيتخصم من (الإجمالي + الخدمة)
        support_box = QGroupBox("الدعم (يُخصم من الفاتورة)")
        support_layout = QHBoxLayout()
        support_layout.addWidget(QLabel("التموين:"))
        self.support_tamween_spin = QDoubleSpinBox()
        self.support_tamween_spin.setDecimals(2)
        self.support_tamween_spin.setMaximum(999999)
        self.support_tamween_spin.valueChanged.connect(self.refresh_cart_table)
        support_layout.addWidget(self.support_tamween_spin)

        support_layout.addWidget(QLabel("العيش:"))
        self.support_bread_spin = QDoubleSpinBox()
        self.support_bread_spin.setDecimals(2)
        self.support_bread_spin.setMaximum(999999)
        self.support_bread_spin.valueChanged.connect(self.refresh_cart_table)
        support_layout.addWidget(self.support_bread_spin)
        support_box.setLayout(support_layout)
        right_col.addWidget(support_box)

        # خدمة: مبلغ يُضاف على الفاتورة قبل حساب المطلوب
        service_box = QGroupBox("خدمة (تُضاف على الفاتورة)")
        service_layout = QHBoxLayout()
        self.card_hit_spin = QDoubleSpinBox()
        self.card_hit_spin.setDecimals(2)
        self.card_hit_spin.setMaximum(999999)
        self.card_hit_spin.valueChanged.connect(self.refresh_cart_table)
        service_layout.addWidget(self.card_hit_spin)
        service_box.setLayout(service_layout)
        right_col.addWidget(service_box)

        payment_box = QGroupBox("طريقة الدفع")
        payment_layout = QVBoxLayout()
        payment_layout.setSpacing(10)
        self.payment_method_combo = QComboBox()
        self.payment_method_combo.addItem("كاش (فوري)", "cash")
        self.payment_method_combo.addItem("آجل (على حساب عميل)", "credit")
        self.payment_method_combo.addItem("فيزا", "visa")
        self.payment_method_combo.addItem("إنستا باي", "instapay")
        self.payment_method_combo.addItem("محفظة", "wallet")
        self.payment_method_combo.currentIndexChanged.connect(self._on_payment_method_changed)
        payment_layout.addWidget(self.payment_method_combo)

        customer_row = QHBoxLayout()
        self.customer_search_edit = QLineEdit()
        self.customer_search_edit.setPlaceholderText("اكتب اسم العميل...")
        self.customer_search_edit.setEnabled(False)
        self.customer_search_edit.textChanged.connect(self.on_customer_search_changed)
        customer_row.addWidget(self.customer_search_edit)
        payment_layout.addLayout(customer_row)

        self.customer_results_list = QListWidget()
        self.customer_results_list.setMinimumHeight(110)
        self.customer_results_list.setMaximumHeight(130)
        self.customer_results_list.itemClicked.connect(self.on_customer_selected)
        self.customer_results_list.setEnabled(False)
        payment_layout.addWidget(self.customer_results_list)

        self.selected_customer_label = QLabel("لا يوجد عميل محدد")
        self.selected_customer_label.setStyleSheet("color: gray; margin-top: 4px;")
        payment_layout.addWidget(self.selected_customer_label)

        payment_box.setLayout(payment_layout)
        right_col.addWidget(payment_box)
        self.selected_customer = None

        sale_type_box = QGroupBox("نوع السعر للصنف القادم")
        sale_type_layout = QHBoxLayout()
        self.sale_type_combo = QComboBox()
        self.sale_type_combo.addItem("تموين (يتطلب بطاقة)", "tamween")
        self.sale_type_combo.addItem("حر", "free")
        self.sale_type_combo.addItem("عيش", "bread")
        self.sale_type_combo.addItem("جملة", "wholesale")
        sale_type_layout.addWidget(self.sale_type_combo)
        sale_type_box.setLayout(sale_type_layout)
        right_col.addWidget(sale_type_box)

        right_col.addStretch()

        right_col_widget = QWidget()
        right_col_widget.setLayout(right_col)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setWidget(right_col_widget)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        main_layout.addWidget(right_scroll, 2)

        # --------- العمود الأوسط: سلة المشتريات ---------
        center_col = QVBoxLayout()
        self.cart_table = QTableWidget(0, 5)
        self.cart_table.setHorizontalHeaderLabels(
            ["الصنف", "النوع", "الكمية", "السعر", "الإجمالي"]
        )
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cart_table.setColumnWidth(1, 110)
        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.cart_table.setColumnWidth(2, 110)
        self.cart_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.cart_table.setColumnWidth(3, 90)
        self.cart_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.cart_table.setColumnWidth(4, 100)
        self.cart_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        center_col.addWidget(self.cart_table)

        remove_btn = QPushButton("حذف الصنف المحدد")
        remove_btn.clicked.connect(self.remove_selected)
        center_col.addWidget(remove_btn)

        main_layout.addLayout(center_col, 3)

        # --------- العمود الأيسر: الإجماليات والدفع ---------
        left_col = QVBoxLayout()
        totals_box = QGroupBox("الإجمالي")
        totals_layout = QVBoxLayout()
        self.total_tamween_label = QLabel("التموين: 0.00 ج.م")
        self.total_free_label = QLabel("الحر: 0.00 ج.م")
        self.total_bread_label = QLabel("العيش: 0.00 ج.م")
        self.total_wholesale_label = QLabel("الجملة: 0.00 ج.م")
        self.card_hit_label = QLabel("خدمة: 0.00 ج.م")
        self.card_hit_label.setStyleSheet("color: #a15c00;")
        self.grand_total_label = QLabel("الإجمالي: 0.00 ج.م")
        self.total_with_service_label = QLabel("الإجمالي + الخدمة: 0.00 ج.م")
        self.support_label = QLabel("الدعم: 0.00 ج.م")
        self.support_label.setStyleSheet("color: #1D6FD8;")
        self.required_label = QLabel("المطلوب: 0.00 ج.م")
        self.required_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #C0392B;")
        self.remaining_label = QLabel("المتبقي: 0.00 ج.م")
        self.remaining_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #1E7A3D;")
        totals_layout.addWidget(self.total_tamween_label)
        totals_layout.addWidget(self.total_free_label)
        totals_layout.addWidget(self.total_bread_label)
        totals_layout.addWidget(self.total_wholesale_label)
        totals_layout.addWidget(self.grand_total_label)
        totals_layout.addWidget(self.card_hit_label)
        totals_layout.addWidget(self.total_with_service_label)
        totals_layout.addWidget(self.support_label)
        totals_layout.addWidget(self.required_label)
        totals_layout.addWidget(self.remaining_label)
        totals_box.setLayout(totals_layout)
        left_col.addWidget(totals_box)

        checkout_btn = QPushButton("إتمام البيع والطباعة")
        checkout_btn.setObjectName("checkoutButton")
        checkout_btn.setStyleSheet("font-size: 15px;")
        checkout_btn.clicked.connect(self.checkout)
        left_col.addWidget(checkout_btn)

        clear_btn = QPushButton("إلغاء الفاتورة الحالية")
        clear_btn.clicked.connect(self.clear_cart)
        left_col.addWidget(clear_btn)

        hold_btn = QPushButton("تعليق الفاتورة")
        hold_btn.clicked.connect(self.hold_current_sale)
        left_col.addWidget(hold_btn)

        held_list_btn = QPushButton("الفواتير المعلّقة")
        held_list_btn.clicked.connect(self.open_held_sales_dialog)
        left_col.addWidget(held_list_btn)

        shift_invoices_btn = QPushButton("فواتير الوردية الحالية")
        shift_invoices_btn.clicked.connect(self.open_shift_invoices_dialog)
        left_col.addWidget(shift_invoices_btn)

        self.last_invoice_btn = QPushButton("⏮ الرجوع لآخر فاتورة")
        self.last_invoice_btn.setEnabled(False)
        self.last_invoice_btn.clicked.connect(self.open_last_invoice_dialog)
        left_col.addWidget(self.last_invoice_btn)

        left_col.addStretch()
        main_layout.addLayout(left_col, 1)

        shortcuts_label = QLabel(
            "اختصارات: F1 التركيز على البحث  |  F2 التركيز على بطاقة التموين  |  "
            "F3 / F5 إتمام البيع والطباعة  |  Delete حذف الصنف المحدد  |  Esc إلغاء الفاتورة"
        )
        shortcuts_label.setStyleSheet("color: #9AA6B2; font-size: 11px;")
        shortcuts_label.setAlignment(Qt.AlignCenter)
        outer_layout = QVBoxLayout()
        outer_layout.addLayout(main_layout)
        outer_layout.addWidget(shortcuts_label)
        self.setLayout(outer_layout)

        self._setup_shortcuts()
        self.barcode_edit.setFocus()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F1"), self, activated=lambda: self.barcode_edit.setFocus())
        QShortcut(QKeySequence("F2"), self, activated=lambda: self.card_edit.setFocus())
        QShortcut(QKeySequence("F3"), self, activated=self.checkout)
        QShortcut(QKeySequence("F5"), self, activated=self.checkout)
        QShortcut(QKeySequence("Delete"), self, activated=self.remove_selected)
        QShortcut(QKeySequence("Escape"), self, activated=self.clear_cart)

    # ---------------- منطق العمل ----------------
    def on_search_text_changed(self, text):
        text = text.strip()
        self.search_results_list.clear()
        if len(text) < 1:
            return
        try:
            results = self.db.search_products(text)
        except DatabaseError:
            return
        for product in results[:8]:
            qty = float(product["quantity"])
            label = f"{product['name']}  —  متاح: {qty:g} {product['unit'] or ''}"
            if product["barcode"]:
                label += f"  ({product['barcode']})"
            item = QListWidgetItem(label)
            if qty <= float(product["min_quantity"]):
                item.setForeground(Qt.red)
            item.setData(Qt.UserRole, product)
            self.search_results_list.addItem(item)

    def eventFilter(self, source, event):
        """PgUp/PgDn في حقل البحث يتنقلوا بين نتائج البحث"""
        from PyQt5.QtCore import QEvent
        if source is self.barcode_edit and event.type() == QEvent.KeyPress:
            count = self.search_results_list.count()
            if count == 0:
                return super().eventFilter(source, event)
            key = event.key()
            current = self.search_results_list.currentRow()
            if key == Qt.Key_PageDown:
                next_row = min(current + 1, count - 1) if current >= 0 else 0
                self.search_results_list.setCurrentRow(next_row)
                return True
            elif key == Qt.Key_PageUp:
                prev_row = max(current - 1, 0) if current >= 0 else 0
                self.search_results_list.setCurrentRow(prev_row)
                return True
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                # لو في عنصر محدد في القائمة → اختاره
                if self.search_results_list.currentItem():
                    self.on_search_item_selected(self.search_results_list.currentItem())
                    return True
        return super().eventFilter(source, event)

    def on_search_item_selected(self, item):
        product = item.data(Qt.UserRole)
        self._try_add_product(product)
        self.barcode_edit.clear()
        self.search_results_list.clear()
        self.barcode_edit.setFocus()

    def on_barcode_enter(self):
        text = self.barcode_edit.text().strip()
        if not text:
            return
        try:
            product = self.db.find_product_by_barcode(text)
            if not product:
                results = self.db.search_products(text)
                if not results:
                    QMessageBox.warning(self, "غير موجود", "لم يتم العثور على صنف بهذا الباركود/الاسم")
                    return
                product = results[0]
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self._try_add_product(product)
        self.barcode_edit.clear()
        self.search_results_list.clear()

    def _try_add_product(self, product):
        """يتحقق من الشروط ويضيف الصنف للسلة. يستخدم من مسح الباركود ومن قائمة البحث."""
        qty_available = float(product["quantity"])
        unit_label = product["unit"] or ""
        stock_text = f"الكمية المتاحة بالمخزون: {qty_available:g} {unit_label}"
        self.stock_label.setText(stock_text)
        if qty_available <= float(product["min_quantity"]):
            self.stock_label.setStyleSheet("color: #C0392B; font-weight: 700;")
        else:
            self.stock_label.setStyleSheet("color: #4A5A6B; font-weight: 600;")

        sale_type = self.sale_type_combo.currentData()

        if sale_type == "tamween" and not self.active_ration_card:
            QMessageBox.warning(self, "تنبيه", "من فضلك اربط بطاقة تموين أولاً قبل البيع بسعر التموين")
            return

        if qty_available <= 0:
            QMessageBox.warning(self, "تنبيه", f"الصنف \"{product['name']}\" غير متوفر بالمخزون")
            return

        price_field = {
            "tamween": "price_tamween",
            "free": "price_free",
            "bread": "price_bread",
            "wholesale": "price_wholesale",
        }[sale_type]
        unit_price = float(product[price_field])

        self.cart.append({
            "product_id": product["id"],
            "name": product["name"],
            "sale_type": sale_type,
            "quantity": 1,
            "unit_price": unit_price,
            "price_tamween": float(product["price_tamween"]),
            "price_free": float(product["price_free"]),
            "price_bread": float(product["price_bread"]),
            "price_wholesale": float(product["price_wholesale"]),
        })
        self.refresh_cart_table()

    def attach_ration_card(self):
        card_number = self.card_edit.text().strip()
        if not card_number:
            return
        try:
            card = self.db.find_ration_card(card_number)
            if not card:
                # عميل جديد معاهش بطاقة مسجلة - نسجلها أوتوماتيك برقمها بس من غير أي بيانات زيادة
                self.db.add_ration_card({
                    "card_number": card_number,
                    "holder_name": None,
                    "family_members": 1,
                    "phone": None,
                    "monthly_limit": 0,
                    "notes": "أُضيفت تلقائيًا وقت البيع",
                })
                card = self.db.find_ration_card(card_number)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.active_ration_card = card
        self.last_invoice_btn.setEnabled(True)
        usage = self.db.ration_card_monthly_usage(card["id"])
        limit_txt = f" (السقف الشهري: {card['monthly_limit']:.2f} ج.م)" if card["monthly_limit"] else ""
        holder_txt = card["holder_name"] or "عميل جديد (بدون اسم مسجل)"
        self.card_status_label.setText(
            f"مرتبطة: {holder_txt} - رقم {card['card_number']} | "
            f"مستهلك من التموين هذا الشهر: {usage:.2f} ج.م{limit_txt}"
        )
        self.card_status_label.setStyleSheet("color: green; font-weight: bold;")

        self.family_members_spin.setValue(card["family_members"] or 1)
        self.family_members_spin.setEnabled(True)
        self.save_card_details_btn.setEnabled(True)

    def save_card_details(self):
        if not self.active_ration_card:
            return
        try:
            self.db.update_card_quick(
                self.active_ration_card["id"],
                int(self.family_members_spin.value()),
                float(self.active_ration_card.get("bread_value") or 0),
            )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        self.active_ration_card["family_members"] = int(self.family_members_spin.value())
        QMessageBox.information(self, "تم", "تم تحديث عدد الأفراد بنجاح")

    def refresh_cart_table(self):
        self.cart_table.setRowCount(len(self.cart))
        self.cart_table.verticalHeader().setDefaultSectionSize(44)
        totals = {"tamween": 0.0, "free": 0.0, "bread": 0.0, "wholesale": 0.0}
        type_labels = {"tamween": "تموين", "free": "حر", "bread": "عيش", "wholesale": "جملة"}

        for row, item in enumerate(self.cart):
            line_total = item["quantity"] * item["unit_price"]
            totals[item["sale_type"]] += line_total

            self.cart_table.setItem(row, 0, QTableWidgetItem(item["name"]))

            type_combo = QComboBox()
            type_combo.addItem("تموين", "tamween")
            type_combo.addItem("حر", "free")
            type_combo.addItem("عيش", "bread")
            type_combo.addItem("جملة", "wholesale")
            idx = type_combo.findData(item["sale_type"])
            type_combo.setCurrentIndex(idx if idx >= 0 else 0)
            type_combo.currentIndexChanged.connect(
                lambda _, r=row, combo=type_combo: self.update_sale_type(r, combo.currentData())
            )
            self.cart_table.setCellWidget(row, 1, type_combo)

            qty_spin = QDoubleSpinBox()
            qty_spin.setDecimals(2)
            qty_spin.setMinimum(0.01)
            qty_spin.setMaximum(9999)
            qty_spin.setValue(item["quantity"])
            qty_spin.valueChanged.connect(lambda val, r=row: self.update_quantity(r, val))
            self.cart_table.setCellWidget(row, 2, qty_spin)

            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{item['unit_price']:.2f}"))
            self.cart_table.setItem(row, 4, QTableWidgetItem(f"{line_total:.2f}"))

        self.total_tamween_label.setText(f"التموين: {totals['tamween']:.2f} ج.م")
        self.total_free_label.setText(f"الحر: {totals['free']:.2f} ج.م")
        self.total_bread_label.setText(f"العيش: {totals['bread']:.2f} ج.م")
        self.total_wholesale_label.setText(f"الجملة: {totals['wholesale']:.2f} ج.م")
        self.grand_total_label.setText(f"الإجمالي: {sum(totals.values()):.2f} ج.م")

        card_hit = self.card_hit_spin.value()
        total_with_service = round(sum(totals.values()) + card_hit, 2)
        support_tamween = self.support_tamween_spin.value()
        support_bread = self.support_bread_spin.value()
        support_total = round(support_tamween + support_bread, 2)
        net = round(total_with_service - support_total, 2)
        required = round(net, 2) if net > 0 else 0.0
        remaining = round(-net, 2) if net < 0 else 0.0

        self.card_hit_label.setText(f"خدمة: {card_hit:.2f} ج.م")
        self.total_with_service_label.setText(f"الإجمالي + الخدمة: {total_with_service:.2f} ج.م")
        self.support_label.setText(f"الدعم: {support_total:.2f} ج.م")
        self.required_label.setText(f"المطلوب: {required:.2f} ج.م")
        self.remaining_label.setText(f"المتبقي: {remaining:.2f} ج.م")

    def update_sale_type(self, row, new_type):
        if not (0 <= row < len(self.cart)):
            return
        item = self.cart[row]
        if item["sale_type"] == new_type:
            return

        if new_type == "tamween" and not self.active_ration_card:
            QMessageBox.warning(self, "تنبيه", "من فضلك اربط بطاقة تموين أولاً قبل تغيير النوع لتموين")
            self.refresh_cart_table()  # يرجّع القايمة لاختيارها الصح تاني
            return

        price_field = {
            "tamween": "price_tamween",
            "free": "price_free",
            "bread": "price_bread",
            "wholesale": "price_wholesale",
        }[new_type]
        item["sale_type"] = new_type
        item["unit_price"] = item.get(price_field, item["unit_price"])
        self.refresh_cart_table()

    def update_quantity(self, row, value):
        if 0 <= row < len(self.cart):
            self.cart[row]["quantity"] = value
            self.refresh_cart_table()

    def remove_selected(self):
        row = self.cart_table.currentRow()
        if row >= 0:
            del self.cart[row]
            self.refresh_cart_table()

    def _on_payment_method_changed(self):
        is_credit = self.payment_method_combo.currentData() == "credit"
        self.customer_search_edit.setEnabled(is_credit)
        self.customer_results_list.setEnabled(is_credit)
        if not is_credit:
            self.selected_customer = None
            self.selected_customer_label.setText("لا يوجد عميل محدد")
            self.selected_customer_label.setStyleSheet("color: gray;")
            self.customer_search_edit.clear()
            self.customer_results_list.clear()

    def on_customer_search_changed(self, text):
        self.customer_results_list.clear()
        text = text.strip()
        if len(text) < 1:
            return
        try:
            results = self.db.search_customers(text)
        except DatabaseError:
            return
        for c in results:
            item = QListWidgetItem(f"{c['name']} — {c['phone'] or ''}")
            item.setData(Qt.UserRole, c)
            self.customer_results_list.addItem(item)

    def on_customer_selected(self, item):
        customer = item.data(Qt.UserRole)
        self.selected_customer = customer
        self.selected_customer_label.setText(f"العميل: {customer['name']}")
        self.selected_customer_label.setStyleSheet("color: green; font-weight: bold;")
        self.customer_search_edit.clear()
        self.customer_results_list.clear()

    def open_shift_invoices_dialog(self):
        try:
            shift = self.db.get_open_shift()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        if not shift:
            QMessageBox.information(self, "تنبيه", "مفيش وردية مفتوحة دلوقتي")
            return

        try:
            invoices = self.db.list_shift_invoices(shift["id"])
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"فواتير الوردية رقم {shift['id']}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)

        if not invoices:
            layout.addWidget(QLabel("مفيش فواتير في الوردية دي لسه."))
        else:
            list_widget = QListWidget()
            for inv in invoices:
                net = inv["net_total"] if inv["net_total"] is not None else inv["grand_total"]
                status_txt = " (ملغاة)" if inv["status"] == "cancelled" else ""
                item = QListWidgetItem(
                    f"فاتورة {inv['invoice_number']} — {float(net):.2f} ج.م — "
                    f"{inv.get('cashier_name') or ''}{status_txt}"
                )
                item.setData(Qt.UserRole, inv["id"])
                list_widget.addItem(item)
            layout.addWidget(list_widget)

            view_btn = QPushButton("عرض/تعديل الفاتورة المحددة")
            view_btn.setObjectName("primaryButton")
            view_btn.clicked.connect(lambda: self._open_invoice_from_list(list_widget, dialog))
            layout.addWidget(view_btn)

        dialog.exec_()

    def _open_invoice_from_list(self, list_widget, parent_dialog):
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(parent_dialog, "تنبيه", "اختار فاتورة الأول")
            return
        invoice_id = item.data(Qt.UserRole)
        parent_dialog.accept()
        self.open_invoice_editor(invoice_id)

    def open_invoice_editor(self, invoice_id):
        try:
            invoice, items = self.db.get_invoice_with_items(invoice_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        if not invoice:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"فاتورة رقم {invoice['invoice_number']}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(550, 460)
        layout = QVBoxLayout(dialog)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)

        net = invoice["net_total"] if invoice["net_total"] is not None else invoice["grand_total"]
        status_text = "ملغاة بالكامل ❌" if invoice["status"] == "cancelled" else "نشطة ✅"
        header = QLabel(f"الحالة: {status_text}\nالإجمالي الصافي الحالي: {float(net):.2f} ج.م")
        content_layout.addWidget(header)

        type_labels = {"tamween": "تموين", "free": "حر", "bread": "عيش", "wholesale": "جملة"}
        table = QTableWidget(len(items), 5)
        table.setHorizontalHeaderLabels(["الصنف", "النوع", "الكمية", "الإجمالي", "الحالة"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        for row, it in enumerate(items):
            table.setItem(row, 0, QTableWidgetItem(it["product_name"]))
            table.setItem(row, 1, QTableWidgetItem(type_labels.get(it["sale_type"], it["sale_type"])))
            table.setItem(row, 2, QTableWidgetItem(f"{float(it['quantity']):g}"))
            table.setItem(row, 3, QTableWidgetItem(f"{float(it['line_total']):.2f}"))
            status_item = QTableWidgetItem("ملغى" if it["status"] == "cancelled" else "نشط")
            if it["status"] == "cancelled":
                status_item.setForeground(Qt.red)
            table.setItem(row, 4, status_item)
        content_layout.addWidget(table)
        layout.addWidget(content_widget)

        action_row = QHBoxLayout()
        reprint_btn = QPushButton("🖶 طباعة الفاتورة (طابعة حرارية)")
        reprint_btn.clicked.connect(lambda: self._reprint_receipt(invoice, items))
        action_row.addWidget(reprint_btn)
        layout.addLayout(action_row)

        if self.can_cancel and invoice["status"] != "cancelled":
            btn_row = QHBoxLayout()
            edit_item_btn = QPushButton("تعديل الصنف المحدد")
            edit_item_btn.clicked.connect(lambda: self._edit_selected_item(table, items, dialog, invoice_id))
            cancel_item_btn = QPushButton("إلغاء الصنف المحدد فقط")
            cancel_item_btn.clicked.connect(lambda: self._cancel_selected_item(table, items, dialog))
            cancel_invoice_btn = QPushButton("إلغاء الفاتورة بالكامل")
            cancel_invoice_btn.setObjectName("primaryButton")
            cancel_invoice_btn.clicked.connect(lambda: self._cancel_whole_invoice(invoice_id, dialog))
            btn_row.addWidget(edit_item_btn)
            btn_row.addWidget(cancel_item_btn)
            btn_row.addWidget(cancel_invoice_btn)
            layout.addLayout(btn_row)
        elif not self.can_cancel:
            note = QLabel("شاشة عرض بس — التعديل والإلغاء محتاجين صلاحية خاصة.")
            note.setStyleSheet("color: gray;")
            layout.addWidget(note)

        dialog.exec_()

    def _edit_selected_item(self, table, items, dialog, invoice_id):
        row = table.currentRow()
        if row < 0:
            QMessageBox.warning(dialog, "تنبيه", "اختار صنف من الجدول الأول")
            return
        item = items[row]
        if item["status"] == "cancelled":
            QMessageBox.information(dialog, "تنبيه", "الصنف ده ملغى بالفعل، مينفعش تعدّل فيه")
            return

        edit_dialog = QDialog(dialog)
        edit_dialog.setWindowTitle(f"تعديل: {item['product_name']}")
        edit_dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(edit_dialog)

        qty_spin = QDoubleSpinBox()
        qty_spin.setDecimals(2)
        qty_spin.setMaximum(999999)
        qty_spin.setValue(float(item["quantity"]))
        price_spin = QDoubleSpinBox()
        price_spin.setDecimals(2)
        price_spin.setMaximum(999999)
        price_spin.setValue(float(item["unit_price"]))

        form.addRow("الكمية الجديدة:", qty_spin)
        form.addRow("السعر الجديد:", price_spin)

        confirm_btn = QPushButton("حفظ التعديل")
        confirm_btn.setObjectName("primaryButton")
        form.addRow(confirm_btn)

        def do_edit():
            try:
                self.db.update_invoice_item(item["id"], qty_spin.value(), price_spin.value(), self.current_user["id"])
            except DatabaseError as e:
                QMessageBox.critical(edit_dialog, "خطأ", str(e))
                return
            QMessageBox.information(edit_dialog, "تم", "تم تعديل الصنف وتحديث الفاتورة والمخزون")
            edit_dialog.accept()
            dialog.accept()
            self.open_invoice_editor(invoice_id)

        confirm_btn.clicked.connect(do_edit)
        edit_dialog.exec_()

    def _reprint_receipt(self, invoice, items):
        cfg = config.load_config()
        cart_like = [
            {
                "name": it["product_name"],
                "quantity": float(it["quantity"]),
                "unit_price": float(it["unit_price"]),
                "sale_type": it["sale_type"],
            }
            for it in items if it["status"] != "cancelled"
        ]
        grand_total = float(invoice["grand_total"])
        card_hit_amount = float(invoice.get("card_hit_amount") or 0)
        support_tamween = float(invoice.get("support_tamween") or 0)
        support_bread = float(invoice.get("support_bread") or 0)
        total_with_service = round(grand_total + card_hit_amount, 2)
        net_total = float(invoice["net_total"]) if invoice["net_total"] is not None else total_with_service
        required_amount = round(net_total, 2) if net_total > 0 else 0.0
        remaining_amount = round(-net_total, 2) if net_total < 0 else 0.0

        result = {
            "invoice_number": invoice["invoice_number"],
            "total_tamween": float(invoice["total_tamween"]),
            "total_free": float(invoice["total_free"]),
            "total_bread": float(invoice["total_bread"]),
            "total_wholesale": float(invoice["total_wholesale"]),
            "grand_total": grand_total,
            "card_hit_amount": card_hit_amount,
            "total_with_service": total_with_service,
            "support_tamween": support_tamween,
            "support_bread": support_bread,
            "net_total": net_total,
            "required_amount": required_amount,
            "remaining_amount": remaining_amount,
            "payment_method": invoice.get("payment_method"),
        }
        ration_card = None
        if invoice.get("ration_card_id"):
            try:
                ration_card = self.db.get_ration_card_by_id(invoice["ration_card_id"])
            except DatabaseError:
                ration_card = None
        cashier_name = invoice.get("cashier_name") or self.current_user.get("full_name")
        receipt_text = printer.build_receipt_text(
            cfg, result, cart_like, ration_card=ration_card, cashier_name=cashier_name,
            width=int(cfg.get("receipt_width", 32))
        )
        receipt_html = printer.build_receipt_html(cfg, result, cart_like, ration_card=ration_card, cashier_name=cashier_name)
        try:
            printer.print_receipt(receipt_text, receipt_html)
            QMessageBox.information(self, "تم", "تم إرسال الإيصال للطباعة")
        except Exception as e:
            QMessageBox.warning(self, "تنبيه طباعة", f"حصل خطأ أثناء الطباعة:\n{e}")

    def _cancel_selected_item(self, table, items, dialog):
        row = table.currentRow()
        if row < 0:
            QMessageBox.warning(dialog, "تنبيه", "اختار صنف من الجدول الأول")
            return
        item = items[row]
        if item["status"] == "cancelled":
            QMessageBox.information(dialog, "تنبيه", "الصنف ده ملغى بالفعل")
            return

        confirm = QMessageBox.question(
            dialog, "تأكيد", f"متأكد إنك عايز تلغي صنف \"{item['product_name']}\" من الفاتورة دي؟"
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.cancel_invoice_item(item["id"], self.current_user["id"])
        except DatabaseError as e:
            QMessageBox.critical(dialog, "خطأ", str(e))
            return
        QMessageBox.information(dialog, "تم", "تم إلغاء الصنف وإرجاع الكمية للمخزون")
        dialog.accept()
        self.open_invoice_editor(item["invoice_id"])

    def _cancel_whole_invoice(self, invoice_id, dialog):
        confirm = QMessageBox.question(
            dialog, "تأكيد نهائي",
            "متأكد إنك عايز تلغي الفاتورة دي بالكامل؟ كل الكميات هترجع للمخزون."
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.cancel_invoice(invoice_id, self.current_user["id"], "إلغاء من شاشة البيع")
        except DatabaseError as e:
            QMessageBox.critical(dialog, "خطأ", str(e))
            return
        QMessageBox.information(dialog, "تم الإلغاء", "تم إلغاء الفاتورة بالكامل وإرجاع الكميات للمخزون")
        dialog.accept()

    def hold_current_sale(self):
        if not self.cart:
            QMessageBox.information(self, "تنبيه", "السلة فارغة، مفيش حاجة تتعلّق")
            return

        label, ok = QInputDialog.getText(
            self, "تعليق الفاتورة", "اسم أو ملاحظة تساعدك تتعرف على الفاتورة دي بعدين (اختياري):"
        )
        if not ok:
            return

        ration_card_id = self.active_ration_card["id"] if self.active_ration_card else None
        try:
            self.db.hold_sale(
                self.current_user["id"], self.cart, ration_card_id,
                self.card_hit_spin.value(), label.strip(),
                support_tamween=self.support_tamween_spin.value(),
                support_bread=self.support_bread_spin.value(),
            )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(self, "تم التعليق", "تم تعليق الفاتورة. تقدر ترجعلها من زرار \"الفواتير المعلّقة\".")
        self.clear_cart()

    def open_held_sales_dialog(self):
        try:
            held_sales = self.db.list_held_sales()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("الفواتير المعلّقة")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)

        if not held_sales:
            layout.addWidget(QLabel("مفيش فواتير معلّقة دلوقتي."))
        else:
            list_widget = QListWidget()
            for hs in held_sales:
                cart_items = json.loads(hs["cart_json"])
                item_count = len(cart_items)
                card_txt = f" - بطاقة {hs['card_number']}" if hs["card_number"] else ""
                text = (
                    f"{hs['label'] or '(بدون اسم)'} — {item_count} صنف{card_txt} — "
                    f"بواسطة {hs['held_by_name']} — {hs['held_at']}"
                )
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, hs["id"])
                list_widget.addItem(item)
            layout.addWidget(list_widget)

            btn_row = QHBoxLayout()
            resume_btn = QPushButton("استكمال الفاتورة المحددة")
            resume_btn.setObjectName("primaryButton")
            resume_btn.clicked.connect(lambda: self._resume_selected(list_widget, dialog))
            preview_btn = QPushButton("معاينة وطباعة")
            preview_btn.clicked.connect(lambda: self._preview_held_sale(list_widget, dialog))
            delete_btn = QPushButton("حذف الفاتورة المحددة")
            delete_btn.clicked.connect(lambda: self._delete_selected_held(list_widget, dialog))
            btn_row.addWidget(resume_btn)
            btn_row.addWidget(preview_btn)
            btn_row.addWidget(delete_btn)
            layout.addLayout(btn_row)

        dialog.exec_()

    def _preview_held_sale(self, list_widget, parent_dialog):
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(parent_dialog, "تنبيه", "اختار فاتورة الأول")
            return
        held_id = item.data(Qt.UserRole)

        try:
            held_sales = self.db.list_held_sales()
            hs = next((h for h in held_sales if h["id"] == held_id), None)
        except DatabaseError as e:
            QMessageBox.critical(parent_dialog, "خطأ", str(e))
            return
        if not hs:
            return

        cart_items = json.loads(hs["cart_json"])
        type_labels = {"tamween": "تموين", "free": "حر", "bread": "عيش", "wholesale": "جملة"}

        preview_dialog = QDialog(parent_dialog)
        preview_dialog.setWindowTitle(f"معاينة: {hs['label'] or 'فاتورة معلّقة'}")
        preview_dialog.setLayoutDirection(Qt.RightToLeft)
        preview_dialog.resize(450, 400)
        layout = QVBoxLayout(preview_dialog)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.addWidget(QLabel(f"الاسم/الملاحظة: {hs['label'] or '(بدون اسم)'}"))
        content_layout.addWidget(QLabel(f"بواسطة: {hs['held_by_name']} — {hs['held_at']}"))

        table = QTableWidget(len(cart_items), 4)
        table.setHorizontalHeaderLabels(["الصنف", "النوع", "الكمية", "الإجمالي"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        total = 0.0
        for row, it in enumerate(cart_items):
            line_total = it["quantity"] * it["unit_price"]
            total += line_total
            table.setItem(row, 0, QTableWidgetItem(it["name"]))
            table.setItem(row, 1, QTableWidgetItem(type_labels.get(it["sale_type"], it["sale_type"])))
            table.setItem(row, 2, QTableWidgetItem(f"{it['quantity']:g}"))
            table.setItem(row, 3, QTableWidgetItem(f"{line_total:.2f}"))
        content_layout.addWidget(table)
        content_layout.addWidget(QLabel(f"الإجمالي: {total:.2f} ج.م"))
        layout.addWidget(content_widget)

        print_row = QHBoxLayout()

        def print_as_receipt():
            cfg = config.load_config()
            meta = [f"الاسم/الملاحظة: {hs['label'] or '(بدون اسم)'}", f"بواسطة: {hs['held_by_name']} — {hs['held_at']}"]
            item_lines = []
            for it in cart_items:
                line_total = it["quantity"] * it["unit_price"]
                item_lines.append(f"{it['name']} ({type_labels.get(it['sale_type'], it['sale_type'])})")
                item_lines.append(f"  {it['quantity']:g} x {it['unit_price']:.2f} = {line_total:.2f} ج.م")
            text = printer.build_generic_receipt_text(
                cfg, hs["label"] or "فاتورة معلّقة", meta, item_lines,
                [f"الإجمالي: {total:.2f} ج.م"], width=int(cfg.get("receipt_width", 32))
            )
            try:
                printer.print_receipt(text)
            except Exception as e:
                QMessageBox.warning(preview_dialog, "تنبيه طباعة", f"حصل خطأ أثناء الطباعة:\n{e}")

        print_receipt_btn = QPushButton("🖶 طباعة (طابعة حرارية)")
        print_receipt_btn.clicked.connect(print_as_receipt)
        print_row.addWidget(print_receipt_btn)
        layout.addLayout(print_row)

        preview_dialog.exec_()

    def _resume_selected(self, list_widget, dialog):
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(dialog, "تنبيه", "اختار فاتورة الأول")
            return
        held_id = item.data(Qt.UserRole)

        try:
            held_sales = self.db.list_held_sales()
            hs = next((h for h in held_sales if h["id"] == held_id), None)
            if not hs:
                return

            if hs["ration_card_id"]:
                card = self.db.get_ration_card_by_id(hs["ration_card_id"])
                if card:
                    self.active_ration_card = card
                    self.last_invoice_btn.setEnabled(True)
                    usage = self.db.ration_card_monthly_usage(card["id"])
                    holder_txt = card["holder_name"] or "عميل جديد (بدون اسم مسجل)"
                    self.card_status_label.setText(
                        f"مرتبطة: {holder_txt} - رقم {card['card_number']} | "
                        f"مستهلك من التموين هذا الشهر: {usage:.2f} ج.م"
                    )
                    self.card_status_label.setStyleSheet("color: green; font-weight: bold;")
                    self.family_members_spin.setValue(card["family_members"] or 1)
                    self.family_members_spin.setEnabled(True)
                    self.save_card_details_btn.setEnabled(True)

            self.cart = json.loads(hs["cart_json"])
            self.card_hit_spin.setValue(float(hs["card_hit_amount"]))
            self.support_tamween_spin.setValue(float(hs.get("support_tamween") or 0))
            self.support_bread_spin.setValue(float(hs.get("support_bread") or 0))
            self.refresh_cart_table()
            self.db.delete_held_sale(held_id)
        except DatabaseError as e:
            QMessageBox.critical(dialog, "خطأ", str(e))
            return

        dialog.accept()

    def _delete_selected_held(self, list_widget, dialog):
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(dialog, "تنبيه", "اختار فاتورة الأول")
            return
        confirm = QMessageBox.question(dialog, "تأكيد", "هل تأكد إنك عايز تحذف الفاتورة المعلّقة دي نهائيًا؟")
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.delete_held_sale(item.data(Qt.UserRole))
        except DatabaseError as e:
            QMessageBox.critical(dialog, "خطأ", str(e))
            return
        dialog.accept()
        self.open_held_sales_dialog()

    def open_last_invoice_dialog(self):
        if not self.active_ration_card:
            return
        try:
            invoice_id, items = self.db.get_last_invoice_items_for_card(self.active_ration_card["id"])
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        if not invoice_id:
            QMessageBox.information(self, "تنبيه", "مفيش فواتير سابقة لصاحب البطاقة ده")
            return

        type_labels = {"tamween": "تموين", "free": "حر", "bread": "عيش", "wholesale": "جملة"}
        dialog = QDialog(self)
        dialog.setWindowTitle("آخر فاتورة لهذا العميل")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)

        holder = self.active_ration_card.get("holder_name") or "بدون اسم مسجل"
        layout.addWidget(QLabel(f"آخر طلبات {holder} (فاتورة رقم {invoice_id}):"))

        table = QTableWidget(len(items), 4)
        table.setHorizontalHeaderLabels(["الصنف", "النوع", "الكمية", "السعر"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, it in enumerate(items):
            table.setItem(row, 0, QTableWidgetItem(it["product_name"]))
            table.setItem(row, 1, QTableWidgetItem(type_labels.get(it["sale_type"], it["sale_type"])))
            table.setItem(row, 2, QTableWidgetItem(f"{float(it['quantity']):g}"))
            table.setItem(row, 3, QTableWidgetItem(f"{float(it['unit_price']):.2f}"))
        layout.addWidget(table)

        add_btn = QPushButton("➕ إضافة كل الأصناف دي للفاتورة الحالية")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(lambda: self._add_last_invoice_items(items, dialog))
        layout.addWidget(add_btn)

        dialog.exec_()

    def _add_last_invoice_items(self, items, dialog):
        for it in items:
            # نستخدم سعر المنتج الحالي لنفس نوع البيع بدل السعر القديم، عشان الأسعار ممكن تكون اتغيرت
            try:
                current_products = self.db.search_products(it["product_name"])
                match = next((p for p in current_products if p["id"] == it["product_id"]), None)
            except DatabaseError:
                match = None

            price_field = {
                "tamween": "price_tamween", "free": "price_free",
                "bread": "price_bread", "wholesale": "price_wholesale",
            }[it["sale_type"]]
            unit_price = float(match[price_field]) if match else float(it["unit_price"])

            self.cart.append({
                "product_id": it["product_id"],
                "name": it["product_name"],
                "sale_type": it["sale_type"],
                "quantity": float(it["quantity"]),
                "unit_price": unit_price,
                "price_tamween": float(match["price_tamween"]) if match else unit_price,
                "price_free": float(match["price_free"]) if match else unit_price,
                "price_bread": float(match["price_bread"]) if match else unit_price,
                "price_wholesale": float(match["price_wholesale"]) if match else unit_price,
            })

        self.refresh_cart_table()
        dialog.accept()
        QMessageBox.information(self, "تم", "تمت إضافة كل الأصناف للفاتورة الحالية")

    def clear_cart(self):
        self.cart = []
        self.active_ration_card = None
        self.last_invoice_btn.setEnabled(False)
        self.card_edit.clear()
        self.card_status_label.setText("لا توجد بطاقة مرتبطة بهذه الفاتورة")
        self.card_status_label.setStyleSheet("color: gray;")
        self.family_members_spin.setValue(1)
        self.family_members_spin.setEnabled(False)
        self.save_card_details_btn.setEnabled(False)
        self.card_hit_spin.setValue(0)
        self.support_tamween_spin.setValue(0)
        self.support_bread_spin.setValue(0)
        self.payment_method_combo.setCurrentIndex(0)
        self.selected_customer = None
        self.selected_customer_label.setText("لا يوجد عميل محدد")
        self.selected_customer_label.setStyleSheet("color: gray;")
        self.customer_search_edit.clear()
        self.customer_results_list.clear()
        self.barcode_edit.clear()
        self.search_results_list.clear()
        self.stock_label.setText("الكمية المتاحة بالمخزون: -")
        self.stock_label.setStyleSheet("color: #4A5A6B; font-weight: 600;")
        self.refresh_cart_table()

    def checkout(self):
        if not self.cart:
            QMessageBox.information(self, "تنبيه", "السلة فارغة")
            return

        payment_method = self.payment_method_combo.currentData()
        if payment_method == "credit" and not self.selected_customer:
            QMessageBox.warning(self, "تنبيه", "اختار عميل الآجل الأول من قائمة البحث قبل إتمام البيع")
            return

        ration_card_id = self.active_ration_card["id"] if self.active_ration_card else None
        items = [
            {
                "product_id": it["product_id"],
                "sale_type": it["sale_type"],
                "quantity": it["quantity"],
                "unit_price": it["unit_price"],
            }
            for it in self.cart
        ]

        try:
            shift_id = self.db.ensure_open_shift(self.current_user["id"])
            result = self.db.create_invoice(
                self.current_user["id"], ration_card_id, items, shift_id,
                card_hit_amount=self.card_hit_spin.value(),
                customer_id=self.selected_customer["id"] if self.selected_customer else None,
                payment_method=payment_method,
                support_tamween=self.support_tamween_spin.value(),
                support_bread=self.support_bread_spin.value(),
            )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "خطأ غير متوقع", f"حصلت مشكلة أثناء حفظ الفاتورة:\n{e}")
            return

        cfg = config.load_config()
        receipt_text = printer.build_receipt_text(
            cfg, result, self.cart, ration_card=self.active_ration_card,
            cashier_name=self.current_user.get("full_name") or self.current_user.get("username"),
            width=int(cfg.get("receipt_width", 32))
        )
        receipt_html = printer.build_receipt_html(
            cfg, result, self.cart, ration_card=self.active_ration_card,
            cashier_name=self.current_user.get("full_name") or self.current_user.get("username"),
        )
        try:
            printer.print_receipt(receipt_text, receipt_html)
        except Exception as e:
            QMessageBox.warning(self, "تنبيه طباعة", f"تم حفظ الفاتورة بنجاح لكن حدث خطأ أثناء الطباعة:\n{e}")

        payment_labels = {"cash": "كاش", "credit": "آجل", "visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}
        if result.get("required_amount", 0) > 0:
            amount_msg = f"المطلوب من العميل: {result['required_amount']:.2f} ج.م"
        elif result.get("remaining_amount", 0) > 0:
            amount_msg = f"المتبقي (دعم زيادة): {result['remaining_amount']:.2f} ج.م"
        else:
            amount_msg = "لا يوجد مبلغ مطلوب أو متبقي"

        if payment_method == "credit":
            money_msg = f"{amount_msg}\n(تمت الإضافة لحساب العميل {self.selected_customer['name']} كآجل)"
        else:
            money_msg = f"طريقة الدفع: {payment_labels.get(payment_method, payment_method)}\n{amount_msg}"

        QMessageBox.information(
            self, "تمت العملية",
            f"تم حفظ الفاتورة رقم {result['invoice_number']}\n{money_msg}"
        )
        self.clear_cart()
