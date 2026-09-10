# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox
)

from database import Database, DatabaseError


class LoginWindow(QWidget):
    def __init__(self, on_success):
        super().__init__()
        self.on_success = on_success
        self.db = Database()
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle("تسجيل الدخول - نظام نقاط بيع التموين")
        self.resize(380, 220)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("نظام نقاط بيع محل التموين")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("اسم المستخدم:", self.username_edit)
        form.addRow("كلمة المرور:", self.password_edit)
        layout.addLayout(form)

        self.login_btn = QPushButton("دخول")
        self.login_btn.setObjectName("loginButton")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.try_login)
        layout.addWidget(self.login_btn)

        self.password_edit.returnPressed.connect(self.try_login)

        hint = QLabel("أول تشغيل؟ استخدم: admin / admin123")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

    def try_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            QMessageBox.warning(self, "تنبيه", "من فضلك ادخل اسم المستخدم وكلمة المرور")
            return
        try:
            user = self.db.authenticate(username, password)
        except DatabaseError as e:
            QMessageBox.critical(self, "خطأ في الاتصال", str(e))
            return

        if user:
            self.on_success(user, self.db)
        else:
            QMessageBox.warning(self, "خطأ", "اسم المستخدم أو كلمة المرور غير صحيحة")
