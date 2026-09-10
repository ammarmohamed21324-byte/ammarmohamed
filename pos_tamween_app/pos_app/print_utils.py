# -*- coding: utf-8 -*-
"""
أداة طباعة موحّدة تستخدمها أي شاشة في البرنامج: تبني مستند منسّق فعليًا (عنوان + جدول بيانات كامل)
وتطبعه عن طريق نافذة طباعة ويندوز العادية. مش بتاخد "سكرين شوت" من الشاشة خالص - البيانات
بتتجاب من نفس المصدر اللي بيملأ الجدول على الشاشة، فأي صف حتى لو مش ظاهر على الشاشة (محتاج سكرول)
بيتطبع عادي.
"""
import html as html_lib

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QTextDocument, QPageSize, QPageLayout
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog


def _esc(value):
    return html_lib.escape("" if value is None else str(value))


def build_report_html(title, meta_lines=None, sections=None, footer_lines=None):
    """
    يبني مستند HTML بسيط ومنسق لأي تقرير أو فاتورة، جاهز للطباعة.

    ملحوظة مهمة: عشان نضمن إن ترتيب الأعمدة يطلع صح على أي طابعة (بعض الطابعات
    بتقلب ترتيب أعمدة الجدول لو اعتمدنا على خاصية RTL بتاعة Qt)، إحنا مش بنعتمد
    على dir="rtl" للترتيب - إحنا بنكتب الأعمدة نفسها بترتيب معكوس يدويًا، فتطلع
    صح مهما كانت الطابعة.

    title: عنوان الورقة (بيظهر كبير فوق).
    meta_lines: قايمة أسطر معلومات (زي التاريخ، رقم الفاتورة...) - كل سطر بيتحط
        في جدول بخانة لوحده، وبيتقسم تلقائي لعمود تسمية وعمود قيمة لو فيه ":" فيه.
    sections: قايمة من dicts، كل واحد فيها ممكن يكون:
        {"heading": "عنوان القسم (اختياري)",
         "headers": ["عمود1", "عمود2", ...],
         "rows": [["قيمة1", "قيمة2", ...], ...]}
        كل عناصر rows بتتحول لنص ويتعمل لها escape تلقائي، فمينفعش يبعت HTML خام فيها.
    footer_lines: قايمة أسطر بتتحط في الآخر (زي الإجمالي) - بنفس منطق meta_lines.
    """
    parts = [
        '<html><head><meta charset="utf-8"></head>',
        '<body style="font-family: Arial, Tahoma, sans-serif; font-size:16px; color:#1a1a1a; text-align:right;">',
        f'<table width="100%"><tr><td style="text-align:center;">'
        f'<span style="font-size:26px; font-weight:bold;">{_esc(title)}</span></td></tr></table>',
    ]

    def info_table(lines):
        parts.append(
            '<table border="1" cellspacing="0" cellpadding="8" '
            'style="width:100%; border-collapse:collapse; margin:10px 0; font-size:15px;">'
        )
        for line in lines:
            if ":" in line:
                label, value = line.split(":", 1)
                # عمودين منفصلين: التسمية لوحدها والقيمة لوحدها قدامها (مش نص واحد مدموج)
                # وبترتيب معكوس يدويًا: القيمة أولًا (تطلع شمال) والتسمية بعدها (تطلع يمين)
                parts.append(
                    f'<tr><td style="text-align:right;">{_esc(value.strip())}</td>'
                    f'<td style="text-align:right; font-weight:bold; width:35%;">{_esc(label.strip())}</td></tr>'
                )
            else:
                parts.append(f'<tr><td colspan="2" style="text-align:right;">{_esc(line)}</td></tr>')
        parts.append('</table>')

    if meta_lines:
        info_table(meta_lines)

    for section in (sections or []):
        heading = section.get("heading")
        if heading:
            parts.append(f'<h2 style="margin-top:22px; margin-bottom:8px; font-size:20px;">{_esc(heading)}</h2>')
        headers = section.get("headers")
        rows = section.get("rows", [])
        if headers:
            parts.append(
                '<table border="1" cellspacing="0" cellpadding="10" '
                'style="width:100%; border-collapse:collapse; margin-bottom:16px; font-size:16px;">'
            )
            parts.append('<tr style="background:#eef3fa; font-weight:bold;">')
            for h in reversed(headers):  # ترتيب معكوس يدويًا عشان يطلع صح مهما كانت الطابعة
                parts.append(f'<th style="padding:10px; text-align:right;">{_esc(h)}</th>')
            parts.append('</tr>')
            for row in rows:
                parts.append('<tr>')
                for cell in reversed(row):
                    parts.append(f'<td style="padding:10px; text-align:right;">{_esc(cell)}</td>')
                parts.append('</tr>')
            parts.append('</table>')

    if footer_lines:
        info_table(footer_lines)

    parts.append('</body></html>')
    return "".join(parts)


