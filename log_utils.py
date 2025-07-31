from functools import wraps
from flask import request, session
from datetime import datetime
import os
import csv

LOG_FILE = "activity_log.csv"

def log_event(event="", request_type=""):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_id = session.get("id", "غير مسجل")
            user_role = session.get("role", "غير معروف")
            user_name = session.get("name", "مجهول")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ip = request.remote_addr

            log_data = [timestamp, user_id, user_name, user_role, ip, event, request_type, request.path]

            file_exists = os.path.isfile(LOG_FILE)
            with open(LOG_FILE, mode='a', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(['الوقت', 'رقم الهوية', 'الاسم', 'الدور', 'IP', 'الحدث', 'نوع الطلب', 'المسار'])
                writer.writerow(log_data)

            return func(*args, **kwargs)
        return wrapper
    return decorator

def log_action(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, "SYSTEM", "", "", "", message, "", ""])
