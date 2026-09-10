# -*- coding: utf-8 -*-
"""
نظام فترة تجريبية بسيط بيشتغل من غير إنترنت خالص.
الفكرة:
- أول مرة البرنامج يتفتح، بيسجل تاريخ التركيب وبيولّد "كود جهاز" ثابت وعشوائي.
- كل مرة بعد كده، البرنامج بيحسب عدد الأيام من تاريخ التركيب.
- لو عدّى عدد أيام الفترة التجريبية ولسه مش "مفعّل"، البرنامج يوقف عند شاشة قفل
  (من غير ما يلمس قاعدة البيانات خالص - البيانات فاضلة زي ما هي).
- عشان يتفتح تاني، صاحب المحل بيقرالك "كود الجهاز" اللي ظاهر على الشاشة،
  وانت بتستخدم أداة "keygen.py" (منفصلة، عندك انت بس، متتبعتش مع البرنامج)
  عشان تطلع "كود تفعيل" بيطابقه بس هو، وتديله للعميل يكتبه.
"""
import os
import hmac
import hashlib
import secrets
import datetime

import config

# نفس المفتاح لازم يكون موجود في keygen.py (عندك انت بس) - متتبعتش الأداة دي
# مع البرنامج للعميل أبدًا، ولو غيّرت المفتاح هنا لازم تغيّره هناك كمان.
SECRET_KEY = b"tamween-pos-secret-key-change-me-2026"

DEFAULT_TRIAL_DAYS = 10


def _license_path():
    return os.path.join(config.get_base_dir(), "license.json")


def _load():
    import json
    path = _license_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    import json
    path = _license_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_or_create_machine_code():
    """كود ثابت لكل تركيب - بيتولّد مرة واحدة بس ويفضل ثابت بعد كده."""
    data = _load()
    if not data.get("machine_code"):
        data["machine_code"] = secrets.token_hex(4).upper()  # زي "A1B2C3D4"
        _save(data)
    return data["machine_code"]


def _ensure_install_date(data):
    if not data.get("install_date"):
        data["install_date"] = datetime.date.today().isoformat()
        _save(data)
    return data["install_date"]


def compute_unlock_code(machine_code):
    """بتحسب كود التفعيل الصحيح لكود جهاز معين - نفس الدالة موجودة في keygen.py."""
    digest = hmac.new(SECRET_KEY, machine_code.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:8].upper()


def get_trial_status(trial_days=DEFAULT_TRIAL_DAYS):
    """
    يرجع dict فيه:
    - activated: مفعّل نهائي ولا لأ
    - machine_code: كود الجهاز
    - days_left: كام يوم فاضل (ممكن يكون سالب لو انتهت)
    - is_locked: هل المفروض يتقفل دلوقتي
    """
    data = _load()
    machine_code = get_or_create_machine_code()
    install_date_str = _ensure_install_date(data)
    install_date = datetime.date.fromisoformat(install_date_str)
    days_passed = (datetime.date.today() - install_date).days
    days_left = trial_days - days_passed

    activated = bool(data.get("activated", False))
    return {
        "activated": activated,
        "machine_code": machine_code,
        "days_left": days_left,
        "is_locked": (not activated) and (days_left < 0),
    }


def try_activate(entered_code):
    """لو الكود صح، بيفعّل البرنامج نهائيًا وبيرجع True. البيانات مش بتتلمس خالص."""
    data = _load()
    machine_code = get_or_create_machine_code()
    expected = compute_unlock_code(machine_code)
    if entered_code.strip().upper() == expected:
        data["activated"] = True
        data["machine_code"] = machine_code
        _save(data)
        return True
    return False
