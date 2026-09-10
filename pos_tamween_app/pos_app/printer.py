# -*- coding: utf-8 -*-
"""
طباعة الفاتورة على طابعة حرارية.
- الوضع "escpos_usb": يستخدم مكتبة python-escpos للطباعة المباشرة على طابعة
  حرارية متصلة بمنفذ USB (يحتاج تعريف Zadig على ويندوز - مشروح في الـ README).
- الوضع "windows_default": ينشئ ملف نصي للفاتورة ويرسله للطابعة الافتراضية
  المُعرّفة في ويندوز (أسهل في الإعداد ويشتغل مع أغلب الطابعات الحرارية اللي
  بتتعرف كطابعة عادية على ويندوز).
"""
import os
import sys
import tempfile
import datetime

import config


def _line(width, char="-"):
    return char * width


def build_receipt_text(store_info, invoice_result, cart_items, ration_card=None, cashier_name="", width=32):
    lines = []
    if store_info.get("store_brand"):
        lines.append(store_info["store_brand"].center(width))
    lines.append(store_info.get("store_name", "").center(width))
    if store_info.get("store_tagline"):
        lines.append(store_info["store_tagline"].center(width))
    lines.append(_line(width))

    now = datetime.datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
    lines.append(f"التاريخ: {now}")
    lines.append(f"رقم الفاتورة: {invoice_result['invoice_number']}")
    lines.append(f"الكاشير: {cashier_name or '-'}")
    lines.append(f"رقم البطاقة: {ration_card['card_number'] if ration_card else '-'}")
    lines.append(f"الماكينة: {store_info.get('machine_number', '1')}")
    customer_name = ration_card.get("holder_name") if ration_card else None
    lines.append(f"اسم العميل: {customer_name or '-'}")
    lines.append(_line(width))

    kind_labels = {"tamween": "تموين", "free": "حر", "bread": "عيش", "wholesale": "جملة"}
    for item in cart_items:
        name = item["name"]
        qty = item["quantity"]
        price = item["unit_price"]
        total = round(qty * price, 2)
        kind = kind_labels.get(item["sale_type"], item["sale_type"])
        lines.append(f"{name} ({kind})")
        lines.append(f"  {qty:g} x {price:.2f} = {total:.2f} ج.م")

    lines.append(_line(width))
    lines.append(f"الاجمالي: {invoice_result['grand_total']:.2f} ج.م")
    total_with_service = invoice_result.get("total_with_service", invoice_result["grand_total"])
    lines.append(f"الاجمالي+الخدمة: {total_with_service:.2f} ج.م")
    support_total = round(
        float(invoice_result.get("support_tamween", 0)) + float(invoice_result.get("support_bread", 0)), 2
    )
    lines.append(f"الدعم: {support_total:.2f} ج.م")
    lines.append(f"المطلوب: {invoice_result.get('required_amount', 0):.2f} ج.م")
    lines.append(f"المتبقي: {invoice_result.get('remaining_amount', 0):.2f} ج.م")
    lines.append(f"عدد الأصناف: {len(cart_items)}")

    if invoice_result.get("payment_method") == "credit":
        lines.append("** البيع بالآجل - على حساب العميل **")
    elif invoice_result.get("payment_method") in ("visa", "instapay", "wallet"):
        pm_labels = {"visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}
        lines.append(f"طريقة الدفع: {pm_labels[invoice_result['payment_method']]}")

    lines.append(_line(width, "="))
    if store_info.get("store_address"):
        lines.append(store_info["store_address"].center(width))
    if store_info.get("store_phone"):
        lines.append(store_info["store_phone"].center(width))
    lines.append(_line(width, "="))
    return "\n".join(lines)


def build_generic_receipt_text(store_info, title, meta_lines, item_lines, footer_lines, width=32):
    """
    نفس شكل إيصال البيع بالظبط، لكن لأي "فاتورة" عايز تطبعها على الطابعة الحرارية
    من مكان تاني في البرنامج (فاتورة قديمة، فاتورة معلّقة...) مش وقت البيع الفعلي.
    item_lines: قايمة أسطر جاهزة (كل صنف بياخد سطرين عادةً: اسم الصنف، وتحته الكمية والإجمالي).
    """
    lines = []
    if store_info.get("store_brand"):
        lines.append(store_info["store_brand"].center(width))
    lines.append(store_info.get("store_name", "").center(width))
    lines.append(_line(width))
    lines.append(title.center(width))
    lines.append(_line(width))

    for line in meta_lines:
        lines.append(line)
    lines.append(_line(width))

    for line in item_lines:
        lines.append(line)

    lines.append(_line(width))
    for line in footer_lines:
        lines.append(line)
    lines.append(_line(width, "="))
    return "\n".join(lines)






def build_receipt_html(store_info, invoice_result, cart_items, ration_card=None, cashier_name=""):
    """
    فاتورة البيع على الطابعة الحرارية.
    جدولان منفصلان بـ table-layout:fixed بدون فراغات بينهم.
    جدول المعلومات: 4 أعمدة ثابتة.
    جدول الأصناف+الإجماليات+الدعم: 4 أعمدة ثابتة (الصنف 58%).
    """
    import html as html_lib

    def esc(v):
        return html_lib.escape("" if v is None else str(v))

    # تاريخ ووقت على سطرين مع ص/م عربي
    _now = datetime.datetime.now()
    date_str = _now.strftime("%d/%m/%Y")
    time_str = _now.strftime("%I:%M:%S")
    am_pm = "ص" if _now.hour < 12 else "م"
    date_cell_html = "%s<br>%s %s" % (esc(date_str), am_pm, esc(time_str))

    card_number = ration_card["card_number"] if ration_card else "-"
    customer_name = (ration_card.get("holder_name") if ration_card else None) or "-"
    machine_number = store_info.get("machine_number", "1")

    total_with_service = invoice_result.get("total_with_service", invoice_result["grand_total"])
    support_total = round(
        float(invoice_result.get("support_tamween", 0)) + float(invoice_result.get("support_bread", 0)), 2
    )
    required_amount = invoice_result.get("required_amount", 0)
    remaining_amount = invoice_result.get("remaining_amount", 0)

    FONT  = "font-family:'Traditional Arabic','Simplified Arabic',Arial,Tahoma,sans-serif;"
    TI    = "width:100%;table-layout:fixed;border-collapse:collapse;font-size:10px;margin:0;"
    TS    = "width:100%;table-layout:fixed;border-collapse:collapse;font-size:10px;margin:0;"
    TA    = "width:100%;border-collapse:collapse;font-size:10px;"
    SEP   = "border-top:2px solid #000;padding:0;height:0;"

    LBL   = "text-align:right;font-weight:bold;white-space:nowrap;padding:1px 3px;font-size:10px;"
    VAL_R = "text-align:right;white-space:nowrap;padding:1px 3px;font-size:10px;"
    VAL_WR= "text-align:right;word-wrap:break-word;padding:1px 3px;font-size:10px;line-height:1.4;"
    NUM   = "text-align:center;white-space:nowrap;padding:1px 2px;font-size:9px;"
    NUM_B = "text-align:center;font-weight:bold;white-space:nowrap;padding:2px 3px;font-size:11px;"
    HDR_C = "text-align:center;font-weight:bold;white-space:nowrap;padding:2px 2px;font-size:9px;"
    HDR_R = "text-align:right;font-weight:bold;white-space:nowrap;padding:2px 3px;font-size:9px;"
    ITM_R = "text-align:right;word-wrap:break-word;padding:1px 3px;font-size:10px;"
    LBR   = "text-align:right;font-weight:bold;white-space:nowrap;padding:1px 3px;font-size:10px;"
    MID   = "text-align:center;vertical-align:middle;word-wrap:break-word;padding:2px;font-size:10px;"

    lines = []
    lines.append('<html><head><meta charset="utf-8"></head>')
    lines.append('<body style="%sfont-size:10px;color:#000;margin:0;padding:0;">' % FONT)

    if store_info.get("store_brand"):
        lines.append('<div style="text-align:center;font-weight:bold;font-size:20px;line-height:1.3;margin:2px 0;">%s</div>' % esc(store_info["store_brand"]))
    if store_info.get("store_name"):
        lines.append('<div style="text-align:center;font-weight:bold;font-size:14px;line-height:1.2;">%s</div>' % esc(store_info["store_name"]))
    if store_info.get("store_tagline"):
        lines.append('<div style="text-align:center;font-size:10px;line-height:1.2;margin-bottom:2px;">%s</div>' % esc(store_info["store_tagline"]))

    # جدول المعلومات — 4 أعمدة fixed
    lines.append('<table border="1" cellspacing="0" cellpadding="0" style="%s">' % TI)
    lines.append('<colgroup><col width="20%"><col width="24%"><col width="36%"><col width="20%"></colgroup>')
    for val1, lbl1, val2_html, lbl2 in [
        (esc(str(invoice_result["invoice_number"])), "رقم الفاتوره", date_cell_html,          "التاريخ"),
        (esc(card_number),                           "رقم البطاقه",  esc(cashier_name or "-"), "الكاشير"),
        (esc(customer_name),                          "اسم العميل",   esc(machine_number),      "الماكينة"),
    ]:
        lines.append('<tr><td style="%s">%s</td><td style="%s">%s</td><td style="%s">%s</td><td style="%s">%s</td></tr>'
            % (VAL_R, val1, LBL, lbl1, VAL_WR, val2_html, LBL, lbl2))
    lines.append('</table>')

    # جدول الأصناف + الإجماليات + الدعم — 4 أعمدة fixed
    lines.append('<table border="1" cellspacing="0" cellpadding="0" style="%s">' % TS)
    lines.append('<colgroup><col width="18%"><col width="14%"><col width="10%"><col width="58%"></colgroup>')

    lines.append('<tr><td style="%s">الإجمالي</td><td style="%s">السعر</td><td style="%s">الكمية</td><td style="%s">الصنف</td></tr>'
        % (HDR_C, HDR_C, HDR_C, HDR_R))

    for item in cart_items:
        lt = round(item["quantity"] * item["unit_price"], 2)
        lines.append('<tr><td style="%s">%.2f</td><td style="%s">%g</td><td style="%s">%g</td><td style="%s">%s</td></tr>'
            % (NUM, lt, NUM, item["unit_price"], NUM, item["quantity"], ITM_R, esc(item["name"])))

    lines.append('<tr><td colspan="4" style="%s"></td></tr>' % SEP)
    lines.append('<tr><td colspan="2" style="%s">%.2f</td><td colspan="2" style="%s">الإجمالي</td></tr>'
        % (NUM_B, invoice_result["grand_total"], LBR))
    lines.append('<tr><td colspan="2" style="%s">%.2f</td><td colspan="2" style="%s">الإجمالي+الخدمة</td></tr>'
        % (NUM_B, total_with_service, LBR))

    lines.append('<tr><td colspan="4" style="%s"></td></tr>' % SEP)

    count_html = '<b style="font-size:10px;">عدد الأصناف</b><br><b style="font-size:15px;">%d</b>' % len(cart_items)
    lines.append('<tr><td colspan="2" rowspan="3" style="%s">%s</td><td style="%s">%.2f</td><td style="%s">الدعم</td></tr>'
        % (MID, count_html, NUM_B, support_total, LBR))
    lines.append('<tr><td style="%s">%.2f</td><td style="%s">المطلوب</td></tr>' % (NUM_B, required_amount, LBR))
    lines.append('<tr><td style="%s">%.2f</td><td style="%s">المتبقي</td></tr>' % (NUM_B, remaining_amount, LBR))
    lines.append('</table>')

    pm = invoice_result.get("payment_method", "")
    if pm == "credit":
        lines.append('<div style="text-align:center;font-weight:bold;margin-top:1px;font-size:10px;">** البيع بالآجل - على حساب العميل **</div>')
    elif pm in ("visa", "instapay", "wallet"):
        pm_labels = {"visa": "فيزا", "instapay": "إنستا باي", "wallet": "محفظة"}
        lines.append('<div style="text-align:center;margin-top:1px;font-size:10px;">طريقة الدفع: %s</div>' % pm_labels[pm])

    combined = []
    if store_info.get("store_address"):
        combined.append("<b>%s</b>" % esc(store_info["store_address"]))
    if store_info.get("store_phone"):
        combined.append(esc(store_info["store_phone"]))
    if combined:
        lines.append('<table border="1" cellspacing="0" cellpadding="2" style="%s">' % TA)
        lines.append('<tr><td style="text-align:center;font-size:9px;">%s</td></tr>' % "<br>".join(combined))
        lines.append('</table>')

    lines.append('</body></html>')
    return "".join(lines)

def print_receipt(receipt_text: str, receipt_html: str = None):
    cfg = config.load_config()
    mode = cfg.get("printer_mode", "windows_default")

    if mode == "escpos_usb":
        _print_escpos(receipt_text, cfg)
    elif receipt_html:
        import print_utils
        print_utils.print_html_direct(receipt_html)
    else:
        _print_windows_default(receipt_text)


def _print_escpos(receipt_text, cfg):
    try:
        from escpos.printer import Usb
        vendor_id = int(cfg["printer_vendor_id"], 16)
        product_id = int(cfg["printer_product_id"], 16)
        p = Usb(vendor_id, product_id)
        p.set(align="right")
        p.text(receipt_text + "\n\n\n")
        p.cut()
    except Exception as e:
        raise RuntimeError(
            f"تعذّرت الطباعة عبر USB (escpos). تأكد من توصيل الطابعة وتعريفها بـ Zadig.\nالتفاصيل: {e}"
        )


def _print_windows_default(receipt_text):
    """
    يحفظ الفاتورة في ملف مؤقت ويطبعه على طابعة ويندوز الافتراضية.
    يعمل فقط على ويندوز (بعد تجميع البرنامج كـ exe).
    """
    if os.name != "nt":
        # فى بيئة تطوير غير ويندوز، نكتفي بحفظ الملف للمعاينة
        tmp_path = os.path.join(tempfile.gettempdir(), "receipt_preview.txt")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)
        print(f"[معاينة الفاتورة فقط - مش هنقدر نطبع فعليًا على غير ويندوز]\n{tmp_path}")
        return

    import win32print
    import win32ui

    printer_name = win32print.GetDefaultPrinter()
    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)
    hDC.StartDoc("فاتورة")
    hDC.StartPage()

    font = win32ui.CreateFont({"name": "Consolas", "height": 34})
    hDC.SelectObject(font)

    y = 50
    for line in receipt_text.split("\n"):
        hDC.TextOut(50, y, line)
        y += 40

    hDC.EndPage()
    hDC.EndDoc()
    hDC.DeleteDC()
