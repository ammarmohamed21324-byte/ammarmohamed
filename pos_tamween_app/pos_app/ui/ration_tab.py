# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QDoubleSpinBox, QSpinBox,
    QGroupBox, QHeaderView, QLabel
)

from database import DatabaseError
from ui.barcode_dialog import BarcodeStickerDialog


class RationTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.editing_card_id = None
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_table()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_table)
        self.auto_refresh_timer.start(2000)

    def _build_ui(self):
        layout = QHBoxLayout(self)

        note = QLabel(
            "ملحوظة: هذا سجل داخلي خاص بالمحل لتتبع مبيعات الدعم لكل بطاقة، "
            "وليس اتصالاً رسميًا بمنظومة الدعم التمويني الحكومية. دبل كليك على أي بطاقة في الجدول للتعديل عليها."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #a15c00; background:#fff3e0; padding:8px; border-radius:4px;")

        self.form_box = QGroupBox("إضافة بطاقة تموين")
        form_layout = QFormLayout()
        self.card_number_edit = QLineEdit()
        self.holder_name_edit = QLineEdit()
        self.family_members_spin = QSpinBox()
        self.family_members_spin.setMinimum(1)
        self.family_members_spin.setMaximum(50)
        self.phone_edit = QLineEdit()
        self.monthly_limit_spin = QDoubleSpinBox()
        self.monthly_limit_spin.setMaximum(999999)
        self.pin_code_edit = QLineEdit()
        self.pin_code_edit.setPlaceholderText("اختياري - للمراجعة فقط")
        self.notes_edit = QLineEdit()

        form_layout.addRow("رقم البطاقة:", self.card_number_edit)
        form_layout.addRow("اسم صاحب البطاقة:", self.holder_name_edit)
        form_layout.addRow("عدد أفراد الأسرة:", self.family_members_spin)
        form_layout.addRow("رقم الهاتف:", self.phone_edit)
        form_layout.addRow("سقف شهري استرشادي (ج.م):", self.monthly_limit_spin)
        form_layout.addRow("الرقم السري (اختياري):", self.pin_code_edit)
        form_layout.addRow("ملاحظات:", self.notes_edit)

        save_btn = QPushButton("حفظ البطاقة")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.save_card)

        new_btn = QPushButton("بطاقة جديدة (تفريغ الحقول)")
        new_btn.clicked.connect(self.reset_form)

        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(new_btn)

        left_layout = QVBoxLayout()
        left_layout.addWidget(note)
        form_container = QVBoxLayout()
        form_container.addLayout(form_layout)
        form_container.addLayout(btn_row)
        self.form_box.setLayout(form_container)
        left_layout.addWidget(self.form_box)
        left_layout.addStretch()
        layout.addLayout(left_layout, 1)

        # جدول البطاقات
        table_layout = QVBoxLayout()
        refresh_btn = QPushButton("تحديث القائمة")
        refresh_btn.clicked.connect(self.refresh_table)
        table_layout.addWidget(refresh_btn)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["رقم البطاقة", "الاسم", "عدد الأفراد", "الهاتف", "مستهلك هذا الشهر", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(5, 205)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.cellDoubleClicked.connect(self.load_row_for_edit)
        table_layout.addWidget(self.table)

        layout.addLayout(table_layout, 2)

    def load_row_for_edit(self, row, _col):
        card_id = self.table.item(row, 0).data(Qt.UserRole)
        try:
            card = self.db.get_ration_card_by_id(card_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        if not card:
            return

        self.editing_card_id = card["id"]
        self.form_box.setTitle(f"تعديل بطاقة رقم {card['card_number']}")
        self.card_number_edit.setText(card["card_number"])
        self.holder_name_edit.setText(card["holder_name"] or "")
        self.family_members_spin.setValue(card["family_members"] or 1)
        self.phone_edit.setText(card["phone"] or "")
        self.monthly_limit_spin.setValue(float(card["monthly_limit"] or 0))
        self.pin_code_edit.setText(card.get("pin_code") or "")
        self.notes_edit.setText(card["notes"] or "")

    def reset_form(self):
        self.editing_card_id = None
        self.form_box.setTitle("إضافة بطاقة تموين")
        self.card_number_edit.clear()
        self.holder_name_edit.clear()
        self.phone_edit.clear()
        self.notes_edit.clear()
        self.pin_code_edit.clear()
        self.monthly_limit_spin.setValue(0)
        self.family_members_spin.setValue(1)

    def save_card(self):
        card_number = self.card_number_edit.text().strip()
        if not card_number:
            QMessageBox.warning(self, "تنبيه", "رقم البطاقة مطلوب")
            return

        data = {
            "card_number": card_number,
            "holder_name": self.holder_name_edit.text().strip(),
            "family_members": self.family_members_spin.value(),
            "phone": self.phone_edit.text().strip(),
            "monthly_limit": self.monthly_limit_spin.value(),
            "pin_code": self.pin_code_edit.text().strip() or None,
            "notes": self.notes_edit.text().strip(),
        }
        try:
            if self.editing_card_id:
                self.db.update_ration_card(self.editing_card_id, data)
            else:
                self.db.add_ration_card(data)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(self, "تم", "تم حفظ البطاقة بنجاح")
        self.reset_form()
        self.refresh_table()

    def refresh_table(self):
        try:
            cards = self.db.list_ration_cards()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.table.setRowCount(len(cards))
        for row, c in enumerate(cards):
            try:
                usage = self.db.ration_card_monthly_usage(c["id"])
            except DatabaseError:
                usage = 0.0
            self.table.setItem(row, 0, QTableWidgetItem(c["card_number"]))
            self.table.setItem(row, 1, QTableWidgetItem(c["holder_name"] or ""))
            self.table.setItem(row, 2, QTableWidgetItem(str(c["family_members"])))
            self.table.setItem(row, 3, QTableWidgetItem(c["phone"] or ""))
            self.table.setItem(row, 4, QTableWidgetItem(f"{usage:.2f} ج.م"))

            print_btn = QPushButton("طباعة باركود البطاقة")
            print_btn.clicked.connect(
                lambda _, card_number=c["card_number"], holder=c["holder_name"] or "": self.print_card_barcode(card_number, holder)
            )
            self.table.setCellWidget(row, 5, print_btn)
            self.table.item(row, 0).setData(Qt.UserRole, c["id"])

        self.table.resizeRowsToContents()

    def print_card_barcode(self, card_number, holder_name):
        dialog = BarcodeStickerDialog(
            f"بطاقة تموين: {holder_name}" if holder_name else "بطاقة تموين",
            card_number,
            subtitle_text=f"رقم البطاقة: {card_number}",
            parent=self,
        )
        dialog.exec_()
