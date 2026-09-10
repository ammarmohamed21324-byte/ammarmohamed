# -*- coding: utf-8 -*-
"""
تصدير كل أصناف المخزون لملف إكسيل، بنفس شكل الأعمدة اللي بيقرأها موديول الاستيراد
(excel_import.py)، عشان تقدر تعدّل على الملف وتستورده تاني لو حبيت.
"""
import openpyxl
from openpyxl.styles import Font, Alignment


HEADERS = [
    "الاسم", "الباركود", "التصنيف", "الوحدة",
    "سعر التموين", "سعر الحر", "سعر العيش", "سعر الجملة",
    "سعر الشراء", "الكمية", "حد التنبيه", "تاريخ الصلاحية",
]


def export_products_to_excel(products, categories_by_id, file_path):
    """
    products: قايمة dicts من db.list_products()
    categories_by_id: dict {id: name} عشان نكتب اسم التصنيف مش رقمه
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "الأصناف"
    ws.sheet_view.rightToLeft = True

    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for p in products:
        category_name = categories_by_id.get(p.get("category_id"), "")
        ws.append([
            p.get("name") or "",
            p.get("barcode") or "",
            category_name,
            p.get("unit") or "",
            float(p.get("price_tamween") or 0),
            float(p.get("price_free") or 0),
            float(p.get("price_bread") or 0),
            float(p.get("price_wholesale") or 0),
            float(p.get("purchase_price") or 0),
            float(p.get("quantity") or 0),
            float(p.get("min_quantity") or 0),
            str(p.get("expiry_date")) if p.get("expiry_date") else "",
        ])

    for col_cells in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
        ws.column_dimensions[col_cells[0].column_letter].width = max(12, min(30, max_len + 2))

    wb.save(file_path)
