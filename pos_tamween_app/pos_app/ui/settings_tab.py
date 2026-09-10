# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QSpinBox,
    QComboBox, QMessageBox, QGroupBox, QCheckBox, QLabel, QFileDialog,
    QDialog, QListWidget, QListWidgetItem, QScrollArea
)

import config
import backup
from database import Database, DatabaseError


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.RightToLeft)
        self.cfg = config.load_config()
        self._build_ui()

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

        store_box = QGroupBox("بيانات المحل (تظهر أعلى الفاتورة)")
        store_form = QFormLayout()
        self.store_brand_edit = QLineEdit(self.cfg.get("store_brand", ""))
        self.store_name_edit = QLineEdit(self.cfg["store_name"])
        self.store_tagline_edit = QLineEdit(self.cfg.get("store_tagline", ""))
        self.store_address_edit = QLineEdit(self.cfg["store_address"])
        self.store_phone_edit = QLineEdit(self.cfg["store_phone"])
        self.machine_number_edit = QLineEdit(self.cfg.get("machine_number", "1"))
        store_form.addRow("اسم الجمعية/العلامة (اختياري):", self.store_brand_edit)
        store_form.addRow("اسم المحل:", self.store_name_edit)
        store_form.addRow("شعار فرعي (اختياري):", self.store_tagline_edit)
        store_form.addRow("العنوان:", self.store_address_edit)
        store_form.addRow("التليفون:", self.store_phone_edit)
        store_form.addRow("رقم الماكينة:", self.machine_number_edit)
        store_box.setLayout(store_form)
        layout.addWidget(store_box)

        db_box = QGroupBox("الاتصال بقاعدة البيانات (نفس البيانات على كل الأجهزة)")
        db_form = QFormLayout()
        self.db_host_edit = QLineEdit(self.cfg["db_host"])
        self.db_host_edit.setPlaceholderText("مثال: 192.168.1.10")
        self.db_port_spin = QSpinBox()
        self.db_port_spin.setMaximum(65535)
        self.db_port_spin.setValue(int(self.cfg["db_port"]))
        self.db_user_edit = QLineEdit(self.cfg["db_user"])
        self.db_password_edit = QLineEdit(self.cfg["db_password"])
        self.db_password_edit.setEchoMode(QLineEdit.Password)
        self.db_name_edit = QLineEdit(self.cfg["db_name"])

        db_form.addRow("عنوان السيرفر (IP):", self.db_host_edit)
        db_form.addRow("المنفذ (Port):", self.db_port_spin)
        db_form.addRow("مستخدم قاعدة البيانات:", self.db_user_edit)
        db_form.addRow("كلمة السر:", self.db_password_edit)
        db_form.addRow("اسم قاعدة البيانات:", self.db_name_edit)
        db_box.setLayout(db_form)
        layout.addWidget(db_box)

        printer_box = QGroupBox("إعدادات الطابعة")
        printer_form = QFormLayout()
        self.printer_mode_combo = QComboBox()
        self.printer_mode_combo.addItem("الطابعة الافتراضية في ويندوز (أسهل)", "windows_default")
        self.printer_mode_combo.addItem("طابعة حرارية USB مباشر (escpos)", "escpos_usb")
        idx = self.printer_mode_combo.findData(self.cfg["printer_mode"])
        self.printer_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.vendor_id_edit = QLineEdit(self.cfg["printer_vendor_id"])
        self.product_id_edit = QLineEdit(self.cfg["printer_product_id"])
        self.receipt_width_spin = QSpinBox()
        self.receipt_width_spin.setRange(24, 64)
        self.receipt_width_spin.setValue(int(self.cfg["receipt_width"]))

        printer_form.addRow("طريقة الطباعة:", self.printer_mode_combo)
        printer_form.addRow("Vendor ID (لو USB):", self.vendor_id_edit)
        printer_form.addRow("Product ID (لو USB):", self.product_id_edit)
        printer_form.addRow("عرض الفاتورة (حرف):", self.receipt_width_spin)
        printer_box.setLayout(printer_form)
        layout.addWidget(printer_box)

        backup_box = QGroupBox("النسخ الاحتياطي التلقائي")
        backup_layout = QVBoxLayout()

        backup_note = QLabel(
            "البرنامج بياخد نسخة احتياطية من قاعدة البيانات تلقائيًا كل يوم مرة. "
            "⚠️ مهم جدًا: اختار مجلد في مكان تاني غير هارد الجهاز ده (فلاشة، هارد خارجي، "
            "أو مجلد على جهاز تاني في نفس الشبكة) عشان لو الجهاز ده حصله عطل، البيانات تفضل محفوظة."
        )
        backup_note.setWordWrap(True)
        backup_note.setStyleSheet("color: #a15c00; background:#fff3e0; padding:8px; border-radius:4px;")
        backup_layout.addWidget(backup_note)

        self.backup_enabled_check = QCheckBox("تفعيل النسخ الاحتياطي التلقائي اليومي")
        self.backup_enabled_check.setChecked(bool(self.cfg.get("backup_enabled", True)))
        backup_layout.addWidget(self.backup_enabled_check)

        backup_form = QFormLayout()
        folder_row = QHBoxLayout()
        self.backup_folder_edit = QLineEdit(self.cfg.get("backup_folder", ""))
        self.backup_folder_edit.setPlaceholderText("مثال: D:\\نسخ احتياطية أو مجلد على فلاشة")
        browse_folder_btn = QPushButton("اختيار مجلد")
        browse_folder_btn.clicked.connect(self.browse_backup_folder)
        folder_row.addWidget(self.backup_folder_edit)
        folder_row.addWidget(browse_folder_btn)
        backup_form.addRow("مجلد النسخ الاحتياطية:", folder_row)

        self.backup_retention_spin = QSpinBox()
        self.backup_retention_spin.setRange(1, 365)
        self.backup_retention_spin.setValue(int(self.cfg.get("backup_retention_days", 14)))
        backup_form.addRow("الاحتفاظ بآخر (يوم):", self.backup_retention_spin)

        mysqldump_row = QHBoxLayout()
        self.mysqldump_path_edit = QLineEdit(self.cfg.get("mysqldump_path", "mysqldump"))
        browse_mysqldump_btn = QPushButton("اختيار ملف")
        browse_mysqldump_btn.clicked.connect(self.browse_mysqldump_path)
        mysqldump_row.addWidget(self.mysqldump_path_edit)
        mysqldump_row.addWidget(browse_mysqldump_btn)
        backup_form.addRow("مسار أداة mysqldump (لو مش شغالة تلقائي):", mysqldump_row)

        mysqlcli_row = QHBoxLayout()
        self.mysql_cli_path_edit = QLineEdit(self.cfg.get("mysql_cli_path", "mysql"))
        browse_mysqlcli_btn = QPushButton("اختيار ملف")
        browse_mysqlcli_btn.clicked.connect(self.browse_mysql_cli_path)
        mysqlcli_row.addWidget(self.mysql_cli_path_edit)
        mysqlcli_row.addWidget(browse_mysqlcli_btn)
        backup_form.addRow("مسار أداة mysql (للاسترجاع، لو مش شغالة تلقائي):", mysqlcli_row)
        backup_layout.addLayout(backup_form)

        last_backup = self.cfg.get("last_backup_date") or "لسه ماحصلش نسخة احتياطية"
        self.last_backup_label = QLabel(f"آخر نسخة احتياطية: {last_backup}")
        backup_layout.addWidget(self.last_backup_label)

        backup_now_btn = QPushButton("📦 عمل نسخة احتياطية الآن")
        backup_now_btn.clicked.connect(self.run_backup_now)
        backup_layout.addWidget(backup_now_btn)

        restore_btn = QPushButton("⏪ استرجاع نسخة احتياطية قديمة")
        restore_btn.clicked.connect(self.open_restore_dialog)
        backup_layout.addWidget(restore_btn)

        backup_box.setLayout(backup_layout)
        layout.addWidget(backup_box)

        btn_row = QVBoxLayout()
        test_btn = QPushButton("اختبار الاتصال بقاعدة البيانات")
        test_btn.clicked.connect(self.test_connection)
        save_btn = QPushButton("حفظ الإعدادات")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.save_settings)
        btn_row.addWidget(test_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)
        layout.addStretch()

    def _collect(self):
        return {
            "store_brand": self.store_brand_edit.text().strip(),
            "store_name": self.store_name_edit.text().strip(),
            "store_tagline": self.store_tagline_edit.text().strip(),
            "store_address": self.store_address_edit.text().strip(),
            "store_phone": self.store_phone_edit.text().strip(),
            "machine_number": self.machine_number_edit.text().strip(),
            "db_host": self.db_host_edit.text().strip(),
            "db_port": self.db_port_spin.value(),
            "db_user": self.db_user_edit.text().strip(),
            "db_password": self.db_password_edit.text(),
            "db_name": self.db_name_edit.text().strip(),
            "printer_mode": self.printer_mode_combo.currentData(),
            "printer_vendor_id": self.vendor_id_edit.text().strip(),
            "printer_product_id": self.product_id_edit.text().strip(),
            "receipt_width": self.receipt_width_spin.value(),
            "backup_enabled": self.backup_enabled_check.isChecked(),
            "backup_folder": self.backup_folder_edit.text().strip(),
            "backup_retention_days": self.backup_retention_spin.value(),
            "mysqldump_path": self.mysqldump_path_edit.text().strip() or "mysqldump",
            "mysql_cli_path": self.mysql_cli_path_edit.text().strip() or "mysql",
            "last_backup_date": self.cfg.get("last_backup_date", ""),
        }

    def browse_mysql_cli_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف mysql.exe", "", "Executable (*.exe);;كل الملفات (*)")
        if path:
            self.mysql_cli_path_edit.setText(path)

    def browse_backup_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "اختيار مجلد النسخ الاحتياطية")
        if folder:
            self.backup_folder_edit.setText(folder)

    def browse_mysqldump_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف mysqldump.exe", "", "Executable (*.exe);;كل الملفات (*)")
        if path:
            self.mysqldump_path_edit.setText(path)

    def open_restore_dialog(self):
        cfg = self._collect()
        backups = backup.list_backups(cfg)
        if not backups:
            QMessageBox.information(self, "تنبيه", "مفيش نسخ احتياطية متاحة في المجلد المحدد حاليًا.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("استرجاع نسخة احتياطية")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)

        warning = QLabel(
            "⚠️ تحذير مهم: استرجاع أي نسخة قديمة هيمسح كل البيانات الحالية في قاعدة البيانات "
            "ويحطّ مكانها بيانات النسخة دي بس. تأكد إن كل الأجهزة التانية قافلة البرنامج قبل ما تكمل، "
            "والإجراء ده مينفعش يتراجع فيه."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #C0392B; font-weight: 600; background:#fdecea; padding:8px; border-radius:4px;")
        layout.addWidget(warning)

        list_widget = QListWidget()
        for b in backups:
            item = QListWidgetItem(f"{b['modified']} — {b['name']} ({b['size_kb']} KB)")
            item.setData(Qt.UserRole, b["path"])
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        restore_btn = QPushButton("استرجاع النسخة المحددة")
        restore_btn.setObjectName("primaryButton")
        restore_btn.clicked.connect(lambda: self._do_restore(list_widget, dialog, cfg))
        layout.addWidget(restore_btn)

        dialog.exec_()

    def _do_restore(self, list_widget, dialog, cfg):
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(dialog, "تنبيه", "اختار نسخة من القائمة الأول")
            return

        file_path = item.data(Qt.UserRole)
        confirm = QMessageBox.question(
            dialog, "تأكيد نهائي",
            f"متأكد 100% إنك عايز تسترجع النسخة دي؟\n{item.text()}\n\n"
            "كل البيانات الحالية هتتمسح ومتترجعش تاني."
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = backup.restore_backup(cfg, file_path)
        if success:
            QMessageBox.information(dialog, "تم الاسترجاع", message)
            dialog.accept()
        else:
            QMessageBox.critical(dialog, "فشل الاسترجاع", message)

    def run_backup_now(self):
        cfg = self._collect()
        config.save_config(cfg)  # نحفظ الإعدادات الحالية الأول عشان النسخة تستخدمها
        success, message, _path = backup.run_backup(cfg)
        if success:
            QMessageBox.information(self, "تم بنجاح", message)
            self.cfg = config.load_config()
            self.last_backup_label.setText(f"آخر نسخة احتياطية: {self.cfg.get('last_backup_date')}")
        else:
            QMessageBox.critical(self, "فشلت النسخة الاحتياطية", message)

    def test_connection(self):
        cfg = self._collect()
        config.save_config(cfg)  # نحفظ مؤقتًا عشان نختبر بنفس القيم
        db = Database()
        try:
            db.connect()
            QMessageBox.information(self, "نجح الاتصال", "تم الاتصال بقاعدة البيانات بنجاح ✅")
        except DatabaseError as e:
            QMessageBox.critical(self, "فشل الاتصال", str(e))

    def save_settings(self):
        cfg = self._collect()
        config.save_config(cfg)
        QMessageBox.information(
            self, "تم الحفظ",
            "تم حفظ الإعدادات. من فضلك أعد تشغيل البرنامج عشان التغييرات تتطبق بالكامل."
        )
