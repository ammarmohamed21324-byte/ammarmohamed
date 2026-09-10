# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)

import license as lic


class LockWindow(QWidget):
    """
    شاشة قفل بتظهر لما الفترة التجريبية تنتهي. مش بتلمس قاعدة البيانات خالص -
    بس بتمنع الاستمرار للبرنامج لحد ما يتكتب كود تفعيل صحيح.
    """

    def __init__(self, on_unlocked):
        super().__init__()
        self.on_unlocked = on_unlocked
        self.setWindowTitle("انتهت الفترة التجريبية")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(480, 320)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("انتهت الفترة التجريبية لهذا البرنامج")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #C0392B;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        note = QLabel(
            "بياناتك كلها محفوظة بالكامل ولسه موجودة زي ما هي. "
            "اتصل بمقدّم البرنامج وقوله كود الجهاز اللي تحت، وهو هيديك كود تفعيل تكتبه هنا."
        )
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        layout.addWidget(note)

        status = lic.get_trial_status()
        code_label = QLabel(f"كود الجهاز: {status['machine_code']}")
        code_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; background:#F4F8FD; "
            "border: 1px solid #C7DDF8; border-radius: 8px; padding: 12px;"
        )
        code_label.setAlignment(Qt.AlignCenter)
        code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(code_label)

        input_row = QHBoxLayout()
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("اكتب كود التفعيل هنا")
        self.code_edit.setAlignment(Qt.AlignCenter)
        input_row.addWidget(self.code_edit)
        layout.addLayout(input_row)

        activate_btn = QPushButton("تفعيل")
        activate_btn.setObjectName("primaryButton")
        activate_btn.clicked.connect(self._try_activate)
        layout.addWidget(activate_btn)

        layout.addStretch()

    def _try_activate(self):
        code = self.code_edit.text().strip()
        if not code:
            QMessageBox.warning(self, "تنبيه", "اكتب كود التفعيل الأول")
            return
        if lic.try_activate(code):
            QMessageBox.information(self, "تم", "تم تفعيل البرنامج بنجاح، هيفتح دلوقتي.")
            self.close()
            self.on_unlocked()
        else:
            QMessageBox.critical(self, "خطأ", "كود التفعيل مش صحيح، تأكد منه مع مقدّم البرنامج.")
