# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QMessageBox
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

import barcode_gen


class BarcodeStickerDialog(QDialog):
    """
    نافذة معاينة وطباعة ملصق باركود: اسم/عنوان بالعربي (يترسم عن طريق Qt فيظهر صح)
    + صورة الباركود + سطر فرعي اختياري (زي السعر أو اسم صاحب البطاقة).
    """
    def __init__(self, title_text, barcode_value, subtitle_text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("معاينة الباركود")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(320, 260)

        outer_layout = QVBoxLayout(self)

        # محتوى الملصق (ده اللي هيتطبع فعليًا، من غير الأزرار)
        self.sticker_widget = QWidget()
        sticker_layout = QVBoxLayout(self.sticker_widget)
        self.sticker_widget.setStyleSheet("background: white;")

        name_label = QLabel(title_text)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-weight: 700; font-size: 14px; color: black;")
        name_label.setWordWrap(True)
        sticker_layout.addWidget(name_label)

        try:
            png_bytes = barcode_gen.render_barcode_png(barcode_value)
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذّر توليد صورة الباركود:\n{e}")
            pixmap = QPixmap()

        img_label = QLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignCenter)
        sticker_layout.addWidget(img_label)

        if subtitle_text:
            sub_label = QLabel(subtitle_text)
            sub_label.setAlignment(Qt.AlignCenter)
            sub_label.setStyleSheet("font-size: 12px; color: black;")
            sticker_layout.addWidget(sub_label)

        outer_layout.addWidget(self.sticker_widget)

        btn_row = QHBoxLayout()
        print_btn = QPushButton("طباعة")
        print_btn.setObjectName("primaryButton")
        print_btn.clicked.connect(self.print_sticker)
        close_btn = QPushButton("إغلاق")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(print_btn)
        btn_row.addWidget(close_btn)
        outer_layout.addLayout(btn_row)

    def print_sticker(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec_() != QPrintDialog.Accepted:
            return

        pixmap = self.sticker_widget.grab()
        painter = QPainter(printer)
        rect = painter.viewport()
        size = pixmap.size()
        size.scale(rect.size(), Qt.KeepAspectRatio)
        painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
        painter.setWindow(pixmap.rect())
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
