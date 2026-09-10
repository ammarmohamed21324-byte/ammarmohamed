# -*- coding: utf-8 -*-
"""
نقطة تشغيل البرنامج.
تشغيل مباشر: python main.py
بعد التجميع: pos_tamween.exe
"""
import os
import sys
import traceback
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from ui.lock_window import LockWindow
import config
import backup
import license as lic


class BackupThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        cfg = config.load_config()
        success, message, _path = backup.run_backup(cfg)
        self.finished_signal.emit(success, message)


def resource_path(relative_path):
    """يرجع المسار الصحيح للملف سواء وأنت شغال بالكود مباشرة أو بعد تحويله لـ exe."""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def install_global_error_handler():
    """
    بدل ما أي خطأ غير متوقع يقفل البرنامج بصمت، هيظهر رسالة واضحة للمستخدم
    توضح إن فيه مشكلة، مع تفاصيل تقنية تساعد في تشخيصها.
    """
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            QMessageBox.critical(
                None, "حدث خطأ غير متوقع",
                "حصلت مشكلة غير متوقعة والبرنامج مقدرش يكمل العملية دي.\n"
                "المعلومات دي ممكن تساعد في تحديد السبب:\n\n" + details[-1500:]
            )
        except Exception:
            pass  # لو حتى عرض الرسالة نفسه فشل، على الأقل منمنعش الإغلاق بصمت

    sys.excepthook = handle_exception


class AppController:
    def __init__(self):
        install_global_error_handler()
        self.app = QApplication(sys.argv)
        self.app.setLayoutDirection(2)  # Qt.RightToLeft
        self._load_theme()

    def _load_theme(self):
        theme_path = resource_path("theme.qss")
        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                self.app.setStyleSheet(f.read())
        except FileNotFoundError:
            pass  # لو الملف مش موجود، البرنامج يشتغل بالشكل الافتراضي من غير كسر
        self.login_win = None
        self.main_win = None

    def start(self):
        status = lic.get_trial_status()
        if status["is_locked"]:
            self.show_lock_screen()
        else:
            self.show_login()
        sys.exit(self.app.exec_())

    def show_lock_screen(self):
        self.lock_win = LockWindow(on_unlocked=self.show_login)
        self.lock_win.show()

    def show_login(self):
        self.login_win = LoginWindow(on_success=self.on_login_success)
        self.login_win.show()

    def on_login_success(self, user, db):
        try:
            self.main_win = MainWindow(user, db, on_logout=self.handle_logout)
            self.main_win.show()
        except Exception:
            raise  # يلتقطها sys.excepthook ويعرض رسالة، والنافذة الحالية (تسجيل الدخول) تفضل مفتوحة
        self.login_win.close()
        self._maybe_run_daily_backup()

        # فحص دوري كل ساعة وهو شغال، عشان لو البرنامج فاضل فاتح كذا يوم من غير
        # تسجيل خروج، النسخة الاحتياطية اليومية تتعمل لوحدها برضو من غير ما حد يقفل ويفتح
        self._backup_check_timer = QTimer()
        self._backup_check_timer.timeout.connect(self._maybe_run_daily_backup)
        self._backup_check_timer.start(60 * 60 * 1000)  # كل ساعة

    def _maybe_run_daily_backup(self):
        cfg = config.load_config()
        if not backup.is_backup_due_today(cfg):
            return
        self._backup_thread = BackupThread()
        self._backup_thread.finished_signal.connect(self._on_backup_finished)
        self._backup_thread.start()

    def _on_backup_finished(self, success, message):
        if not success and self.main_win:
            QMessageBox.warning(
                self.main_win, "تنبيه: فشلت النسخة الاحتياطية اليومية",
                f"{message}\n\nراجع إعدادات النسخ الاحتياطي في تبويب \"الإعدادات\"."
            )

    def handle_logout(self):
        """يقفل نافذة البرنامج الرئيسية ويرجع لشاشة تسجيل الدخول من غير ما يقفل التطبيق كله."""
        if hasattr(self, "_backup_check_timer"):
            self._backup_check_timer.stop()
        self.main_win = None
        self.show_login()


if __name__ == "__main__":
    AppController().start()
