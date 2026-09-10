# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QMessageBox, QComboBox, QDoubleSpinBox, QDialog, QFormLayout, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView
)

from database import DatabaseError
import print_utils


class ShiftTab(QWidget):
    def __init__(self, db, current_user):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_status()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_status)
        self.auto_refresh_timer.start(2000)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        status_box = QGroupBox("حالة الوردية الحالية")
        status_layout = QVBoxLayout()
        self.status_label = QLabel("جاري التحميل...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        status_layout.addWidget(self.status_label)

        self.summary_table = QTableWidget(1, 5)
        self.summary_table.setHorizontalHeaderLabels(["تموين", "حر", "عيش", "جملة", "الإجمالي"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setMaximumHeight(100)
        self.summary_table.setMinimumHeight(90)
        status_layout.addWidget(self.summary_table)

        refresh_btn = QPushButton("تحديث الحالة")
        refresh_btn.clicked.connect(self.refresh_status)
        status_layout.addWidget(refresh_btn)
        status_box.setLayout(status_layout)
        layout.addWidget(status_box)

        actions_box = QGroupBox("إجراءات")
        actions_layout = QHBoxLayout()

        self.start_shift_btn = QPushButton("بدء وردية جديدة")
        self.start_shift_btn.clicked.connect(self.open_start_shift_dialog)
        actions_layout.addWidget(self.start_shift_btn)

        handover_btn = QPushButton("تسليم الوردية لموظف آخر")
        handover_btn.clicked.connect(self.open_handover_dialog)
        actions_layout.addWidget(handover_btn)

        close_btn = QPushButton("تقفيل الوردية نهائيًا")
        close_btn.setObjectName("primaryButton")
        close_btn.clicked.connect(self.open_close_dialog)
        actions_layout.addWidget(close_btn)

        actions_box.setLayout(actions_layout)
        layout.addWidget(actions_box)

        history_box = QGroupBox("سجل التسليمات في هذه الوردية")
        history_layout = QVBoxLayout()
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(["الوقت", "من", "إلى", "قيمة الدرج", "ملاحظات"])
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        history_layout.addWidget(self.history_table)
        history_box.setLayout(history_layout)
        layout.addWidget(history_box)

        layout.addStretch()

    def refresh_status(self):
        try:
            shift = self.db.get_open_shift()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.current_shift = shift
        if not shift:
            self.status_label.setText("لا توجد وردية مفتوحة حاليًا. دوس \"بدء وردية جديدة\" (أو هتتفتح تلقائيًا لو حصل بيع من غير ما تبدأها).")
            self.start_shift_btn.setEnabled(True)
            self._fill_summary_row(None)
            self.history_table.setRowCount(0)
            return

        self.start_shift_btn.setEnabled(False)
        self.status_label.setText(
            f"وردية رقم {shift['id']} — مفتوحة منذ {shift['opened_at']} — "
            f"رأس المال: {float(shift['starting_cash']):.2f} ج.م"
        )
        try:
            summary = self.db.shift_summary(shift["id"])
            history = self.db.shift_handover_history(shift["id"])
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self._fill_summary_row(summary)

        self.history_table.setRowCount(len(history))
        for row, h in enumerate(history):
            self.history_table.setItem(row, 0, QTableWidgetItem(str(h["handover_at"])))
            self.history_table.setItem(row, 1, QTableWidgetItem(h.get("from_name") or "-"))
            self.history_table.setItem(row, 2, QTableWidgetItem(h.get("to_name") or "-"))
            drawer_text = f"{float(h['drawer_amount']):.2f}" if h.get("drawer_amount") is not None else "-"
            self.history_table.setItem(row, 3, QTableWidgetItem(drawer_text))
            self.history_table.setItem(row, 4, QTableWidgetItem(h.get("notes") or ""))

    def _fill_summary_row(self, summary):
        if not summary:
            summary = {"total_tamween": 0, "total_free": 0, "total_bread": 0, "total_wholesale": 0, "grand_total": 0}
        values = [
            summary["total_tamween"], summary["total_free"],
            summary["total_bread"], summary["total_wholesale"], summary["grand_total"],
        ]
        for col, val in enumerate(values):
            self.summary_table.setItem(0, col, QTableWidgetItem(f"{float(val):.2f}"))

    def open_start_shift_dialog(self):
        if getattr(self, "current_shift", None):
            QMessageBox.information(self, "تنبيه", "فيه وردية مفتوحة بالفعل، اقفلها الأول قبل ما تبدأ وردية جديدة")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("بدء وردية جديدة")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)

        starting_cash_spin = QDoubleSpinBox()
        starting_cash_spin.setMaximum(9999999)
        starting_cash_spin.setDecimals(2)
        starting_cash_spin.setValue(0)
        form.addRow("قيمة الدرج قبل بدء الوردية (رأس المال):", starting_cash_spin)

        hint_label = QLabel("سيبها صفر لو الدرج فاضي من الفلوس دلوقتي.")
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow(hint_label)

        confirm_btn = QPushButton("بدء الوردية")
        confirm_btn.setObjectName("primaryButton")
        form.addRow(confirm_btn)

        def do_start():
            try:
                self.db.open_shift(self.current_user["id"], starting_cash_spin.value())
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم بدء الوردية بنجاح")
            dialog.accept()
            self.refresh_status()

        confirm_btn.clicked.connect(do_start)
        dialog.exec_()

    def open_handover_dialog(self):
        if not getattr(self, "current_shift", None):
            QMessageBox.information(self, "تنبيه", "مفيش وردية مفتوحة حاليًا عشان تسلمها")
            return

        try:
            users = self.db.list_users()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("تسليم الوردية")
        dialog.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(dialog)

        to_combo = QComboBox()
        for u in users:
            if u["is_active"] and u["id"] != self.current_user["id"]:
                to_combo.addItem(u["full_name"] or u["username"], u["id"])

        drawer_spin = QDoubleSpinBox()
        drawer_spin.setMaximum(9999999)
        drawer_spin.setDecimals(2)
        try:
            summary = self.db.shift_summary(self.current_shift["id"])
            starting_cash = float(self.current_shift.get("starting_cash", 0))
            drawer_spin.setValue(round(starting_cash + float(summary["grand_total"]), 2))
        except DatabaseError:
            pass

        notes_edit = QLineEdit()

        form.addRow("تسليم الوردية إلى:", to_combo)
        form.addRow("قيمة الدرج وقت التسليم:", drawer_spin)
        form.addRow("ملاحظات (اختياري):", notes_edit)

        confirm_btn = QPushButton("تأكيد التسليم")
        confirm_btn.setObjectName("primaryButton")
        form.addRow(confirm_btn)

        def do_handover():
            to_user_id = to_combo.currentData()
            if to_user_id is None:
                QMessageBox.warning(dialog, "تنبيه", "مفيش مستخدمين تانيين مفعّلين تسلم لهم الوردية")
                return
            try:
                self.db.handover_shift(
                    self.current_shift["id"], self.current_user["id"], to_user_id,
                    drawer_spin.value(), notes_edit.text().strip()
                )
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return
            QMessageBox.information(dialog, "تم", "تم تسجيل تسليم الوردية بنجاح")
            dialog.accept()
            self.refresh_status()

        confirm_btn.clicked.connect(do_handover)
        dialog.exec_()

    def open_close_dialog(self):
        if not getattr(self, "current_shift", None):
            QMessageBox.information(self, "تنبيه", "مفيش وردية مفتوحة حاليًا عشان تقفلها")
            return

        try:
            summary = self.db.shift_summary(self.current_shift["id"])
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("تقفيل الوردية نهائيًا")
        dialog.setLayoutDirection(Qt.RightToLeft)
        layout = QVBoxLayout(dialog)

        starting_cash = float(self.current_shift.get("starting_cash", 0))
        expected_total = round(starting_cash + float(summary["grand_total"]), 2)

        report_label = QLabel(
            f"رأس المال قبل الوردية: {starting_cash:.2f} ج.م\n"
            f"عدد الفواتير: {summary['invoice_count']}\n"
            f"تموين: {float(summary['total_tamween']):.2f} ج.م\n"
            f"حر: {float(summary['total_free']):.2f} ج.م\n"
            f"عيش: {float(summary['total_bread']):.2f} ج.م\n"
            f"جملة: {float(summary['total_wholesale']):.2f} ج.م\n"
            f"الإجمالي المتوقع في الدرج (رأس المال + المبيعات): {expected_total:.2f} ج.م"
        )
        layout.addWidget(report_label)
        print_row = QHBoxLayout()

        def build_html():
            return print_utils.build_report_html(
                f"تقرير تقفيل الوردية رقم {self.current_shift['id']}",
                meta_lines=[
                    f"رأس المال قبل الوردية: {starting_cash:.2f} ج.م",
                    f"عدد الفواتير: {summary['invoice_count']}",
                ],
                footer_lines=[
                    f"تموين: {float(summary['total_tamween']):.2f} ج.م",
                    f"حر: {float(summary['total_free']):.2f} ج.م",
                    f"عيش: {float(summary['total_bread']):.2f} ج.م",
                    f"جملة: {float(summary['total_wholesale']):.2f} ج.م",
                    f"الإجمالي المتوقع في الدرج (رأس المال + المبيعات): {expected_total:.2f} ج.م",
                ],
            )

        print_utils.add_html_print_button(print_row, build_html, dialog, label="🖶 طباعة التقرير")
        layout.addLayout(print_row)

        form = QFormLayout()
        actual_cash_spin = QDoubleSpinBox()
        actual_cash_spin.setMaximum(9999999)
        actual_cash_spin.setDecimals(2)
        actual_cash_spin.setValue(expected_total)
        form.addRow("المبلغ الفعلي في الدرج:", actual_cash_spin)
        layout.addLayout(form)

        warning_label = QLabel(
            "⚠️ التقفيل النهائي هيصفّر ترقيم الفواتير من جديد للوردية القادمة. "
            "لو محتاج تسلّم الوردية لموظف تاني بس من غير ما تصفّر الترقيم، استخدم زرار \"تسليم الوردية\" بدل ده."
        )
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("color: #a15c00;")
        layout.addWidget(warning_label)

        confirm_btn = QPushButton("تأكيد التقفيل النهائي")
        confirm_btn.setObjectName("primaryButton")
        layout.addWidget(confirm_btn)

        def do_close():
            confirm = QMessageBox.question(
                dialog, "تأكيد نهائي",
                "متأكد إنك عايز تقفل الوردية نهائيًا؟ الإجراء ده مينفعش يتراجع فيه."
            )
            if confirm != QMessageBox.Yes:
                return
            try:
                result = self.db.close_shift(
                    self.current_shift["id"], self.current_user["id"], actual_cash_spin.value()
                )
            except DatabaseError as e:
                QMessageBox.critical(dialog, "خطأ", str(e))
                return

            diff = result["difference"]
            if abs(diff) < 0.01:
                diff_text = "الدرج مظبوط تمام، مفيش فرق."
            elif diff > 0:
                diff_text = f"فيه زيادة في الدرج قدرها {diff:.2f} ج.م"
            else:
                diff_text = f"فيه عجز في الدرج قدره {abs(diff):.2f} ج.م"

            QMessageBox.information(
                dialog, "تم التقفيل",
                f"تم تقفيل الوردية بنجاح.\n{diff_text}\n\n"
                "الوردية الجديدة هتتفتح تلقائيًا مع أول عملية بيع، وترقيم الفواتير هيبدأ من 1 تاني."
            )
            dialog.accept()
            self.refresh_status()

        confirm_btn.clicked.connect(do_close)
        dialog.exec_()
