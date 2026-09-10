# -*- coding: utf-8 -*-
import datetime
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QDateEdit, QLabel, QGroupBox, QHeaderView,
    QComboBox, QLineEdit, QDialog, QScrollArea
)

import print_utils
import config
import printer
from database import DatabaseError


class ReportsTab(QWidget):
    def __init__(self, db, current_user=None, can_cancel=False):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.can_cancel = can_cancel
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_employees_list()
        self.employee_combo.currentIndexChanged.connect(self.run_report)
        self.run_report()

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.run_report)
        self.auto_refresh_timer.start(2000)

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        outer_layout.addWidget(scroll_area)

        inner_widget = QWidget()
        scroll_area.setWidget(inner_widget)
        layout = QVBoxLayout(inner_widget)

        filter_row = QHBoxLayout()
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDate(datetime.date.today().replace(day=1))
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDate(datetime.date.today())
        run_btn = QPushButton("عرض التقرير")
        run_btn.clicked.connect(self.run_report)

        filter_row.addWidget(QLabel("من:"))
        filter_row.addWidget(self.date_from)
        filter_row.addWidget(QLabel("إلى:"))
        filter_row.addWidget(self.date_to)
        filter_row.addWidget(run_btn)

        filter_row.addSpacing(20)
        filter_row.addWidget(QLabel("أداء موظف:"))
        self.employee_combo = QComboBox()
        self.employee_combo.addItem("كل الموظفين (بدون تفصيل)", None)
        filter_row.addWidget(self.employee_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        print_report_btn = QPushButton("🖶 طباعة التقرير")
        print_report_btn.clicked.connect(self._print_full_report)
        layout.addWidget(print_report_btn)

        closing_row = QHBoxLayout()
        close_month_btn = QPushButton("📅 تقفيل الشهر (تقرير مفصّل بكل الفواتير)")
        close_month_btn.clicked.connect(lambda: self.open_period_closing_report("month"))
        close_year_btn = QPushButton("📆 تقفيل السنة (تقرير مفصّل بكل الفواتير)")
        close_year_btn.clicked.connect(lambda: self.open_period_closing_report("year"))
        closing_row.addWidget(close_month_btn)
        closing_row.addWidget(close_year_btn)
        layout.addLayout(closing_row)

        stocktake_row = QHBoxLayout()
        stocktake_day_btn = QPushButton("📦 جرد يومي")
        stocktake_day_btn.clicked.connect(lambda: self.open_stocktake_report("يومي"))
        stocktake_month_btn = QPushButton("📦 جرد شهري")
        stocktake_month_btn.clicked.connect(lambda: self.open_stocktake_report("شهري"))
        stocktake_year_btn = QPushButton("📦 جرد سنوي")
        stocktake_year_btn.clicked.connect(lambda: self.open_stocktake_report("سنوي"))
        stocktake_row.addWidget(stocktake_day_btn)
        stocktake_row.addWidget(stocktake_month_btn)
        stocktake_row.addWidget(stocktake_year_btn)
        layout.addLayout(stocktake_row)

        profit_btn = QPushButton("💰 تقرير الأرباح (سعر الشراء مقابل سعر البيع الفعلي)")
        profit_btn.clicked.connect(self.open_profit_report)
        layout.addWidget(profit_btn)

        tamween_report_btn = QPushButton("🖶 طباعة تقرير التموين")
        tamween_report_btn.clicked.connect(self.open_tamween_report)
        layout.addWidget(tamween_report_btn)

        self.report_content_widget = QWidget()
        self.report_content_widget.setStyleSheet("background: white;")
        report_layout = QVBoxLayout(self.report_content_widget)
        report_layout.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 8px 0;")
        report_layout.addWidget(self.summary_label)

        content_row = QHBoxLayout()

        daily_box = QGroupBox("المبيعات اليومية")
        daily_layout = QVBoxLayout()
        self.daily_table = QTableWidget(0, 7)
        self.daily_table.setMinimumHeight(260)
        self.daily_table.setHorizontalHeaderLabels(
            ["اليوم", "تموين", "حر", "عيش", "جملة", "الإجمالي", "عدد الفواتير"]
        )
        self.daily_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        daily_layout.addWidget(self.daily_table)
        print_utils.add_html_print_button(daily_layout, self._build_daily_html, self, label="🖶 طباعة الجدول ده")
        daily_box.setLayout(daily_layout)
        content_row.addWidget(daily_box, 1)

        best_box = QGroupBox("الأصناف الأكثر مبيعًا")
        best_layout = QVBoxLayout()
        best_search_row = QHBoxLayout()
        self.best_search_edit = QLineEdit()
        self.best_search_edit.setPlaceholderText("بحث باسم الصنف...")
        self.best_search_edit.textChanged.connect(self._refresh_best_table)
        best_search_row.addWidget(self.best_search_edit)
        best_layout.addLayout(best_search_row)
        self.best_table = QTableWidget(0, 4)
        self.best_table.setMinimumHeight(260)
        self.best_table.setHorizontalHeaderLabels(["الصنف", "الكمية المباعة", "القيمة", "الربح التقديري"])
        self.best_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        best_layout.addWidget(self.best_table)
        print_utils.add_html_print_button(best_layout, self._build_best_html, self, label="🖶 طباعة الجدول ده")
        best_box.setLayout(best_layout)
        content_row.addWidget(best_box, 1)

        payment_box = QGroupBox("المبيعات حسب طريقة الدفع")
        payment_layout = QVBoxLayout()
        self.payment_method_table = QTableWidget(0, 3)
        self.payment_method_table.setMinimumHeight(260)
        self.payment_method_table.setHorizontalHeaderLabels(["طريقة الدفع", "عدد الفواتير", "الإجمالي"])
        self.payment_method_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        payment_layout.addWidget(self.payment_method_table)
        print_utils.add_html_print_button(payment_layout, self._build_payment_html, self, label="🖶 طباعة الجدول ده")
        payment_box.setLayout(payment_layout)
        content_row.addWidget(payment_box, 1)

        report_layout.addLayout(content_row)

        low_stock_box = QGroupBox("أصناف قاربت على النفاذ")
        low_stock_layout = QVBoxLayout()
        self.low_stock_table = QTableWidget(0, 3)
        self.low_stock_table.setMinimumHeight(200)
        self.low_stock_table.setHorizontalHeaderLabels(["الصنف", "الكمية الحالية", "حد التنبيه"])
        self.low_stock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        low_stock_layout.addWidget(self.low_stock_table)
        print_utils.add_html_print_button(low_stock_layout, self._build_low_stock_html, self, label="🖶 طباعة الجدول ده")
        low_stock_box.setLayout(low_stock_layout)
        report_layout.addWidget(low_stock_box)

        expiry_box = QGroupBox("أصناف قريبة من انتهاء الصلاحية (خلال 30 يوم أو منتهية بالفعل)")
        expiry_layout = QVBoxLayout()
        self.expiry_table = QTableWidget(0, 3)
        self.expiry_table.setMinimumHeight(200)
        self.expiry_table.setHorizontalHeaderLabels(["الصنف", "تاريخ الصلاحية", "الكمية المتاحة"])
        self.expiry_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        expiry_layout.addWidget(self.expiry_table)
        print_utils.add_html_print_button(expiry_layout, self._build_expiry_html, self, label="🖶 طباعة الجدول ده")
        expiry_box.setLayout(expiry_layout)
        report_layout.addWidget(expiry_box)

        self.employee_box = QGroupBox("أداء الموظف المحدد")
        employee_layout = QVBoxLayout()
        self.employee_summary_label = QLabel("")
        self.employee_summary_label.setWordWrap(True)
        self.employee_summary_label.setStyleSheet("font-size: 13px; font-weight: 600; margin-bottom: 6px;")
        employee_layout.addWidget(self.employee_summary_label)

        self.employee_shifts_table = QTableWidget(0, 6)
        self.employee_shifts_table.setHorizontalHeaderLabels(
            ["رقم الوردية", "عدد فواتيره", "مبيعاته في الوردية", "حالة الوردية", "المتوقع بالدرج", "الفعلي بالدرج"]
        )
        self.employee_shifts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        employee_layout.addWidget(self.employee_shifts_table)

        self.employee_box.setLayout(employee_layout)
        self.employee_box.setVisible(False)
        report_layout.addWidget(self.employee_box)

        layout.addWidget(self.report_content_widget)

        invoice_box = QGroupBox("البحث عن فاتورة ومراجعتها")
        invoice_layout = QVBoxLayout()

        search_row = QHBoxLayout()
        self.invoice_search_edit = QLineEdit()
        self.invoice_search_edit.setPlaceholderText("رقم الفاتورة (اتركه فاضي لعرض كل فواتير الفترة المحددة فوق)")
        search_btn = QPushButton("بحث")
        search_btn.clicked.connect(self.search_invoices)
        search_row.addWidget(self.invoice_search_edit)
        search_row.addWidget(search_btn)
        invoice_layout.addLayout(search_row)

        self.invoices_table = QTableWidget(0, 6)
        self.invoices_table.setMinimumHeight(260)
        self.invoices_table.setHorizontalHeaderLabels(
            ["رقم الفاتورة", "التاريخ", "الكاشير", "الإجمالي الصافي", "الحالة", ""]
        )
        self.invoices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.invoices_table.setColumnWidth(5, 160)
        self.invoices_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        invoice_layout.addWidget(self.invoices_table)

        invoice_box.setLayout(invoice_layout)
        layout.addWidget(invoice_box)

    def _build_daily_html(self):
        rows = [
            [str(r["day"]), f"{float(r['total_tamween']):.2f}", f"{float(r['total_free']):.2f}",
             f"{float(r['total_bread']):.2f}", f"{float(r['total_wholesale']):.2f}",
             f"{float(r['grand_total']):.2f}", str(r["invoice_count"])]
            for r in getattr(self, "_last_daily", [])
        ]
        return print_utils.build_report_html(
            "المبيعات اليومية",
            sections=[{
                "headers": ["اليوم", "تموين", "حر", "عيش", "جملة", "الإجمالي", "عدد الفواتير"],
                "rows": rows,
            }],
        )

    def _build_best_html(self):
        rows = [
            [r["name"], f"{float(r['total_qty']):.2f}", f"{float(r['total_value']):.2f}",
             f"{float(r.get('estimated_profit') or 0):.2f}"]
            for r in getattr(self, "_last_best", [])
        ]
        return print_utils.build_report_html(
            "الأصناف الأكثر مبيعًا",
            sections=[{"headers": ["الصنف", "الكمية المباعة", "القيمة", "الربح التقديري"], "rows": rows}],
        )

    def _build_payment_html(self):
        payment_labels = {"cash": "كاش", "credit": "آجل", "visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}
        rows = [
            [payment_labels.get(r["payment_method"], r["payment_method"]), str(r["invoice_count"]), f"{float(r['total']):.2f}"]
            for r in getattr(self, "_last_payment_breakdown", [])
        ]
        return print_utils.build_report_html(
            "المبيعات حسب طريقة الدفع",
            sections=[{"headers": ["طريقة الدفع", "عدد الفواتير", "الإجمالي"], "rows": rows}],
        )

    def _build_low_stock_html(self):
        rows = [
            [p["name"], f"{float(p['quantity']):.2f}", f"{float(p['min_quantity']):.2f}"]
            for p in getattr(self, "_last_low_stock", [])
        ]
        return print_utils.build_report_html(
            "أصناف قاربت على النفاذ",
            sections=[{"headers": ["الصنف", "الكمية الحالية", "حد التنبيه"], "rows": rows}],
        )

    def _build_expiry_html(self):
        rows = [
            [p["name"], str(p["expiry_date"]), f"{float(p['quantity']):.2f}"]
            for p in getattr(self, "_last_expiring", [])
        ]
        return print_utils.build_report_html(
            "أصناف قريبة من انتهاء الصلاحية",
            sections=[{"headers": ["الصنف", "تاريخ الصلاحية", "الكمية المتاحة"], "rows": rows}],
        )

    def refresh_employees_list(self):
        try:
            users = self.db.list_users()
        except DatabaseError:
            return
        current = self.employee_combo.currentData()
        self.employee_combo.blockSignals(True)
        self.employee_combo.clear()
        self.employee_combo.addItem("كل الموظفين (بدون تفصيل)", None)
        for u in users:
            self.employee_combo.addItem(u["full_name"] or u["username"], u["id"])
        idx = self.employee_combo.findData(current)
        self.employee_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.employee_combo.blockSignals(False)

    def _print_full_report(self):
        if not hasattr(self, "_last_daily"):
            QMessageBox.information(self, "تنبيه", "اعرض التقرير الأول قبل الطباعة")
            return

        date_from, date_to = self._last_report_range
        payment_labels = {"cash": "كاش", "credit": "آجل", "visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}

        daily_rows = [
            [str(r["day"]), f"{float(r['total_tamween']):.2f}", f"{float(r['total_free']):.2f}",
             f"{float(r['total_bread']):.2f}", f"{float(r['total_wholesale']):.2f}",
             f"{float(r['grand_total']):.2f}", str(r["invoice_count"])]
            for r in self._last_daily
        ]
        best_rows = [
            [r["name"], f"{float(r['total_qty']):.2f}", f"{float(r['total_value']):.2f}",
             f"{float(r.get('estimated_profit') or 0):.2f}"]
            for r in getattr(self, "_last_best", [])
        ]
        payment_rows = [
            [payment_labels.get(r["payment_method"], r["payment_method"]), str(r["invoice_count"]), f"{float(r['total']):.2f}"]
            for r in self._last_payment_breakdown
        ]
        low_stock_rows = [
            [p["name"], f"{float(p['quantity']):.2f}", f"{float(p['min_quantity']):.2f}"]
            for p in self._last_low_stock
        ]
        expiry_rows = [
            [p["name"], str(p["expiry_date"]), f"{float(p['quantity']):.2f}"]
            for p in self._last_expiring
        ]

        total_tamween = sum(float(r["total_tamween"]) for r in self._last_daily)
        total_free = sum(float(r["total_free"]) for r in self._last_daily)
        total_bread = sum(float(r["total_bread"]) for r in self._last_daily)
        total_wholesale = sum(float(r["total_wholesale"]) for r in self._last_daily)
        grand_total = sum(float(r["grand_total"]) for r in self._last_daily)

        html = print_utils.build_report_html(
            "تقرير المبيعات",
            meta_lines=[f"من {date_from} إلى {date_to}"],
            sections=[
                {"heading": "المبيعات اليومية",
                 "headers": ["اليوم", "تموين", "حر", "عيش", "جملة", "الإجمالي", "عدد الفواتير"],
                 "rows": daily_rows},
                {"heading": "الأصناف الأكثر مبيعًا",
                 "headers": ["الصنف", "الكمية المباعة", "القيمة", "الربح التقديري"],
                 "rows": best_rows},
                {"heading": "المبيعات حسب طريقة الدفع",
                 "headers": ["طريقة الدفع", "عدد الفواتير", "الإجمالي"],
                 "rows": payment_rows},
                {"heading": "أصناف قاربت على النفاذ",
                 "headers": ["الصنف", "الكمية الحالية", "حد التنبيه"],
                 "rows": low_stock_rows},
                {"heading": "أصناف قريبة من انتهاء الصلاحية",
                 "headers": ["الصنف", "تاريخ الصلاحية", "الكمية المتاحة"],
                 "rows": expiry_rows},
            ],
            footer_lines=[
                f"تموين: {total_tamween:.2f} ج.م",
                f"حر: {total_free:.2f} ج.م",
                f"عيش: {total_bread:.2f} ج.م",
                f"جملة: {total_wholesale:.2f} ج.م",
                f"الإجمالي الكلي للفترة: {grand_total:.2f} ج.م",
                f"عدد بطاقات التموين المميزة اللي ضربت خلال الفترة: {getattr(self, '_last_tamween_cards', 0)}",
            ],
        )
        print_utils.print_html(html, self)

    def _refresh_best_table(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        search_term = self.best_search_edit.text().strip()

        try:
            best = self.db.best_selling_products(
                date_from, date_to,
                limit=200 if search_term else 20,
                name_filter=search_term or None,
            )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.best_table.setRowCount(len(best))
        for row, r in enumerate(best):
            self.best_table.setItem(row, 0, QTableWidgetItem(r["name"]))
            self.best_table.setItem(row, 1, QTableWidgetItem(f"{float(r['total_qty']):.2f}"))
            self.best_table.setItem(row, 2, QTableWidgetItem(f"{float(r['total_value']):.2f}"))
            self.best_table.setItem(row, 3, QTableWidgetItem(f"{float(r.get('estimated_profit') or 0):.2f}"))
        self._last_best = best

    def run_report(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")

        try:
            daily = self.db.sales_report(date_from, date_to)
            low_stock = self.db.low_stock_products()
            payment_breakdown = self.db.payment_method_report(date_from, date_to)
            expiring = self.db.products_expiring_soon(30)
            tamween_cards = self.db.tamween_cards_used_count(date_from, date_to)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self._last_report_range = (date_from, date_to)
        self._last_daily = daily
        self._last_low_stock = low_stock
        self._last_payment_breakdown = payment_breakdown
        self._last_expiring = expiring
        self._last_tamween_cards = tamween_cards

        total_tamween = sum(float(r["total_tamween"]) for r in daily)
        total_free = sum(float(r["total_free"]) for r in daily)
        total_bread = sum(float(r["total_bread"]) for r in daily)
        total_wholesale = sum(float(r["total_wholesale"]) for r in daily)
        grand_total = sum(float(r["grand_total"]) for r in daily)
        self.summary_label.setText(
            f"إجمالي الفترة: تموين {total_tamween:.2f} | حر {total_free:.2f} | "
            f"عيش {total_bread:.2f} | جملة {total_wholesale:.2f} | الإجمالي {grand_total:.2f} ج.م | "
            f"عدد بطاقات ضربت تموين: {tamween_cards}"
        )

        self.daily_table.setRowCount(len(daily))
        for row, r in enumerate(daily):
            self.daily_table.setItem(row, 0, QTableWidgetItem(str(r["day"])))
            self.daily_table.setItem(row, 1, QTableWidgetItem(f"{float(r['total_tamween']):.2f}"))
            self.daily_table.setItem(row, 2, QTableWidgetItem(f"{float(r['total_free']):.2f}"))
            self.daily_table.setItem(row, 3, QTableWidgetItem(f"{float(r['total_bread']):.2f}"))
            self.daily_table.setItem(row, 4, QTableWidgetItem(f"{float(r['total_wholesale']):.2f}"))
            self.daily_table.setItem(row, 5, QTableWidgetItem(f"{float(r['grand_total']):.2f}"))
            self.daily_table.setItem(row, 6, QTableWidgetItem(str(r["invoice_count"])))

        self._refresh_best_table()

        payment_labels = {"cash": "كاش", "credit": "آجل", "visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}
        self.payment_method_table.setRowCount(len(payment_breakdown))
        for row, r in enumerate(payment_breakdown):
            self.payment_method_table.setItem(row, 0, QTableWidgetItem(payment_labels.get(r["payment_method"], r["payment_method"])))
            self.payment_method_table.setItem(row, 1, QTableWidgetItem(str(r["invoice_count"])))
            self.payment_method_table.setItem(row, 2, QTableWidgetItem(f"{float(r['total']):.2f}"))

        self.low_stock_table.setRowCount(len(low_stock))
        for row, p in enumerate(low_stock):
            self.low_stock_table.setItem(row, 0, QTableWidgetItem(p["name"]))
            self.low_stock_table.setItem(row, 1, QTableWidgetItem(f"{float(p['quantity']):.2f}"))
            self.low_stock_table.setItem(row, 2, QTableWidgetItem(f"{float(p['min_quantity']):.2f}"))

        import datetime as _dt
        self.expiry_table.setRowCount(len(expiring))
        for row, p in enumerate(expiring):
            self.expiry_table.setItem(row, 0, QTableWidgetItem(p["name"]))
            expiry_item = QTableWidgetItem(str(p["expiry_date"]))
            if p["expiry_date"] < _dt.date.today():
                expiry_item.setForeground(Qt.red)
            else:
                expiry_item.setForeground(Qt.darkYellow)
            self.expiry_table.setItem(row, 1, expiry_item)
            self.expiry_table.setItem(row, 2, QTableWidgetItem(f"{float(p['quantity']):.2f}"))

        self._refresh_employee_performance(date_from, date_to)
        self.search_invoices()

    def _refresh_employee_performance(self, date_from, date_to):
        employee_id = self.employee_combo.currentData()
        if not employee_id:
            self.employee_box.setVisible(False)
            return

        try:
            perf = self.db.employee_performance_report(employee_id, date_from, date_to)
            shifts = self.db.employee_shifts_breakdown(employee_id, date_from, date_to)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.employee_box.setVisible(True)
        self.employee_summary_label.setText(
            f"عدد الفواتير: {perf['invoice_count']} | عدد الورديات: {perf['shifts_worked']} | "
            f"بطاقات تموين استخدمها: {perf['ration_cards_used']}\n"
            f"مبيعاته: تموين {float(perf['total_tamween']):.2f} | حر {float(perf['total_free']):.2f} | "
            f"عيش {float(perf['total_bread']):.2f} | جملة {float(perf['total_wholesale']):.2f} | "
            f"الإجمالي {float(perf['grand_total']):.2f} ج.م"
        )

        self.employee_shifts_table.setRowCount(len(shifts))
        for row, s in enumerate(shifts):
            self.employee_shifts_table.setItem(row, 0, QTableWidgetItem(str(s["shift_id"])))
            self.employee_shifts_table.setItem(row, 1, QTableWidgetItem(str(s["invoice_count"])))
            self.employee_shifts_table.setItem(row, 2, QTableWidgetItem(f"{float(s['employee_sales']):.2f}"))
            status_text = {"open": "مفتوحة", "closed": "مقفولة"}.get(s["status"], "-")
            self.employee_shifts_table.setItem(row, 3, QTableWidgetItem(status_text))
            expected = f"{float(s['expected_cash']):.2f}" if s["expected_cash"] is not None else "-"
            actual = f"{float(s['actual_cash']):.2f}" if s["actual_cash"] is not None else "-"
            self.employee_shifts_table.setItem(row, 4, QTableWidgetItem(expected))
            self.employee_shifts_table.setItem(row, 5, QTableWidgetItem(actual))

    def open_tamween_report(self):
        default_from = self.date_from.date()
        default_to = self.date_to.date()
        self._render_tamween_report(default_from, default_to)

    def _render_tamween_report(self, from_qdate, to_qdate, existing_dialog=None):
        date_from = from_qdate.toString("yyyy-MM-dd")
        date_to = to_qdate.toString("yyyy-MM-dd")

        try:
            data = self.db.tamween_report(date_from, date_to)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        if existing_dialog:
            existing_dialog.close()

        dialog = QDialog(self)
        dialog.setWindowTitle("تقرير التموين")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(480, 300)
        layout = QVBoxLayout(dialog)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("من:"))
        from_edit = QDateEdit(calendarPopup=True)
        from_edit.setDate(from_qdate)
        range_row.addWidget(from_edit)
        range_row.addWidget(QLabel("إلى:"))
        to_edit = QDateEdit(calendarPopup=True)
        to_edit.setDate(to_qdate)
        range_row.addWidget(to_edit)
        show_btn = QPushButton("عرض")
        show_btn.clicked.connect(lambda: self._render_tamween_report(from_edit.date(), to_edit.date(), dialog))
        range_row.addWidget(show_btn)
        range_row.addStretch()
        layout.addLayout(range_row)

        header = QLabel(f"تقرير التموين — من {date_from} إلى {date_to}")
        header.setStyleSheet("font-weight: 600;")
        layout.addWidget(header)

        table = QTableWidget(1, 2)
        table.setHorizontalHeaderLabels(["عدد البطاقات", "إجمالي الفلوس"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setItem(0, 0, QTableWidgetItem(str(data["card_count"])))
        table.setItem(0, 1, QTableWidgetItem(f"{data['total_amount']:.2f} ج.م"))
        layout.addWidget(table)

        def build_html():
            return print_utils.build_report_html(
                "تقرير التموين",
                meta_lines=[f"من {date_from} إلى {date_to}"],
                sections=[{
                    "headers": ["عدد البطاقات", "إجمالي الفلوس"],
                    "rows": [[str(data["card_count"]), f"{data['total_amount']:.2f} ج.م"]],
                }],
            )

        print_row = QHBoxLayout()
        print_utils.add_html_print_button(print_row, build_html, dialog)
        layout.addLayout(print_row)

        dialog.exec_()

    def open_profit_report(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")

        try:
            rows_data = self.db.profit_report(date_from, date_to)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        if not rows_data:
            QMessageBox.information(self, "تنبيه", "مفيش مبيعات في الفترة المحددة فوق")
            return

        total_cost = sum(r["total_cost"] for r in rows_data)
        total_revenue = sum(r["total_revenue"] for r in rows_data)
        total_profit = sum(r["profit"] for r in rows_data)

        dialog = QDialog(self)
        dialog.setWindowTitle("تقرير الأرباح")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(750, 600)
        layout = QVBoxLayout(dialog)

        header = QLabel(
            f"تقرير الأرباح — من {date_from} إلى {date_to}\n"
            f"إجمالي سعر الشراء: {total_cost:.2f} ج.م | إجمالي المبيعات: {total_revenue:.2f} ج.م | "
            f"إجمالي المكسب: {total_profit:.2f} ج.م"
        )
        header.setStyleSheet("font-weight: 600;")
        layout.addWidget(header)

        table = QTableWidget(len(rows_data), 6)
        table.setHorizontalHeaderLabels(
            ["الصنف", "سعر الشراء", "الكمية المباعة", "إجمالي سعر الشراء", "إجمالي البيع الفعلي", "المكسب"]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, r in enumerate(rows_data):
            table.setItem(row, 0, QTableWidgetItem(r["name"]))
            table.setItem(row, 1, QTableWidgetItem(f"{float(r['purchase_price'] or 0):.2f}"))
            table.setItem(row, 2, QTableWidgetItem(f"{r['total_qty']:g}"))
            table.setItem(row, 3, QTableWidgetItem(f"{r['total_cost']:.2f}"))
            table.setItem(row, 4, QTableWidgetItem(f"{r['total_revenue']:.2f}"))
            profit_item = QTableWidgetItem(f"{r['profit']:.2f}")
            profit_item.setForeground(Qt.darkGreen if r["profit"] >= 0 else Qt.red)
            table.setItem(row, 5, profit_item)
        layout.addWidget(table)

        def build_html():
            rows = [
                [r["name"], f"{float(r['purchase_price'] or 0):.2f}", f"{r['total_qty']:g}",
                 f"{r['total_cost']:.2f}", f"{r['total_revenue']:.2f}", f"{r['profit']:.2f}"]
                for r in rows_data
            ]
            return print_utils.build_report_html(
                "تقرير الأرباح",
                meta_lines=[f"من {date_from} إلى {date_to}"],
                sections=[{
                    "headers": ["الصنف", "سعر الشراء", "الكمية المباعة", "إجمالي سعر الشراء",
                                "إجمالي البيع الفعلي", "المكسب"],
                    "rows": rows,
                }],
                footer_lines=[
                    f"إجمالي سعر الشراء: {total_cost:.2f} ج.م",
                    f"إجمالي المبيعات: {total_revenue:.2f} ج.م",
                    f"إجمالي المكسب: {total_profit:.2f} ج.م",
                ],
            )

        print_row = QHBoxLayout()
        print_utils.add_html_print_button(print_row, build_html, dialog)
        layout.addLayout(print_row)

        dialog.exec_()

    def open_stocktake_report(self, period_label):
        now = datetime.datetime.now()
        today = now.date()
        if period_label == "يومي":
            period_text = f"جرد يومي - {today.isoformat()}"
            date_from, date_to = today, today
        elif period_label == "شهري":
            period_text = f"جرد شهري - {now.strftime('%m/%Y')}"
            date_from, date_to = today.replace(day=1), today
        else:
            period_text = f"جرد سنوي - سنة {now.year}"
            date_from, date_to = today.replace(month=1, day=1), today

        try:
            products = self.db.inventory_stocktake_report(date_from.isoformat(), date_to.isoformat())
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(period_text)
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(600, 600)
        layout = QVBoxLayout(dialog)

        header = QLabel(
            f"{period_text}\n"
            f"تاريخ ووقت الجرد: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"عدد الأصناف: {len(products)}"
        )
        header.setStyleSheet("font-weight: 600;")
        layout.addWidget(header)

        table = QTableWidget(len(products), 3)
        table.setHorizontalHeaderLabels(["الصنف", "المباع", "المتبقي"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, p in enumerate(products):
            table.setItem(row, 0, QTableWidgetItem(p["name"]))
            table.setItem(row, 1, QTableWidgetItem(f"{p['sold']:g}"))
            table.setItem(row, 2, QTableWidgetItem(f"{p['remaining']:g}"))
        layout.addWidget(table)

        def build_html():
            rows = [[p["name"], f"{p['sold']:g}", f"{p['remaining']:g}"] for p in products]
            return print_utils.build_report_html(
                period_text,
                meta_lines=[f"تاريخ ووقت الجرد: {now.strftime('%Y-%m-%d %H:%M')}", f"عدد الأصناف: {len(products)}"],
                sections=[{"headers": ["الصنف", "المباع", "المتبقي"], "rows": rows}],
            )

        print_row = QHBoxLayout()
        print_utils.add_html_print_button(print_row, build_html, dialog)
        layout.addLayout(print_row)

        dialog.exec_()

    def open_period_closing_report(self, period):
        today = datetime.date.today()
        if period == "month":
            date_from = today.replace(day=1)
            period_label = f"شهر {today.month}/{today.year}"
        else:
            date_from = today.replace(month=1, day=1)
            period_label = f"سنة {today.year}"
        date_to = today

        try:
            invoices = self.db.search_invoices(date_from.isoformat(), date_to.isoformat())
            tamween_cards = self.db.tamween_cards_used_count(date_from.isoformat(), date_to.isoformat())
            tamween_data = self.db.tamween_report(date_from.isoformat(), date_to.isoformat())
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        if not invoices:
            QMessageBox.information(self, "تنبيه", "مفيش فواتير في الفترة دي")
            return

        active_invoices = [i for i in invoices if i["status"] == "active"]
        total_tamween = sum(float(i["total_tamween"]) for i in active_invoices)
        total_free = sum(float(i["total_free"]) for i in active_invoices)
        total_bread = sum(float(i["total_bread"]) for i in active_invoices)
        total_wholesale = sum(float(i["total_wholesale"]) for i in active_invoices)
        grand_total = sum(float(i["net_total"] if i["net_total"] is not None else i["grand_total"]) for i in active_invoices)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"تقفيل {period_label}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(650, 550)
        layout = QVBoxLayout(dialog)

        header = QLabel(
            f"تقرير تقفيل {period_label}\n"
            f"من {date_from} إلى {date_to}\n"
            f"عدد الفواتير: {len(invoices)} (نشطة: {len(active_invoices)})\n"
            f"عدد بطاقات التموين المميزة اللي ضربت: {tamween_cards}\n"
            f"إجمالي فلوس التموين المباعة: {tamween_data['total_amount']:.2f} ج.م\n\n"
            f"إجمالي التموين: {total_tamween:.2f} ج.م\n"
            f"إجمالي الحر: {total_free:.2f} ج.م\n"
            f"إجمالي العيش: {total_bread:.2f} ج.م\n"
            f"إجمالي الجملة: {total_wholesale:.2f} ج.م\n"
            f"الإجمالي الكلي للفترة: {grand_total:.2f} ج.م"
        )
        header.setStyleSheet("font-weight: 600;")
        layout.addWidget(header)

        table = QTableWidget(len(invoices), 6)
        table.setHorizontalHeaderLabels(["رقم الفاتورة", "التاريخ", "الكاشير", "طريقة الدفع", "الصافي", "الحالة"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        payment_labels = {"cash": "كاش", "credit": "آجل", "visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}
        for row, inv in enumerate(invoices):
            table.setItem(row, 0, QTableWidgetItem(inv["invoice_number"]))
            table.setItem(row, 1, QTableWidgetItem(str(inv["created_at"])))
            table.setItem(row, 2, QTableWidgetItem(inv.get("cashier_name") or "-"))
            table.setItem(row, 3, QTableWidgetItem(payment_labels.get(inv.get("payment_method"), "-")))
            net = inv["net_total"] if inv["net_total"] is not None else inv["grand_total"]
            table.setItem(row, 4, QTableWidgetItem(f"{float(net):.2f}"))
            status_item = QTableWidgetItem("ملغاة" if inv["status"] == "cancelled" else "نشطة")
            if inv["status"] == "cancelled":
                status_item.setForeground(Qt.red)
            table.setItem(row, 5, status_item)
        layout.addWidget(table)

        def build_html():
            rows = []
            for inv in invoices:
                net = inv["net_total"] if inv["net_total"] is not None else inv["grand_total"]
                rows.append([
                    inv["invoice_number"], str(inv["created_at"]), inv.get("cashier_name") or "-",
                    payment_labels.get(inv.get("payment_method"), "-"), f"{float(net):.2f}",
                    "ملغاة" if inv["status"] == "cancelled" else "نشطة",
                ])
            return print_utils.build_report_html(
                f"تقرير تقفيل {period_label}",
                meta_lines=[
                    f"من {date_from} إلى {date_to}",
                    f"عدد الفواتير: {len(invoices)} (نشطة: {len(active_invoices)})",
                    f"عدد بطاقات التموين المميزة اللي ضربت: {tamween_cards}",
                    f"إجمالي فلوس التموين المباعة: {tamween_data['total_amount']:.2f} ج.م",
                ],
                sections=[{
                    "headers": ["رقم الفاتورة", "التاريخ", "الكاشير", "طريقة الدفع", "الصافي", "الحالة"],
                    "rows": rows,
                }],
                footer_lines=[
                    f"إجمالي التموين: {total_tamween:.2f} ج.م",
                    f"إجمالي الحر: {total_free:.2f} ج.م",
                    f"إجمالي العيش: {total_bread:.2f} ج.م",
                    f"إجمالي الجملة: {total_wholesale:.2f} ج.م",
                    f"الإجمالي الكلي للفترة: {grand_total:.2f} ج.م",
                ],
            )

        btn_row = QHBoxLayout()
        print_utils.add_html_print_button(btn_row, build_html, dialog)
        confirm_btn = QPushButton(f"تسجيل تقفيل {period_label} في سجل الحركة")
        confirm_btn.setObjectName("primaryButton")
        confirm_btn.clicked.connect(lambda: self._confirm_period_closing(period_label, grand_total, len(active_invoices), dialog))
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

        dialog.exec_()

    def _confirm_period_closing(self, period_label, grand_total, invoice_count, dialog):
        try:
            self.db.log_activity(
                self.current_user["id"] if self.current_user else None,
                "close_period",
                f"تقفيل {period_label} - {invoice_count} فاتورة نشطة - إجمالي {grand_total:.2f} ج.م"
            )
        except DatabaseError as e:
            QMessageBox.critical(dialog, "خطأ", str(e))
            return
        QMessageBox.information(dialog, "تم", f"تم تسجيل تقفيل {period_label} في سجل الحركة. الفواتير فضلت محفوظة كاملة في البرنامج.")

    def search_invoices(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        term = self.invoice_search_edit.text().strip()

        try:
            invoices = self.db.search_invoices(date_from, date_to, invoice_number=term or None)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.invoices_table.setRowCount(len(invoices))
        for row, inv in enumerate(invoices):
            self.invoices_table.setItem(row, 0, QTableWidgetItem(inv["invoice_number"]))
            self.invoices_table.setItem(row, 1, QTableWidgetItem(str(inv["created_at"])))
            self.invoices_table.setItem(row, 2, QTableWidgetItem(inv.get("cashier_name") or "-"))
            net = inv["net_total"] if inv["net_total"] is not None else inv["grand_total"]
            self.invoices_table.setItem(row, 3, QTableWidgetItem(f"{float(net):.2f}"))
            status_item = QTableWidgetItem("ملغاة" if inv["status"] == "cancelled" else "نشطة")
            if inv["status"] == "cancelled":
                status_item.setForeground(Qt.red)
            self.invoices_table.setItem(row, 4, status_item)

            view_btn = QPushButton("عرض التفاصيل")
            view_btn.clicked.connect(lambda _, inv_id=inv["id"]: self.open_invoice_detail(inv_id))
            self.invoices_table.setCellWidget(row, 5, view_btn)
        self.invoices_table.resizeRowsToContents()

    def open_invoice_detail(self, invoice_id):
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
        dialog.resize(500, 450)
        layout = QVBoxLayout(dialog)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: white;")
        content_layout = QVBoxLayout(content_widget)

        net = invoice["net_total"] if invoice["net_total"] is not None else invoice["grand_total"]
        status_text = "ملغاة ❌" if invoice["status"] == "cancelled" else "نشطة ✅"
        header = QLabel(
            f"الحالة: {status_text}\nالتاريخ: {invoice['created_at']}\n"
            f"الإجمالي الصافي: {float(net):.2f} ج.م"
        )
        if invoice["status"] == "cancelled":
            header.setText(header.text() + f"\nسبب الإلغاء: {invoice.get('cancel_reason') or '-'}")
        content_layout.addWidget(header)

        items_table = QTableWidget(len(items), 4)
        items_table.setHorizontalHeaderLabels(["الصنف", "النوع", "الكمية", "الإجمالي"])
        items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        type_labels = {"tamween": "تموين", "free": "حر", "bread": "عيش", "wholesale": "جملة"}
        for row, it in enumerate(items):
            items_table.setItem(row, 0, QTableWidgetItem(it["product_name"]))
            items_table.setItem(row, 1, QTableWidgetItem(type_labels.get(it["sale_type"], it["sale_type"])))
            items_table.setItem(row, 2, QTableWidgetItem(f"{float(it['quantity']):g}"))
            items_table.setItem(row, 3, QTableWidgetItem(f"{float(it['line_total']):.2f}"))
        content_layout.addWidget(items_table)

        layout.addWidget(content_widget)

        def print_as_receipt():
            cfg = config.load_config()
            meta = [f"رقم الفاتورة: {invoice['invoice_number']}", f"التاريخ: {invoice['created_at']}", f"الحالة: {status_text}"]
            if invoice["status"] == "cancelled":
                meta.append(f"سبب الإلغاء: {invoice.get('cancel_reason') or '-'}")
            item_lines = []
            for it in items:
                item_lines.append(f"{it['product_name']} ({type_labels.get(it['sale_type'], it['sale_type'])})")
                item_lines.append(f"  {float(it['quantity']):g} = {float(it['line_total']):.2f} ج.م")
            text = printer.build_generic_receipt_text(
                cfg, f"فاتورة رقم {invoice['invoice_number']}", meta, item_lines,
                [f"الإجمالي الصافي: {float(net):.2f} ج.م"], width=int(cfg.get("receipt_width", 32))
            )
            try:
                printer.print_receipt(text)
            except Exception as e:
                QMessageBox.warning(dialog, "تنبيه طباعة", f"حصل خطأ أثناء الطباعة:\n{e}")

        btn_row = QHBoxLayout()
        print_receipt_btn = QPushButton("🖶 طباعة الفاتورة (طابعة حرارية)")
        print_receipt_btn.clicked.connect(print_as_receipt)
        btn_row.addWidget(print_receipt_btn)
        if self.can_cancel and invoice["status"] != "cancelled":
            cancel_btn = QPushButton("إلغاء هذه الفاتورة")
            cancel_btn.setObjectName("primaryButton")
            cancel_btn.clicked.connect(lambda: self._do_cancel_invoice(invoice_id, dialog))
            btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        dialog.exec_()

    def _do_cancel_invoice(self, invoice_id, dialog):
        from PyQt5.QtWidgets import QInputDialog
        reason, ok = QInputDialog.getText(dialog, "سبب الإلغاء", "اكتب سبب إلغاء الفاتورة (اختياري):")
        if not ok:
            return
        confirm = QMessageBox.question(
            dialog, "تأكيد نهائي",
            "متأكد إنك عايز تلغي الفاتورة دي؟ الكمية هترجع للمخزون والإجراء مينفعش يتراجع فيه."
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.cancel_invoice(invoice_id, self.current_user["id"], reason.strip())
        except DatabaseError as e:
            QMessageBox.critical(dialog, "خطأ", str(e))
            return
        QMessageBox.information(dialog, "تم الإلغاء", "تم إلغاء الفاتورة وإرجاع الكمية للمخزون بنجاح")
        dialog.accept()
        self.search_invoices()
