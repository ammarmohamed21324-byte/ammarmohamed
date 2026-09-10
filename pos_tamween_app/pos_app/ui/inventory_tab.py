# -*- coding: utf-8 -*-
import datetime
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDoubleSpinBox,
    QCheckBox, QGroupBox, QHeaderView, QInputDialog, QLabel, QFileDialog, QDialog,
    QDateEdit, QCompleter
)

from database import DatabaseError
import barcode_gen
import excel_import
import excel_export
import print_utils
from ui.barcode_dialog import BarcodeStickerDialog


class InventoryTab(QWidget):
    def __init__(self, db, current_user):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.editing_product_id = None
        self.setLayoutDirection(Qt.RightToLeft)
        self.setAcceptDrops(True)
        self._build_ui()
        self.refresh_categories()
        self.refresh_units()
        self.refresh_table()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_table)
        self.auto_refresh_timer.start(2000)  # كل ثانيتين، عشان أي بيع/إضافة من جهاز تاني تظهر أوتوماتيك تقريبًا لحظيًا

    # ---------------- السحب والإفلات لاستيراد إكسيل ----------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".xlsx", ".xlsm")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".xlsx", ".xlsm")):
                self.run_excel_import(path)
                return

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # نموذج إضافة / تعديل صنف
        form_box = QGroupBox("بيانات الصنف")
        form_layout = QFormLayout()

        self.barcode_edit = QLineEdit()
        barcode_row = QHBoxLayout()
        barcode_row.addWidget(self.barcode_edit)
        generate_barcode_btn = QPushButton("توليد باركود")
        generate_barcode_btn.clicked.connect(self.generate_barcode)
        barcode_row.addWidget(generate_barcode_btn)

        self.name_edit = QLineEdit()
        self.category_combo = QComboBox()
        add_cat_btn = QPushButton("+ تصنيف جديد")
        add_cat_btn.clicked.connect(self.add_category_dialog)
        cat_row = QHBoxLayout()
        cat_row.addWidget(self.category_combo)
        cat_row.addWidget(add_cat_btn)

        self.unit_combo = QComboBox()
        add_unit_btn = QPushButton("+ وحدة جديدة")
        add_unit_btn.clicked.connect(self.add_unit_dialog)
        unit_row = QHBoxLayout()
        unit_row.addWidget(self.unit_combo)
        unit_row.addWidget(add_unit_btn)

        self.units_per_package_spin = QDoubleSpinBox()
        self.units_per_package_spin.setDecimals(0)
        self.units_per_package_spin.setMaximum(99999)
        self.units_per_package_spin.setSpecialValueText("لا ينطبق")

        self.price_tamween_spin = QDoubleSpinBox()
        self.price_tamween_spin.setMaximum(999999)
        self.price_tamween_spin.setDecimals(2)

        self.price_free_spin = QDoubleSpinBox()
        self.price_free_spin.setMaximum(999999)
        self.price_free_spin.setDecimals(2)

        self.price_bread_spin = QDoubleSpinBox()
        self.price_bread_spin.setMaximum(999999)
        self.price_bread_spin.setDecimals(2)

        self.price_wholesale_spin = QDoubleSpinBox()
        self.price_wholesale_spin.setMaximum(999999)
        self.price_wholesale_spin.setDecimals(2)

        self.purchase_price_spin = QDoubleSpinBox()
        self.purchase_price_spin.setMaximum(999999)
        self.purchase_price_spin.setDecimals(2)

        self.has_expiry_check = QCheckBox("له تاريخ صلاحية")
        self.has_expiry_check.stateChanged.connect(lambda state: self.expiry_date_edit.setEnabled(bool(state)))
        self.expiry_date_edit = QDateEdit(calendarPopup=True)
        self.expiry_date_edit.setDate(QDate.currentDate())
        self.expiry_date_edit.setEnabled(False)

        self.quantity_spin = QDoubleSpinBox()
        self.quantity_spin.setMaximum(999999)
        self.quantity_spin.setDecimals(2)

        self.min_quantity_spin = QDoubleSpinBox()
        self.min_quantity_spin.setMaximum(999999)
        self.min_quantity_spin.setDecimals(2)

        form_layout.addRow("الباركود:", barcode_row)
        form_layout.addRow("اسم الصنف:", self.name_edit)
        form_layout.addRow("التصنيف:", cat_row)
        form_layout.addRow("الوحدة:", unit_row)
        form_layout.addRow("عدد القطع في الوحدة دي (اختياري):", self.units_per_package_spin)
        form_layout.addRow("سعر الشراء (التكلفة):", self.purchase_price_spin)
        form_layout.addRow("سعر التموين:", self.price_tamween_spin)
        form_layout.addRow("سعر الحر:", self.price_free_spin)
        form_layout.addRow("سعر العيش:", self.price_bread_spin)
        form_layout.addRow("سعر الجملة:", self.price_wholesale_spin)
        form_layout.addRow(self.has_expiry_check)
        form_layout.addRow("تاريخ الصلاحية:", self.expiry_date_edit)
        form_layout.addRow("الكمية بالمخزون:", self.quantity_spin)
        form_layout.addRow("حد التنبيه (نفاذ):", self.min_quantity_spin)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("حفظ الصنف")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.save_product)
        new_btn = QPushButton("صنف جديد (تفريغ الحقول)")
        new_btn.clicked.connect(self.reset_form)
        print_barcode_btn = QPushButton("معاينة وطباعة الباركود")
        print_barcode_btn.clicked.connect(self.print_barcode)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(print_barcode_btn)

        form_container = QVBoxLayout()
        form_container.addLayout(form_layout)
        form_container.addLayout(btn_row)
        form_box.setLayout(form_container)
        layout.addWidget(form_box, 1)

        # جدول الأصناف
        table_box = QVBoxLayout()

        import_zone = QLabel(
            "📥 استيراد أصناف كتير مرة واحدة: اسحب ملف إكسيل (.xlsx) وإفلته هنا في أي مكان بالشاشة دي، "
            "أو دوس \"اختيار ملف إكسيل\" تحت. أول صف لازم يكون فيه عناوين الأعمدة (الاسم، الباركود، التصنيف، "
            "الوحدة، سعر التموين، سعر الحر، سعر العيش، سعر الجملة، الكمية، حد التنبيه)."
        )
        import_zone.setWordWrap(True)
        import_zone.setAlignment(Qt.AlignCenter)
        import_zone.setStyleSheet(
            "background:#EAF2FD; border:2px dashed #90BDEF; border-radius:8px; padding:10px; color:#0C447C; font-size:12px;"
        )
        table_box.addWidget(import_zone)

        import_btn = QPushButton("اختيار ملف إكسيل للاستيراد")
        import_btn.clicked.connect(self.choose_excel_file)
        table_box.addWidget(import_btn)

        export_btn = QPushButton("📤 تصدير كل الأصناف كإكسيل")
        export_btn.clicked.connect(self.export_to_excel)
        table_box.addWidget(export_btn)

        waste_row = QHBoxLayout()
        waste_btn = QPushButton("📉 تسجيل هالك (تالف/فاقد)")
        waste_btn.clicked.connect(self.open_record_waste_dialog)
        waste_log_btn = QPushButton("سجل الهوالك")
        waste_log_btn.clicked.connect(self.open_waste_log_dialog)
        waste_row.addWidget(waste_btn)
        waste_row.addWidget(waste_log_btn)
        table_box.addLayout(waste_row)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("بحث بالاسم أو الباركود...")
        self.search_edit.textChanged.connect(self.refresh_table)
        refresh_btn = QPushButton("تحديث")
        refresh_btn.clicked.connect(self.refresh_table)
        search_row.addWidget(self.search_edit)
        search_row.addWidget(refresh_btn)
        table_box.addLayout(search_row)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["الباركود", "الاسم", "الشراء", "تموين", "حر", "عيش", "جملة", "الكمية", "الصلاحية", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(9, 105)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Fixed)
        self.table.cellDoubleClicked.connect(self.load_row_for_edit)
        table_box.addWidget(self.table)

        layout.addLayout(table_box, 2)

    def generate_barcode(self):
        if self.barcode_edit.text().strip():
            confirm = QMessageBox.question(
                self, "تأكيد",
                "الصنف عنده باركود بالفعل، عايز تستبدله بكود جديد؟"
            )
            if confirm != QMessageBox.Yes:
                return

        def exists_check(code):
            try:
                return self.db.find_product_by_barcode(code) is not None
            except DatabaseError:
                return False

        try:
            new_code = barcode_gen.generate_unique_code(exists_check, prefix="P")
        except RuntimeError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.barcode_edit.setText(new_code)
        QMessageBox.information(
            self, "تم التوليد",
            f"تم توليد الكود: {new_code}\nمتنساش تدوس \"حفظ الصنف\" عشان يتسجل، وبعدها تقدر تطبع الملصق."
        )

    def print_barcode(self):
        barcode_value = self.barcode_edit.text().strip()
        name = self.name_edit.text().strip()
        if not barcode_value:
            QMessageBox.warning(self, "تنبيه", "لازم يكون فيه باركود الأول (ولّده أو اكتبه) قبل الطباعة")
            return
        if not name:
            name = "صنف بدون اسم"

        price = self.price_free_spin.value()
        subtitle = f"{price:.2f} ج.م" if price else ""
        dialog = BarcodeStickerDialog(name, barcode_value, subtitle_text=subtitle, parent=self)
        dialog.exec_()

    def open_record_waste_dialog(self):
        try:
            products = self.db.list_products()
            suppliers = self.db.list_suppliers()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("تسجيل هالك")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)

        product_combo = QComboBox()
        product_combo.setEditable(True)
        product_combo.setInsertPolicy(QComboBox.NoInsert)
        for p in products:
            product_combo.addItem(f"{p['name']} — متاح: {float(p['quantity']):g}", p["id"])
        product_completer = QCompleter([product_combo.itemText(i) for i in range(product_combo.count())], product_combo)
        product_completer.setCaseSensitivity(Qt.CaseInsensitive)
        product_completer.setFilterMode(Qt.MatchContains)
        product_combo.setCompleter(product_completer)
        product_combo.setCurrentIndex(-1)
        product_combo.lineEdit().setPlaceholderText("اكتب اسم الصنف للبحث...")

        qty_spin = QDoubleSpinBox()
        qty_spin.setDecimals(2)
        qty_spin.setMaximum(999999)
        qty_spin.setValue(1)

        reason_combo = QComboBox()
        reason_combo.addItems(["تالف", "منتهي الصلاحية", "كسر", "سرقة/فقدان", "أخرى"])

        supplier_combo = QComboBox()
        supplier_combo.addItem("بدون تحديد مورد", None)
        for s in suppliers:
            supplier_combo.addItem(s["name"], s["id"])

        notes_edit = QLineEdit()

        form.addRow("الصنف:", product_combo)
        form.addRow("الكمية:", qty_spin)
        form.addRow("السبب:", reason_combo)
        form.addRow("محسوبة على مورد (اختياري):", supplier_combo)
        supplier_note = QLabel(
            "لو حددت مورد، قيمة الهالك دي هتتخصم من رصيده تلقائي (تعويض عن بضاعة تالفة استلمتها منه)."
        )
        supplier_note.setWordWrap(True)
        supplier_note.setStyleSheet("color: gray; font-size: 12px;")
        form.addRow(supplier_note)
        form.addRow("ملاحظات (اختياري):", notes_edit)

        confirm_btn = QPushButton("تسجيل الهالك")
        confirm_btn.setObjectName("primaryButton")
        form.addRow(confirm_btn)

        def do_record():
            product_id = product_combo.currentData()
            if product_id is None:
                # المستخدم كتب واختار من اقتراحات البحث - نلاقي الصنف بمطابقة النص
                idx = product_combo.findText(product_combo.currentText())
                if idx >= 0:
                    product_id = product_combo.itemData(idx)
            if product_id is None:
                QMessageBox.warning(dialog, "تنبيه", "اختار صنف من نتائج البحث الأول")
                return
            try:
                self.db.record_waste(
                    product_id, qty_spin.value(), reason_combo.currentText(),
                    notes_edit.text().strip(), self.current_user["id"],
                    supplier_id=supplier_combo.currentData(),
                )
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل الهالك وتحديث المخزون بنجاح")
            dialog.accept()
            self.refresh_table()

        confirm_btn.clicked.connect(do_record)
        dialog.exec_()

    def open_waste_log_dialog(self):
        try:
            waste_records = self.db.list_waste()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("سجل الهوالك")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(600, 450)
        layout = QVBoxLayout(dialog)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)

        total_loss = sum(float(w["quantity"]) * float(w.get("purchase_price") or 0) for w in waste_records)
        content_layout.addWidget(QLabel(f"إجمالي عدد السجلات: {len(waste_records)} — قيمة الخسارة التقديرية: {total_loss:.2f} ج.م"))

        table = QTableWidget(len(waste_records), 7)
        table.setHorizontalHeaderLabels(["الصنف", "الكمية", "السبب", "محسوبة على مورد", "بواسطة", "التاريخ", "ملاحظات"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, w in enumerate(waste_records):
            table.setItem(row, 0, QTableWidgetItem(w["product_name"]))
            table.setItem(row, 1, QTableWidgetItem(f"{float(w['quantity']):g}"))
            table.setItem(row, 2, QTableWidgetItem(w.get("reason") or "-"))
            table.setItem(row, 3, QTableWidgetItem(w.get("supplier_name") or "-"))
            table.setItem(row, 4, QTableWidgetItem(w.get("recorded_by_name") or "-"))
            table.setItem(row, 5, QTableWidgetItem(str(w["recorded_at"])))
            table.setItem(row, 6, QTableWidgetItem(w.get("notes") or ""))
        content_layout.addWidget(table)
        layout.addWidget(content_widget)

        def build_html():
            rows = [
                [w["product_name"], f"{float(w['quantity']):g}", w.get("reason") or "-",
                 w.get("supplier_name") or "-", w.get("recorded_by_name") or "-",
                 str(w["recorded_at"]), w.get("notes") or ""]
                for w in waste_records
            ]
            return print_utils.build_report_html(
                "سجل الهوالك",
                meta_lines=[f"إجمالي عدد السجلات: {len(waste_records)}"],
                sections=[{
                    "headers": ["الصنف", "الكمية", "السبب", "محسوبة على مورد", "بواسطة", "التاريخ", "ملاحظات"],
                    "rows": rows,
                }],
                footer_lines=[f"قيمة الخسارة التقديرية: {total_loss:.2f} ج.م"],
            )

        print_row = QHBoxLayout()
        print_utils.add_html_print_button(print_row, build_html, dialog)
        layout.addLayout(print_row)

        dialog.exec_()

    def export_to_excel(self):
        try:
            products = self.db.list_products()
            categories = self.db.list_categories()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        if not products:
            QMessageBox.information(self, "تنبيه", "مفيش أصناف في المخزون عشان تصدرها")
            return

        categories_by_id = {c["id"]: c["name"] for c in categories}

        default_name = f"أصناف_المخزون_{datetime.date.today().isoformat()}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "حفظ ملف الإكسيل", default_name, "ملفات إكسيل (*.xlsx)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path += ".xlsx"

        try:
            excel_export.export_products_to_excel(products, categories_by_id, file_path)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذّر حفظ الملف:\n{e}")
            return

        QMessageBox.information(self, "تم بنجاح", f"تم تصدير {len(products)} صنف إلى:\n{file_path}")

    def choose_excel_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختيار ملف إكسيل للاستيراد", "", "ملفات إكسيل (*.xlsx *.xlsm)"
        )
        if path:
            self.run_excel_import(path)

    def run_excel_import(self, path):
        confirm = QMessageBox.question(
            self, "تأكيد الاستيراد",
            f"هيتم قراءة الملف:\n{path}\nوإضافة كل الأصناف الموجودة فيه كأصناف جديدة. متأكد؟"
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            result = excel_import.import_products(self.db, path)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذّرت قراءة الملف:\n{e}")
            return

        message = f"تم استيراد {result['success_count']} من أصل {result['total_found']} صنف بنجاح."
        if result["failed_rows"]:
            message += "\n\nمشاكل حصلت:\n" + "\n".join(result["failed_rows"][:15])
            if len(result["failed_rows"]) > 15:
                message += f"\n... و {len(result['failed_rows']) - 15} مشكلة تانية"

        if result["success_count"] > 0:
            QMessageBox.information(self, "نتيجة الاستيراد", message)
        else:
            QMessageBox.warning(self, "نتيجة الاستيراد", message)

        self.refresh_categories()
        self.refresh_table()

    def refresh_categories(self):
        self.category_combo.clear()
        try:
            cats = self.db.list_categories()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        for c in cats:
            self.category_combo.addItem(c["name"], c["id"])

    def refresh_units(self):
        current = self.unit_combo.currentText()
        self.unit_combo.clear()
        try:
            units = self.db.list_units()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        for u in units:
            self.unit_combo.addItem(u["name"])
        idx = self.unit_combo.findText(current)
        if idx >= 0:
            self.unit_combo.setCurrentIndex(idx)

    def add_unit_dialog(self):
        name, ok = QInputDialog.getText(self, "وحدة جديدة", "اسم الوحدة (مثلا: كرتونة، شيكارة، طبلية):")
        if ok and name.strip():
            try:
                self.db.add_unit(name.strip())
            except DatabaseError as e:
                QMessageBox.critical(self, "خطأ", str(e))
                return
            self.refresh_units()
            idx = self.unit_combo.findText(name.strip())
            if idx >= 0:
                self.unit_combo.setCurrentIndex(idx)

    def add_category_dialog(self):
        name, ok = QInputDialog.getText(self, "تصنيف جديد", "اسم التصنيف:")
        if ok and name.strip():
            try:
                self.db.add_category(name.strip())
            except DatabaseError as e:
                QMessageBox.critical(self, "خطأ", str(e))
                return
            self.refresh_categories()

    def refresh_table(self):
        term = self.search_edit.text().strip()
        try:
            products = self.db.search_products(term) if term else self.db.list_products()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        import datetime
        self.table.setRowCount(len(products))
        for row, p in enumerate(products):
            self.table.setItem(row, 0, QTableWidgetItem(p["barcode"] or ""))
            self.table.setItem(row, 1, QTableWidgetItem(p["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(f"{float(p.get('purchase_price') or 0):.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{float(p['price_tamween']):.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{float(p['price_free']):.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{float(p['price_bread']):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{float(p['price_wholesale']):.2f}"))
            qty_item = QTableWidgetItem(f"{float(p['quantity']):.2f}")
            if float(p["quantity"]) <= float(p["min_quantity"]):
                qty_item.setForeground(Qt.red)
            self.table.setItem(row, 7, qty_item)

            expiry = p.get("expiry_date")
            expiry_item = QTableWidgetItem(str(expiry) if expiry else "-")
            if expiry:
                days_left = (expiry - datetime.date.today()).days
                if days_left < 0:
                    expiry_item.setForeground(Qt.red)
                elif days_left <= 30:
                    expiry_item.setForeground(Qt.darkYellow)
            self.table.setItem(row, 8, expiry_item)

            del_btn = QPushButton("حذف")
            del_btn.clicked.connect(lambda _, pid=p["id"]: self.delete_product(pid))
            self.table.setCellWidget(row, 9, del_btn)
            # نخزن الـ id في أول عمود كبيانات مخفية
            self.table.item(row, 0).setData(Qt.UserRole, p["id"])

        self.table.resizeRowsToContents()

    def load_row_for_edit(self, row, _col):
        product_id = self.table.item(row, 0).data(Qt.UserRole)
        try:
            products = self.db.list_products()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        product = next((p for p in products if p["id"] == product_id), None)
        if not product:
            return

        self.editing_product_id = product["id"]
        self.barcode_edit.setText(product["barcode"] or "")
        self.name_edit.setText(product["name"])
        idx = self.category_combo.findData(product["category_id"])
        self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        unit_idx = self.unit_combo.findText(product["unit"] or "قطعة")
        self.unit_combo.setCurrentIndex(unit_idx if unit_idx >= 0 else 0)
        self.units_per_package_spin.setValue(int(product.get("units_per_package") or 0))
        self.price_tamween_spin.setValue(float(product["price_tamween"]))
        self.price_free_spin.setValue(float(product["price_free"]))
        self.price_bread_spin.setValue(float(product["price_bread"]))
        self.price_wholesale_spin.setValue(float(product["price_wholesale"]))
        self.purchase_price_spin.setValue(float(product.get("purchase_price") or 0))
        if product.get("expiry_date"):
            self.has_expiry_check.setChecked(True)
            self.expiry_date_edit.setDate(QDate(product["expiry_date"].year, product["expiry_date"].month, product["expiry_date"].day))
        else:
            self.has_expiry_check.setChecked(False)
            self.expiry_date_edit.setDate(QDate.currentDate())
        self.quantity_spin.setValue(float(product["quantity"]))
        self.min_quantity_spin.setValue(float(product["min_quantity"]))

    def reset_form(self):
        self.editing_product_id = None
        self.barcode_edit.clear()
        self.name_edit.clear()
        idx = self.unit_combo.findText("قطعة")
        self.unit_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.units_per_package_spin.setValue(0)
        self.price_tamween_spin.setValue(0)
        self.price_free_spin.setValue(0)
        self.price_bread_spin.setValue(0)
        self.price_wholesale_spin.setValue(0)
        self.purchase_price_spin.setValue(0)
        self.has_expiry_check.setChecked(False)
        self.expiry_date_edit.setDate(QDate.currentDate())
        self.quantity_spin.setValue(0)
        self.min_quantity_spin.setValue(0)

    def save_product(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "اسم الصنف مطلوب")
            return

        data = {
            "barcode": self.barcode_edit.text().strip() or None,
            "name": name,
            "category_id": self.category_combo.currentData(),
            "unit": self.unit_combo.currentText().strip() or "قطعة",
            "price_tamween": self.price_tamween_spin.value(),
            "price_free": self.price_free_spin.value(),
            "price_bread": self.price_bread_spin.value(),
            "price_wholesale": self.price_wholesale_spin.value(),
            "purchase_price": self.purchase_price_spin.value(),
            "expiry_date": self.expiry_date_edit.date().toString("yyyy-MM-dd") if self.has_expiry_check.isChecked() else None,
            "units_per_package": int(self.units_per_package_spin.value()) or None,
            "quantity": self.quantity_spin.value(),
            "min_quantity": self.min_quantity_spin.value(),
        }

        try:
            if self.editing_product_id:
                self.db.update_product(self.editing_product_id, data)
            else:
                self.db.add_product(data)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(self, "تم", "تم حفظ الصنف بنجاح")
        self.reset_form()
        self.refresh_table()

    def delete_product(self, product_id):
        confirm = QMessageBox.question(self, "تأكيد", "هل أنت متأكد من حذف هذا الصنف؟")
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.delete_product(product_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        self.refresh_table()
