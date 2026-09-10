# -*- coding: utf-8 -*-
"""
توليد أكواد باركود فريدة، وتوليد صورة الباركود (Code128) كـ PNG في الذاكرة
لعرضها وطباعتها من داخل البرنامج.
"""
import io
import random

import barcode
from barcode.writer import ImageWriter


def generate_unique_code(exists_check, prefix="P", length=9):
    """
    يولّد كود باركود فريد.
    exists_check: دالة بترجع True لو الكود ده مستخدم بالفعل في قاعدة البيانات.
    """
    for _ in range(30):
        number = "".join(str(random.randint(0, 9)) for _ in range(length))
        code = f"{prefix}{number}"
        if not exists_check(code):
            return code
    raise RuntimeError("تعذّر توليد كود باركود فريد، حاول مرة أخرى")


def render_barcode_png(data: str) -> bytes:
    """يولّد صورة باركود Code128 بصيغة PNG في الذاكرة من نص/رقم معين."""
    code128 = barcode.get_barcode_class("code128")
    instance = code128(data, writer=ImageWriter())
    buffer = io.BytesIO()
    instance.write(buffer, options={
        "write_text": True,
        "module_height": 10,
        "font_size": 8,
        "quiet_zone": 2,
    })
    return buffer.getvalue()
