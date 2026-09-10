# -*- coding: utf-8 -*-
"""
استيراد جماعي للأصناف من ملف إكسيل لتبويب المخزون.
الأعمدة المتوقعة في أول صف (بالعربي أو الإنجليزي، الترتيب مش مهم):
الاسم* | الباركود | التصنيف | الوحدة | سعر التموين | سعر الحر | سعر العيش | سعر الجملة | الكمية | حد التنبيه
العمود الوحيد الإجباري هو "الاسم".
"""
import openpyxl

COLUMN_ALIASES = {
    "name": ["الاسم", "اسم الصنف", "name", "product name"],
    "barcode": ["الباركود", "باركود", "barcode"],
    "category": ["التصنيف", "الفئة", "category"],
    "unit": ["الوحدة", "unit"],
    "price_tamween": ["سعر التموين", "التموين", "price_tamween", "tamween"],
    "price_free": ["سعر الحر", "الحر", "price_free", "free"],
    "price_bread": ["سعر العيش", "العيش", "price_bread", "bread"],
    "price_wholesale": ["سعر الجملة", "الجملة", "price_wholesale", "wholesale"],
    "quantity": ["الكمية", "quantity", "qty"],
    "min_quantity": ["حد التنبيه", "حد النفاذ", "min_quantity"],
}


def _normalize(text):
    return str(text).strip().lower() if text is not None else ""


def _map_headers(header_row):
    """يرجع dict: field_name -> column_index (0-based)."""
    mapping = {}
    normalized_headers = [_normalize(h) for h in header_row]
    for field, aliases in COLUMN_ALIASES.items():
        normalized_aliases = [_normalize(a) for a in aliases]
        for idx, header in enumerate(normalized_headers):
            if header in normalized_aliases:
                mapping[field] = idx
                break
    return mapping


def read_products_from_excel(file_path):
    """
    يرجع (products, errors):
    products: قايمة dicts فيها بيانات كل صنف جاهزة للإضافة (category بيفضل نص لحد ما يتحول لـ id لاحقًا)
    errors: قايمة نصوص توضح أي صف فشل ولية
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb.active

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return [], ["الملف فاضي"]

    header_row = rows[0]
    mapping = _map_headers(header_row)

    if "name" not in mapping:
        return [], ["مفيش عمود اسمه \"الاسم\" في أول صف بالملف. تأكد إن أول صف فيه عناوين الأعمدة."]

    products = []
    errors = []

    for row_num, row in enumerate(rows[1:], start=2):
        def get(field, default=None):
            idx = mapping.get(field)
            if idx is None or idx >= len(row):
                return default
            value = row[idx]
            return value if value is not None else default

        name = get("name")
        if not name or not str(name).strip():
            continue  # صف فاضي، تجاهله من غير ما نعتبره خطأ

        try:
            products.append({
                "name": str(name).strip(),
                "barcode": str(get("barcode")).strip() if get("barcode") else None,
                "category": str(get("category")).strip() if get("category") else None,
                "unit": str(get("unit")).strip() if get("unit") else "قطعة",
                "price_tamween": float(get("price_tamween", 0) or 0),
                "price_free": float(get("price_free", 0) or 0),
                "price_bread": float(get("price_bread", 0) or 0),
                "price_wholesale": float(get("price_wholesale", 0) or 0),
                "quantity": float(get("quantity", 0) or 0),
                "min_quantity": float(get("min_quantity", 0) or 0),
            })
        except (ValueError, TypeError) as e:
            errors.append(f"صف {row_num}: قيمة غير صحيحة ({e})")

    return products, errors


def import_products(db, file_path):
    """
    يستورد الأصناف فعليًا في قاعدة البيانات.
    يرجع dict فيه: success_count, failed_rows (قايمة أسباب الفشل)
    """
    products, parse_errors = read_products_from_excel(file_path)

    category_cache = {}
    try:
        for c in db.list_categories():
            category_cache[c["name"].strip().lower()] = c["id"]
    except Exception:
        pass

    success_count = 0
    failed_rows = list(parse_errors)

    for p in products:
        try:
            category_id = None
            if p["category"]:
                key = p["category"].lower()
                if key in category_cache:
                    category_id = category_cache[key]
                else:
                    category_id = db.add_category(p["category"])
                    category_cache[key] = category_id

            db.add_product({
                "barcode": p["barcode"],
                "name": p["name"],
                "category_id": category_id,
                "unit": p["unit"],
                "price_tamween": p["price_tamween"],
                "price_free": p["price_free"],
                "price_bread": p["price_bread"],
                "price_wholesale": p["price_wholesale"],
                "quantity": p["quantity"],
                "min_quantity": p["min_quantity"],
            })
            success_count += 1
        except Exception as e:
            failed_rows.append(f"الصنف \"{p['name']}\": فشلت الإضافة ({e})")

    return {"success_count": success_count, "failed_rows": failed_rows, "total_found": len(products)}