def _set_rtl(document):
    """
    بيفرض اتجاه الكتابة RTL على المستند نفسه (مش بس على وسم dir في الـ HTML)،
    لأن محرك الطباعة الفعلي في Qt أحيانًا بيتجاهل اتجاه الـ HTML وبيطبع بعكس
    الاتجاه، حتى لو المعاينة على الشاشة كانت شكلها صح.
    """
    option = document.defaultTextOption()
    option.setTextDirection(Qt.RightToLeft)
    document.setDefaultTextOption(option)


def print_html_direct(html_content):
    """
    زي print_html بالظبط، لكن من غير ما يفتح نافذة اختيار طابعة - بيطبع على طول
    على الطابعة الافتراضية في ويندوز، وبنفس مقاس الورق المظبوط عليها (مفيد للإيصالات
    اللي المفروض تطبع فورًا من غير ما حد يختار حاجة في كل عملية بيع).
    """
    printer = QPrinter(QPrinter.HighResolution)
    # هامش أمان صغير جدًا (2 مم) عشان بعض الطابعات الحرارية بتحسب "عرض الورقة"
    # بشكل مختلف شوية عن اللي البرنامج حاسبه، فبتقص حتة صغيرة من الحافة من غير الهامش ده
    printer.setPageMargins(2, 2, 2, 2, QPrinter.Millimeter)
    document = QTextDocument()
    _set_rtl(document)
    document.setHtml(html_content)
    document.setPageSize(printer.pageRect(QPrinter.Point).size())
    document.print_(printer)


def print_html(html_content, parent=None, dialog_title="طباعة"):
    """يفتح نافذة طباعة ويندوز العادية ويطبع مستند HTML منسّق (مش صورة شاشة) على ورقة A4 عادية."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageOrientation(QPageLayout.Portrait)

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(dialog_title)
    if dialog.exec_() != QPrintDialog.Accepted:
        return False

    document = QTextDocument()
    document.setDefaultStyleSheet("body { font-size: 15px; }")
    _set_rtl(document)
    document.setHtml(html_content)
    document.setPageSize(printer.pageRect(QPrinter.Point).size())
    document.print_(printer)
    return True


def add_html_print_button(layout, html_provider, parent=None, label="🖶 طباعة"):
    """
    يضيف زرار طباعة جاهز لأي layout. html_provider ممكن يكون نص HTML جاهز،
    أو دالة (callable) بترجع نص الـ HTML وقت الضغط على الزرار (مفيد لو البيانات بتتغيّر).
    """
    def do_print():
        content = html_provider() if callable(html_provider) else html_provider
        print_html(content, parent)

    btn = QPushButton(label)
    btn.clicked.connect(do_print)
    layout.addWidget(btn)
    return btn


def print_widget(widget, parent=None):
    """
    (طريقة قديمة - بتاخد صورة من الشاشة زي ما هي بالظبط). فضلت موجودة للتوافق،
    لكن الأفضل استخدام print_html/build_report_html لأي تقرير أو جدول بيانات
    عشان الطباعة تطلع منسقة وكاملة مش سكرين شوت.
    """
    printer = QPrinter(QPrinter.HighResolution)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("طباعة")
    if dialog.exec_() != QPrintDialog.Accepted:
        return False

    pixmap = widget.grab()
    painter = QPainter(printer)
    rect = painter.viewport()
    size = pixmap.size()
    size.scale(rect.size(), Qt.KeepAspectRatio)
    painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
    painter.setWindow(pixmap.rect())
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return True


def add_print_button(layout, widget_to_print, parent=None, label="🖶 طباعة"):
    """(طريقة قديمة) زرار بيطبع صورة الشاشة. استخدم add_html_print_button بدالها في أي جدول بيانات."""
    btn = QPushButton(label)
    btn.clicked.connect(lambda: print_widget(widget_to_print, parent))
    layout.addWidget(btn)
    return btn
