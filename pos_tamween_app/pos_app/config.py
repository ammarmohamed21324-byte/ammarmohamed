# -*- coding: utf-8 -*-
"""
إعدادات البرنامج: بيانات الاتصال بقاعدة البيانات وبيانات المحل.
الإعدادات بتتخزن في ملف config.json بجانب البرنامج، وأول مرة تشغيل بيتم
إنشاء الملف بقيم افتراضية ويقدر المستخدم يعدلها من شاشة الإعدادات داخل البرنامج.
"""
import json
import os
import sys


def get_base_dir():
    """المسار الأساسي للبرنامج (يشتغل صح سواء .py أو .exe بعد التجميع)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(get_base_dir(), "config.json")

DEFAULT_CONFIG = {
    "store_brand": "",
    "store_name": "محل التموين",
    "store_tagline": "",
    "store_address": "",
    "store_phone": "",
    "machine_number": "1",
    "db_host": "127.0.0.1",   # اكتب هنا الـ IP بتاع جهاز السيرفر داخل المحل
    "db_port": 3306,
    "db_user": "pos_user",
    "db_password": "pos_pass",
    "db_name": "pos_tamween",
    "printer_mode": "windows_default",  # "escpos_usb" أو "windows_default"
    "printer_vendor_id": "0x04b8",
    "printer_product_id": "0x0202",
    "receipt_width": 32,
    "backup_enabled": True,
    "backup_folder": "",              # لو فاضي، بيستخدم مجلد "backups" جنب البرنامج
    "mysqldump_path": "mysqldump",    # المسار الكامل لو مش موجود في PATH
    "mysql_cli_path": "mysql",        # نفس الفكرة، لكن لأداة الاسترجاع
    "backup_retention_days": 14,
    "last_backup_date": ""
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
