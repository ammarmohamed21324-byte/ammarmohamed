# -*- coding: utf-8 -*-
"""
نسخ احتياطي تلقائي لقاعدة البيانات باستخدام mysqldump.
البرنامج بيعمل نسخة (ملف .sql) كل يوم مرة (أول ما تفتح البرنامج في يوم جديد)،
وبيحتفظ بآخر N يوم بس ويمسح الأقدم عشان القرص مايمتلئش.

مهم جدًا: لحماية حقيقية من عطل الجهاز نفسه، لازم مجلد النسخ الاحتياطية يكون
في مكان تاني غير هارد الجهاز ده (فلاشة، هارد خارجي، أو مجلد على جهاز تاني
في نفس الشبكة) - مش مجلد على نفس الجهاز بس.
"""
import os
import subprocess
import datetime
import glob

import config


def get_backup_folder(cfg):
    folder = cfg.get("backup_folder", "").strip()
    if not folder:
        folder = os.path.join(config.get_base_dir(), "backups")
    os.makedirs(folder, exist_ok=True)
    return folder


def is_backup_due_today(cfg):
    if not cfg.get("backup_enabled", True):
        return False
    today = datetime.date.today().isoformat()
    return cfg.get("last_backup_date", "") != today


def run_backup(cfg=None):
    """
    يعمل نسخة احتياطية فورية بغض النظر عن تاريخ آخر نسخة.
    يرجع (success: bool, message: str, file_path: str|None)
    """
    if cfg is None:
        cfg = config.load_config()

    folder = get_backup_folder(cfg)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    file_name = f"pos_tamween_backup_{timestamp}.sql"
    file_path = os.path.join(folder, file_name)

    mysqldump_path = cfg.get("mysqldump_path", "mysqldump") or "mysqldump"
    cmd = [
        mysqldump_path,
        f"-h{cfg['db_host']}",
        f"-P{cfg['db_port']}",
        f"-u{cfg['db_user']}",
        f"-p{cfg['db_password']}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--set-gtid-purged=OFF",
        cfg["db_name"],
    ]

    try:
        with open(file_path, "wb") as f:
            result = subprocess.run(
                cmd, stdout=f, stderr=subprocess.PIPE, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        if result.returncode != 0:
            error_text = result.stderr.decode("utf-8", errors="ignore")
            if os.path.exists(file_path):
                os.remove(file_path)
            return False, f"فشل عمل النسخة الاحتياطية:\n{error_text}", None

        if os.path.getsize(file_path) == 0:
            os.remove(file_path)
            return False, "النسخة الاحتياطية طلعت فاضية، تأكد من بيانات الاتصال بقاعدة البيانات.", None

    except FileNotFoundError:
        return False, (
            "تعذّر إيجاد أداة mysqldump. تأكد إن MySQL متثبت، أو اكتب المسار الكامل "
            "لملف mysqldump.exe في إعدادات النسخ الاحتياطي."
        ), None
    except subprocess.TimeoutExpired:
        return False, "استغرقت عملية النسخ وقت طويل جدًا وتم إلغاؤها.", None
    except Exception as e:
        return False, f"حصل خطأ غير متوقع أثناء النسخ الاحتياطي:\n{e}", None

    cfg["last_backup_date"] = datetime.date.today().isoformat()
    config.save_config(cfg)

    cleanup_old_backups(folder, cfg.get("backup_retention_days", 14))

    return True, f"تم عمل نسخة احتياطية بنجاح:\n{file_path}", file_path


def cleanup_old_backups(folder, retention_days):
    """يمسح ملفات النسخ الاحتياطية الأقدم من عدد الأيام المحدد."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        pattern = os.path.join(folder, "pos_tamween_backup_*.sql")
        for file_path in glob.glob(pattern):
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
            if mtime < cutoff:
                os.remove(file_path)
    except Exception:
        pass  # تنظيف النسخ القديمة مش عملية حرجة، لو فشلت مايهمش


def restore_backup(cfg, file_path):
    """
    يرجّع قاعدة البيانات لحالة نسخة احتياطية معينة (بيمسح البيانات الحالية ويحطّ مكانها بيانات النسخة).
    يرجع (success: bool, message: str)
    """
    if not os.path.exists(file_path):
        return False, "الملف المحدد غير موجود."

    mysql_cli_path = cfg.get("mysql_cli_path", "mysql") or "mysql"
    cmd = [
        mysql_cli_path,
        f"-h{cfg['db_host']}",
        f"-P{cfg['db_port']}",
        f"-u{cfg['db_user']}",
        f"-p{cfg['db_password']}",
        "--default-character-set=utf8mb4",
        cfg["db_name"],
    ]

    try:
        with open(file_path, "rb") as f:
            result = subprocess.run(
                cmd, stdin=f, stderr=subprocess.PIPE, timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        if result.returncode != 0:
            error_text = result.stderr.decode("utf-8", errors="ignore")
            return False, f"فشل الاسترجاع:\n{error_text}"
    except FileNotFoundError:
        return False, (
            "تعذّر إيجاد أداة mysql. تأكد إن MySQL متثبت، أو اكتب المسار الكامل "
            "لملف mysql.exe في إعدادات النسخ الاحتياطي."
        )
    except subprocess.TimeoutExpired:
        return False, "استغرقت عملية الاسترجاع وقت طويل جدًا وتم إلغاؤها."
    except Exception as e:
        return False, f"حصل خطأ غير متوقع أثناء الاسترجاع:\n{e}"

    return True, "تم استرجاع النسخة الاحتياطية بنجاح. أعد تشغيل البرنامج على كل الأجهزة."


def list_backups(cfg=None):
    if cfg is None:
        cfg = config.load_config()
    folder = get_backup_folder(cfg)
    pattern = os.path.join(folder, "pos_tamween_backup_*.sql")
    files = sorted(glob.glob(pattern), reverse=True)
    return [
        {"path": f, "name": os.path.basename(f), "size_kb": round(os.path.getsize(f) / 1024, 1),
         "modified": datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")}
        for f in files
    ]
