# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QDoubleSpinBox, QGroupBox,
    QHeaderView, QLabel, QDialog, QDateEdit
)

from database import DatabaseError


class PayrollTab(QWidget):
    def __init__(self, db, current_user):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        note = QLabel(
            "الصافي المستحق = الراتب الأساسي - (السلف + الجزاءات + الغيابات) اللي لسه مش متسدّدة. "
            "لما تدوس \"صرف الراتب\"، الخصومات دي كلها بتتقفل تلقائيًا ويبدأ حساب جديد للشهر الجاي."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #a15c00; background:#fff3e0; padding:8px; border-radius:4px;")
        layout.addWidget(note)

        refresh_btn = QPushButton("تحديث القائمة")
        refresh_btn.clicked.connect(self.refresh_table)
        layout.addWidget(refresh_btn)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["الموظف", "الراتب الأساسي", "إجمالي الخصومات", "الصافي", "", "", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(4, 150)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 360)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(6, 150)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        layout.addWidget(self.table)

    def refresh_table(self):
        try:
            summary = self.db.list_payroll_summary()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.table.setRowCount(len(summary))
        for row, emp in enumerate(summary):
            self.table.setItem(row, 0, QTableWidgetItem(emp["full_name"] or emp["username"]))
            self.table.setItem(row, 1, QTableWidgetItem(f"{emp['monthly_salary']:.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{emp['total_deductions']:.2f}"))
            net_item = QTableWidgetItem(f"{emp['net_due']:.2f}")
            if emp["net_due"] < 0:
                net_item.setForeground(Qt.red)
            self.table.setItem(row, 3, net_item)

            salary_btn = QPushButton("تعديل الراتب")
            salary_btn.clicked.connect(lambda _, uid=emp["id"], name=emp["full_name"]: self.edit_salary(uid, name))
            self.table.setCellWidget(row, 4, salary_btn)

            actions_row = QHBoxLayout()
            advance_btn = QPushButton("سلفة")
            advance_btn.clicked.connect(lambda _, uid=emp["id"], name=emp["full_name"]: self.add_advance(uid, name))
            penalty_btn = QPushButton("جزاء")
            penalty_btn.clicked.connect(lambda _, uid=emp["id"], name=emp["full_name"]: self.add_penalty(uid, name))
            absence_btn = QPushButton("غياب")
            absence_btn.clicked.connect(lambda _, uid=emp["id"], name=emp["full_name"]: self.add_absence(uid, name))
            actions_widget = QWidget()
            actions_widget.setLayout(actions_row)
            actions_row.setContentsMargins(0, 0, 0, 0)
            actions_row.addWidget(advance_btn)
            actions_row.addWidget(penalty_btn)
            actions_row.addWidget(absence_btn)
            self.table.setCellWidget(row, 5, actions_widget)

            pay_btn = QPushButton("صرف الراتب")
            pay_btn.setObjectName("primaryButton")
            pay_btn.clicked.connect(lambda _, uid=emp["id"], name=emp["full_name"]: self.pay_salary(uid, name))
            self.table.setCellWidget(row, 6, pay_btn)

        self.table.resizeRowsToContents()

    def edit_salary(self, user_id, name):
        current = self.db.get_employee_salary(user_id)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"تعديل راتب {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)
        salary_spin = QDoubleSpinBox()
        salary_spin.setMaximum(999999)
        salary_spin.setDecimals(2)
        salary_spin.setValue(current)
        form.addRow("الراتب الشهري:", salary_spin)

        save_btn = QPushButton("حفظ")
        save_btn.setObjectName("primaryButton")
        form.addRow(save_btn)

        def do_save():
            try:
                self.db.set_employee_salary(user_id, salary_spin.value())
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            dialog.accept()
            self.refresh_table()

        save_btn.clicked.connect(do_save)
        dialog.exec_()

    def add_advance(self, user_id, name):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"سلفة جديدة لـ {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)
        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(999999)
        amount_spin.setDecimals(2)
        notes_edit = QLineEdit()
        form.addRow("مبلغ السلفة:", amount_spin)
        form.addRow("ملاحظات (اختياري):", notes_edit)

        save_btn = QPushButton("تسجيل السلفة")
        save_btn.setObjectName("primaryButton")
        form.addRow(save_btn)

        def do_save():
            if amount_spin.value() <= 0:
                QMessageBox.warning(dialog, "تنبيه", "المبلغ لازم يكون أكبر من صفر")
                return
            try:
                self.db.add_advance(user_id, amount_spin.value(), self.current_user["id"], notes_edit.text().strip())
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل السلفة بنجاح")
            dialog.accept()
            self.refresh_table()

        save_btn.clicked.connect(do_save)
        dialog.exec_()

    def add_penalty(self, user_id, name):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"جزاء جديد لـ {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)
        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(999999)
        amount_spin.setDecimals(2)
        reason_edit = QLineEdit()
        form.addRow("مبلغ الجزاء:", amount_spin)
        form.addRow("السبب:", reason_edit)

        save_btn = QPushButton("تسجيل الجزاء")
        save_btn.setObjectName("primaryButton")
        form.addRow(save_btn)

        def do_save():
            if amount_spin.value() <= 0:
                QMessageBox.warning(dialog, "تنبيه", "المبلغ لازم يكون أكبر من صفر")
                return
            try:
                self.db.add_penalty(user_id, amount_spin.value(), self.current_user["id"], reason_edit.text().strip())
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل الجزاء بنجاح")
            dialog.accept()
            self.refresh_table()

        save_btn.clicked.connect(do_save)
        dialog.exec_()

    def add_absence(self, user_id, name):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"تسجيل غياب لـ {name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)

        date_edit = QDateEdit(calendarPopup=True)
        date_edit.setDate(QDate.currentDate())
        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(999999)
        amount_spin.setDecimals(2)
        notes_edit = QLineEdit()
        form.addRow("تاريخ الغياب:", date_edit)
        form.addRow("قيمة الخصم:", amount_spin)
        form.addRow("ملاحظات (اختياري):", notes_edit)

        save_btn = QPushButton("تسجيل الغياب")
        save_btn.setObjectName("primaryButton")
        form.addRow(save_btn)

        def do_save():
            try:
                self.db.add_absence(
                    user_id, date_edit.date().toString("yyyy-MM-dd"), amount_spin.value(),
                    self.current_user["id"], notes_edit.text().strip()
                )
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل الغياب بنجاح")
            dialog.accept()
            self.refresh_table()

        save_btn.clicked.connect(do_save)
        dialog.exec_()

    def pay_salary(self, user_id, name):
        base_salary = self.db.get_employee_salary(user_id)
        outstanding_advances = self.db.get_outstanding_advances_total(user_id)
        outstanding_penalties = self.db.get_outstanding_penalties_total(user_id)
        outstanding_absences = self.db.get_outstanding_absences_total(user_id)
        total_deductions = outstanding_advances + outstanding_penalties + outstanding_absences
        net = round(base_salary - total_deductions, 2)

        confirm = QMessageBox.question(
            self, "تأكيد صرف الراتب",
            f"راتب {name} الأساسي: {base_salary:.2f} ج.م\n"
            f"السلف المستحقة: {outstanding_advances:.2f} ج.م\n"
            f"الجزاءات المستحقة: {outstanding_penalties:.2f} ج.م\n"
            f"خصومات الغياب: {outstanding_absences:.2f} ج.م\n"
            f"الصافي المستحق دفعه: {net:.2f} ج.م\n\n"
            "هل تأكد إنك عايز تصرف الراتب وتقفل كل الخصومات دي؟"
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            result = self.db.pay_salary(user_id, self.current_user["id"])
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(
            self, "تم الصرف",
            f"تم صرف صافي {result['net_paid']:.2f} ج.م لـ {name} بنجاح.\nكل الخصومات اتقفلت وهيبدأ حساب جديد."
        )
        self.refresh_table()
