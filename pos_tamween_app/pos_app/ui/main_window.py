# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QTabWidget, QMessageBox, QLabel, QPushButton, QMenu

from ui.pos_tab import PosTab
from ui.inventory_tab import InventoryTab
from ui.ration_tab import RationTab
from ui.reports_tab import ReportsTab
from ui.settings_tab import SettingsTab
from ui.users_tab import UsersTab
from ui.shift_tab import ShiftTab
from ui.suppliers_tab import SuppliersTab
from ui.payroll_tab import PayrollTab
from ui.customers_tab import CustomersTab


class MainWindow(QMainWindow):
    def __init__(self, user, db, on_logout=None):
        super().__init__()
        self.user = user
        self.db = db
        self.on_logout = on_logout
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle(f"نظام نقاط بيع التموين - مسجل الدخول: {user['full_name']} ({user['role']})")
        self.resize(1100, 650)
        self._build_ui()
        self._build_status_bar()

    def _build_status_bar(self):
        user_btn = QPushButton(f"👤 {self.user['full_name']}  ▾")
        user_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #0C447C; "
            "font-weight: 600; padding: 4px 10px; } QPushButton:hover { background: #EAF2FD; border-radius: 6px; }"
        )

        menu = QMenu(user_btn)
        menu.setLayoutDirection(Qt.RightToLeft)
        logout_action = menu.addAction("تسجيل خروج")
        logout_action.triggered.connect(self._handle_logout)
        user_btn.setMenu(menu)

        self.statusBar().addPermanentWidget(user_btn)

    def _handle_logout(self):
        confirm = QMessageBox.question(
            self, "تأكيد تسجيل الخروج",
            f"هل تأكد إنك عايز تسجل خروج من حساب {self.user['full_name']}؟"
        )
        if confirm != QMessageBox.Yes:
            return
        if self.on_logout:
            self.on_logout()
        self.close()

    def _build_ui(self):
        tabs = QTabWidget()
        is_admin = self.user["role"] == "admin"
        perms = self.user.get("permissions", set())

        def allowed(key):
            return is_admin or key in perms

        if allowed("pos_sell"):
            can_cancel_pos = is_admin or allowed("cancel_invoices")
            tabs.addTab(PosTab(self.db, self.user, can_cancel_pos), "شاشة البيع")
        if allowed("manage_shift"):
            tabs.addTab(ShiftTab(self.db, self.user), "الوردية")
        if allowed("manage_inventory"):
            tabs.addTab(InventoryTab(self.db, self.user), "المخزون والأصناف")
        if allowed("manage_suppliers") or allowed("approve_supplier_invoices"):
            can_approve_invoices = is_admin or allowed("approve_supplier_invoices")
            tabs.addTab(SuppliersTab(self.db, self.user, can_approve_invoices), "الموردين واستلام البضاعة")
        if allowed("manage_ration_cards"):
            tabs.addTab(RationTab(self.db), "بطاقات التموين")
        if allowed("view_reports"):
            can_cancel_invoices = is_admin or allowed("cancel_invoices")
            tabs.addTab(ReportsTab(self.db, self.user, can_cancel_invoices), "التقارير")
        if allowed("manage_users"):
            tabs.addTab(UsersTab(self.db, self.user), "المستخدمين والصلاحيات")
        if allowed("manage_payroll"):
            tabs.addTab(PayrollTab(self.db, self.user), "الرواتب والسلف")
        if allowed("manage_customers"):
            tabs.addTab(CustomersTab(self.db, self.user), "حسابات العملاء")
        if is_admin or allowed("manage_settings"):
            tabs.addTab(SettingsTab(), "الإعدادات")

        if tabs.count() == 0:
            no_access = QLabel("حسابك مفعّل لكن مفيهوش أي صلاحيات معينة لسه. كلّم الأدمن يديك صلاحيات.")
            no_access.setAlignment(Qt.AlignCenter)
            tabs.addTab(no_access, "بدون صلاحيات")

        self.setCentralWidget(tabs)
