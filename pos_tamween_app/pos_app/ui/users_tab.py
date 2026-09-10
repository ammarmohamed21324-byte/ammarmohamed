# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QCheckBox,
    QGroupBox, QHeaderView, QInputDialog
)

from database import DatabaseError


class UsersTab(QWidget):
    def __init__(self, db, current_user):
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.editing_user_id = None
        self.permission_checks = {}  # permission_key -> QCheckBox
        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self.refresh_users_table()
        self.refresh_activity_log()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # ---------------- نموذج إنشاء / تعديل مستخدم ----------------
        form_box = QGroupBox("بيانات المستخدم")
        form_layout = QFormLayout()

        self.username_edit = QLineEdit()
        self.full_name_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("اتركه فاضي لو مش عايز تغيّر الباسورد")

        self.role_combo = QComboBox()
        self.role_combo.addItem("موظف / كاشير (صلاحيات محددة)", "cashier")
        self.role_combo.addItem("أدمن (كل الصلاحيات تلقائيًا)", "admin")
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)

        self.active_check = QCheckBox("الحساب مفعّل")
        self.active_check.setChecked(True)

        form_layout.addRow("اسم المستخدم:", self.username_edit)
        form_layout.addRow("الاسم بالكامل:", self.full_name_edit)
        form_layout.addRow("كلمة المرور:", self.password_edit)
        form_layout.addRow("نوع الحساب:", self.role_combo)
        form_layout.addRow(self.active_check)

        self.permissions_box = QGroupBox("الصلاحيات (للموظف/الكاشير فقط)")
        self.permissions_layout = QVBoxLayout()
        self.permissions_box.setLayout(self.permissions_layout)
        self._load_permission_checkboxes()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("حفظ المستخدم")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.save_user)
        new_btn = QPushButton("مستخدم جديد (تفريغ الحقول)")
        new_btn.clicked.connect(self.reset_form)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(new_btn)

        form_container = QVBoxLayout()
        form_container.addLayout(form_layout)
        form_container.addWidget(self.permissions_box)
        form_container.addLayout(btn_row)
        form_box.setLayout(form_container)
        layout.addWidget(form_box, 1)

        # ---------------- جدول المستخدمين + سجل الحركة ----------------
        right_col = QVBoxLayout()

        users_box = QGroupBox("المستخدمين الحاليين")
        users_layout = QVBoxLayout()
        self.users_table = QTableWidget(0, 7)
        self.users_table.setHorizontalHeaderLabels(
            ["اسم المستخدم", "الاسم بالكامل", "نوع الحساب", "الحالة", "", "", ""]
        )
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col, width in [(4, 115), (5, 170), (6, 115)]:
            self.users_table.setColumnWidth(col, width)
            self.users_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
        self.users_table.cellDoubleClicked.connect(self.load_row_for_edit)
        users_layout.addWidget(self.users_table)
        users_box.setLayout(users_layout)
        right_col.addWidget(users_box, 2)

        log_box = QGroupBox("سجل الحركة (آخر العمليات)")
        log_layout = QVBoxLayout()
        refresh_log_btn = QPushButton("تحديث السجل")
        refresh_log_btn.clicked.connect(self.refresh_activity_log)
        log_layout.addWidget(refresh_log_btn)
        self.log_table = QTableWidget(0, 4)
        self.log_table.setHorizontalHeaderLabels(["الوقت", "المستخدم", "العملية", "التفاصيل"])
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        log_layout.addWidget(self.log_table)
        log_box.setLayout(log_layout)
        right_col.addWidget(log_box, 3)

        layout.addLayout(right_col, 2)

    def _load_permission_checkboxes(self):
        while self.permissions_layout.count():
            item = self.permissions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.permission_checks = {}

        try:
            permissions = self.db.list_permissions()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        for perm in permissions:
            cb = QCheckBox(perm["label"])
            self.permission_checks[perm["permission_key"]] = cb
            self.permissions_layout.addWidget(cb)

    def _on_role_changed(self):
        is_admin = self.role_combo.currentData() == "admin"
        self.permissions_box.setEnabled(not is_admin)

    def refresh_users_table(self):
        try:
            users = self.db.list_users()
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.users_table.setRowCount(len(users))
        for row, u in enumerate(users):
            self.users_table.setItem(row, 0, QTableWidgetItem(u["username"]))
            self.users_table.setItem(row, 1, QTableWidgetItem(u["full_name"] or ""))
            self.users_table.setItem(row, 2, QTableWidgetItem("أدمن" if u["role"] == "admin" else "موظف"))
            status_item = QTableWidgetItem("مفعّل" if u["is_active"] else "معطّل")
            if not u["is_active"]:
                status_item.setForeground(Qt.red)
            self.users_table.setItem(row, 3, status_item)

            deactivate_btn = QPushButton("تعطيل" if u["is_active"] else "تفعيل")
            deactivate_btn.clicked.connect(lambda _, uid=u["id"], active=u["is_active"]: self.toggle_active(uid, active))
            self.users_table.setCellWidget(row, 4, deactivate_btn)

            reset_pw_btn = QPushButton("إعادة تعيين الباسورد")
            reset_pw_btn.clicked.connect(lambda _, uid=u["id"], name=u["full_name"] or u["username"]: self.reset_password(uid, name))
            self.users_table.setCellWidget(row, 5, reset_pw_btn)

            delete_btn = QPushButton("حذف")
            delete_btn.clicked.connect(lambda _, uid=u["id"], name=u["full_name"] or u["username"]: self.delete_user(uid, name))
            self.users_table.setCellWidget(row, 6, delete_btn)

            self.users_table.item(row, 0).setData(Qt.UserRole, u["id"])

        self.users_table.resizeRowsToContents()

    def load_row_for_edit(self, row, _col):
        user_id = self.users_table.item(row, 0).data(Qt.UserRole)
        try:
            user = self.db.get_user_by_id(user_id)
            perms = self.db.get_user_permissions(user_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        if not user:
            return

        self.editing_user_id = user["id"]
        self.username_edit.setText(user["username"])
        self.username_edit.setEnabled(False)
        self.full_name_edit.setText(user["full_name"] or "")
        self.password_edit.clear()
        idx = self.role_combo.findData(user["role"])
        self.role_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.active_check.setChecked(bool(user["is_active"]))

        for key, cb in self.permission_checks.items():
            cb.setChecked(key in perms)

    def reset_form(self):
        self.editing_user_id = None
        self.username_edit.clear()
        self.username_edit.setEnabled(True)
        self.full_name_edit.clear()
        self.password_edit.clear()
        self.role_combo.setCurrentIndex(0)
        self.active_check.setChecked(True)
        for cb in self.permission_checks.values():
            cb.setChecked(False)

    def save_user(self):
        username = self.username_edit.text().strip()
        full_name = self.full_name_edit.text().strip()
        role = self.role_combo.currentData()
        password = self.password_edit.text()
        selected_permissions = [key for key, cb in self.permission_checks.items() if cb.isChecked()]

        if not username:
            QMessageBox.warning(self, "تنبيه", "اسم المستخدم مطلوب")
            return

        try:
            if self.editing_user_id:
                self.db.update_user(
                    self.editing_user_id, full_name, role,
                    1 if self.active_check.isChecked() else 0,
                    selected_permissions,
                    new_password=password or None,
                )
                self.db.log_activity(
                    self.current_user["id"], "update_user",
                    f"تعديل بيانات المستخدم: {username}"
                )
            else:
                if not password:
                    QMessageBox.warning(self, "تنبيه", "كلمة المرور مطلوبة للمستخدم الجديد")
                    return
                if self.db.username_exists(username):
                    QMessageBox.warning(self, "تنبيه", "اسم المستخدم ده موجود بالفعل")
                    return
                self.db.add_user(username, password, full_name, role, selected_permissions)
                self.db.log_activity(
                    self.current_user["id"], "create_user",
                    f"إنشاء مستخدم جديد: {username} ({'أدمن' if role=='admin' else 'موظف'})"
                )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(self, "تم", "تم حفظ بيانات المستخدم بنجاح")
        self.reset_form()
        self.refresh_users_table()
        self.refresh_activity_log()

    def toggle_active(self, user_id, currently_active):
        if user_id == self.current_user["id"]:
            QMessageBox.warning(self, "تنبيه", "مينفعش تعطّل حسابك انت اللي داخل بيه دلوقتي")
            return
        try:
            user = self.db.get_user_by_id(user_id)
            perms = self.db.get_user_permissions(user_id)
            self.db.update_user(
                user_id, user["full_name"], user["role"],
                0 if currently_active else 1, list(perms),
            )
            self.db.log_activity(
                self.current_user["id"],
                "deactivate_user" if currently_active else "activate_user",
                f"{'تعطيل' if currently_active else 'تفعيل'} المستخدم: {user['username']}"
            )
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        self.refresh_users_table()
        self.refresh_activity_log()

    def reset_password(self, user_id, name):
        new_password, ok = QInputDialog.getText(
            self, f"إعادة تعيين باسورد {name}", "اكتب كلمة المرور الجديدة:", QLineEdit.Normal
        )
        if not ok or not new_password.strip():
            return
        try:
            user = self.db.get_user_by_id(user_id)
            perms = self.db.get_user_permissions(user_id)
            self.db.update_user(
                user_id, user["full_name"], user["role"], user["is_active"],
                list(perms), new_password=new_password.strip(),
            )
            self.db.log_activity(self.current_user["id"], "reset_password", f"إعادة تعيين باسورد المستخدم: {name}")
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        QMessageBox.information(self, "تم", f"تم تغيير كلمة مرور {name} بنجاح")
        self.refresh_activity_log()

    def delete_user(self, user_id, name):
        if user_id == self.current_user["id"]:
            QMessageBox.warning(self, "تنبيه", "مينفعش تحذف حسابك انت اللي داخل بيه دلوقتي")
            return
        confirm = QMessageBox.question(
            self, "تأكيد الحذف",
            f"متأكد إنك عايز تحذف {name} نهائيًا؟ الإجراء ده مينفعش يتراجع فيه."
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.delete_user(user_id)
        except DatabaseError as e:
            QMessageBox.critical(self, "تعذّر الحذف", str(e))
            return
        QMessageBox.information(self, "تم", f"تم حذف {name} نهائيًا")
        self.refresh_users_table()
        self.refresh_activity_log()

    def refresh_activity_log(self):
        try:
            logs = self.db.list_activity_log(limit=100)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        self.log_table.setRowCount(len(logs))
        for row, entry in enumerate(logs):
            self.log_table.setItem(row, 0, QTableWidgetItem(str(entry["created_at"])))
            self.log_table.setItem(row, 1, QTableWidgetItem(entry.get("user_full_name") or "-"))
            self.log_table.setItem(row, 2, QTableWidgetItem(entry["action"]))
            self.log_table.setItem(row, 3, QTableWidgetItem(entry["details"] or ""))
