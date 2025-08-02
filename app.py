from flask import Flask, render_template, request, redirect, session, send_from_directory, flash, url_for, send_file, jsonify
import pandas as pd
import json
import os
from datetime import datetime
from openpyxl import Workbook
from functools import wraps
from log_utils import log_action, log_event
from notification.email import send_email
from itsdangerous import URLSafeTimedSerializer
import csv
LOG_FILE = "logs.csv"

app = Flask(__name__)
app.secret_key = 'zawk-secret'
SECRET_KEY = 'zawk-secret'  # نفسه الموجود في app.secret_key
SECURITY_SALT = 'reset-salt'  # يمكنك تغييره لو أحببت

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    return serializer.dumps(email, salt=SECURITY_SALT)

def verify_reset_token(token, expiration=3600):  # صالح لمدة ساعة
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    try:
        return serializer.loads(token, salt=SECURITY_SALT, max_age=expiration)
    except:
        return None

# ✅ تعريف مسارات الملفات (ثابتة)
EMPLOYEE_FILE = 'employees.csv'
REQUEST_FILE = 'requests.csv'
EVALUATION_FILE = 'evaluations.csv'
MESSAGE_FILE = 'messages.xlsx'

def log_action(name, id_number, role, branch, event, request_type='', request_id=''):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = request.remote_addr
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([name, id_number, role, branch, event, request_type, request_id, now, ip])

def log_event(event="", request_type="", request_id_key=""):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'id' in session:
                request_id = request.form.get(request_id_key) if request_id_key else ""
                log_action(
                    name=session.get('name', ''),
                    id_number=session.get('id', ''),
                    role=session.get('role', ''),
                    branch=session.get('branch', ''),
                    event=event or f.__name__,
                    request_type=request_type,
                    request_id=request_id
                )
            return f(*args, **kwargs)
        return wrapper
    return decorator


def sync_evaluations():
    now = datetime.now()
    period = f"{now.year}-H1" if now.month <= 6 else f"{now.year}-H2"

    employees_path = 'employees.csv'
    if not os.path.exists(employees_path):
        print("⚠️ ملف الموظفين غير موجود.")
        return

    df_emp = pd.read_csv(employees_path, encoding='utf-8-sig')
    df_emp.columns = df_emp.columns.str.strip()

    # التأكد من الأعمدة الأساسية
    if 'رقم الهوية' not in df_emp.columns:
        print("⚠️ لا يوجد عمود 'رقم الهوية'")
        return

    df_emp['الاسم'] = df_emp['الاسم'] if 'الاسم' in df_emp.columns else ''
    df_emp['الفرع'] = df_emp['الفرع'] if 'الفرع' in df_emp.columns else ''
    df_emp['الدور'] = df_emp['الوظيفة'] if 'الوظيفة' in df_emp.columns else ''

    # قراءة ملف التقييمات
    eval_path = 'evaluations.csv'
    if os.path.exists(eval_path):
        df_eval = pd.read_csv(eval_path, encoding='utf-8-sig')
    else:
        df_eval = pd.DataFrame(columns=[
            'رقم الهوية', 'الاسم', 'الفرع', 'الدور', 'period',
            'punctuality', 'discipline', 'behavior', 'attendance',
            'total_score', 'evaluator', 'evaluation_date', 'bonus_percentage'
        ])

    df_eval.fillna('', inplace=True)

    # ✅ حذف الموظفين الذين لم يعودوا موجودين
    existing_ids = df_emp['رقم الهوية'].astype(str).tolist()
    df_eval = df_eval[df_eval['رقم الهوية'].astype(str).isin(existing_ids)]

    # التحقق من الموظفين الذين لم يُقيّموا بعد للفترة الحالية
    existing_ids_for_period = df_eval[df_eval['period'] == period]['رقم الهوية'].astype(str).tolist()
    new_rows = []

    for _, row in df_emp.iterrows():
        eid = str(row['رقم الهوية'])
        if eid not in existing_ids_for_period:
            new_rows.append({
                'رقم الهوية': eid,
                'الاسم': row['الاسم'],
                'الفرع': row['الفرع'],
                'الدور': row['الدور'],
                'period': period,
                'punctuality': '',
                'discipline': '',
                'behavior': '',
                'attendance': '',
                'total_score': '',
                'evaluator': '',
                'evaluation_date': '',
                'bonus_percentage': ''
            })

    if new_rows:
        df_eval = pd.concat([df_eval, pd.DataFrame(new_rows)], ignore_index=True)
        print(f"✅ تمت إضافة {len(new_rows)} سطر جديد للفترة {period}.")
    else:
        print(f"ℹ️ لا يوجد تقييمات جديدة للفترة {period}.")

    df_eval.to_csv(eval_path, index=False, encoding='utf-8-sig')
def get_unread_count_for_user(user_id):
    try:
        df = pd.read_excel("messages.xlsx")
        return len(df[(df['ReceiverID'] == user_id) & (df['Status'] == 'Unread')])
    except:
        return 0


if not os.path.exists(REQUEST_FILE):
    pd.DataFrame(columns=[
        'رقم الهوية', 'اسم الموظف', 'الدور', 'الفرع', 'نوع الطلب',
        'تاريخ البداية', 'تاريخ النهاية', 'عدد الساعات', 'تاريخ التنفيذ',
        'تفاصيل', 'الحالة', 'تاريخ الطلب', 'تاريخ الموافقة الأولى', 'تاريخ الموافقة الثانية'
    ]).to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')

LOG_FILE = 'logs.csv'

# إنشاء ملف السجلات إذا لم يكن موجودًا
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=[
        'الاسم', 'الرقم الوظيفي', 'الدور', 'الفرع', 
        'الحدث', 'نوع الطلب', 'رقم الطلب', 
        'التاريخ والوقت', 'IP المستخدم'
    ]).to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
def log_action(name, id_number, role, branch, event, request_type=None, request_id=None):
    ip = request.remote_addr
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # تحميل السجلات الحالية
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE, encoding='utf-8-sig')
    else:
        df = pd.DataFrame(columns=[
            'الاسم', 'الرقم الوظيفي', 'الدور', 'الفرع',
            'الحدث', 'نوع الطلب', 'رقم الطلب',
            'التاريخ والوقت', 'IP المستخدم'
        ])

    # إضافة السجل الجديد
    df.loc[len(df)] = [
        name, id_number, role, branch,
        event, request_type, request_id,
        timestamp, ip
    ]

    # حفظ التحديث في الملف
    df.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')

@app.route('/confirm_return', methods=['POST'])
def confirm_return():
    if 'id' not in session or session['role'] != 'مدير':
        return redirect('/login')

    req_id = int(request.form['request_id'])
    action = request.form['action']
    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    df['تاريخ بداية الإجازة'] = df.get('تاريخ البداية', '')
    df['تاريخ نهاية الإجازة'] = df.get('تاريخ النهاية', '')


    idx = df.index[df['رقم الطلب'] == req_id].tolist()
    if not idx:
        return "طلب غير موجود"

    i = idx[0]
    if df.at[i, 'الفرع'] != session['branch']:
        return "غير مصرح لك تعديل هذا الطلب"

    if action == 'returned':
        return_date = request.form['return_date']
        df.at[i, 'تاريخ مباشرة العمل'] = return_date
        df.at[i, 'حالة المباشرة'] = 'تمت المباشرة'
    elif action == 'not_returned':
        df.at[i, 'تاريخ مباشرة العمل'] = ''
        df.at[i, 'حالة المباشرة'] = 'لم يعد'

    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    return redirect('/manager_vacations')



@app.route('/')
@log_event(event="عرض الصفحة الرئيسية", request_type="عرض")
def home():
    return redirect('/login')


@app.route('/login', methods=['GET', 'POST'])
@log_event(event="تسجيل دخول", request_type="المصادقة")
def login():
    if request.method == 'POST':
        id_number = request.form['id_number']
        password = request.form['password']

        df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')

        # تنظيف القيم والتعامل مع القيم الفارغة
        df['رقم الهوية'] = df['رقم الهوية'].astype(str).str.strip()
        df['كلمة المرور'] = df['كلمة المرور'].fillna('').astype(str).str.strip()
        df['الاسم'] = df['الاسم'].astype(str).str.strip()
        df['الدور'] = df['الدور'].astype(str).str.strip()
        df['الفرع'] = df['الفرع'].astype(str).str.strip()
        df['رقم الهاتف'] = df['رقم الهاتف'].astype(str).str.strip()

        for _, row in df.iterrows():
            if row['رقم الهوية'] == id_number and row['كلمة المرور'] == password:
                session['id'] = row['رقم الهوية']
                session['name'] = row['الاسم']
                session['role'] = row['الدور']
                session['branch'] = row['الفرع']
                session['phone'] = row['رقم الهاتف']
                log_action(session['name'], session['id'], session['role'], session['branch'], 'تسجيل دخول')
                return redirect('/dashboard')

        return 'رقم الهوية أو كلمة المرور غير صحيحة'
    return render_template('login.html')

@app.route('/hr_dashboard')
@log_event(event="عرض لوحة الموارد البشرية", request_type="عرض")
def hr_dashboard():
    if 'id' not in session or session['role'] != 'موارد بشرية':
        return redirect('/login')

    # ✅ حساب عدد الرسائل غير المقروءة
    unread_count = get_unread_count_for_user(session['id'])

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')

    pending = df[(df['الحالة'] == 'مقبول') & (df['تاريخ الموافقة الأولى'].notna())]
    completed = df[df['الحالة'].isin([
        'مقبول نهائيًا', 'مرفوض من الموارد البشرية', 'مرفوض من المدير', 'مرفوض من المشرف'
    ])]

    pending = pending.sort_values(by='تاريخ الطلب', ascending=False)
    completed = completed.sort_values(by='تاريخ الطلب', ascending=False)

    vacation_notify_pending = df[
        (df['نوع الطلب'] == 'إجازة') &
        (df['تاريخ مباشرة العمل'].notna()) &
        ((df['تم إشعار الموارد بالمباشرة'].isna()) | (df['تم إشعار الموارد بالمباشرة'] == ""))
    ]

    # ✅ حساب عدد حالات رفض تأجيل الإجازة التي لم يُعاد إرسالها
    reject_count = 0
    two_year_file = 'two_year_leave_decisions.csv'
    if os.path.exists(two_year_file):
        df_two = pd.read_csv(two_year_file, encoding='utf-8-sig')
        df_rejected = df_two[
            (df_two['القرار / Decision'] == 'لا أوافق / I Disagree') &
            (df_two.get('أُعيد الإرسال؟', '') != 'نعم')
        ]
        reject_count = df_rejected.shape[0]

    return render_template('hr_dashboard.html',
                           name=session['name'],
                           requests=pending.to_dict(orient='records'),
                           completed_requests=completed.to_dict(orient='records'),
                           vacation_notify_count=len(vacation_notify_pending),
                           reject_count=reject_count,
                           unread_count=unread_count)

@app.route('/logout')
@log_event(event="تسجيل الخروج", request_type="عملية")
def logout():
    session.clear()
    return redirect('/login')
# ✅ دالة لحساب عدد الرسائل غير المقروءة
def get_unread_count_for_user(user_id):
    try:
        df = pd.read_excel('messages.xlsx')
        df.fillna('', inplace=True)
        user_id = str(user_id)

        # تأكد من الأعمدة
        if 'PermanentlyDeletedBy' not in df.columns:
            df['PermanentlyDeletedBy'] = ''
        if 'DeletedBy' not in df.columns:
            df['DeletedBy'] = ''

        unread_df = df[
            (df['ReceiverID'].astype(str) == user_id) &
            (df['Status'] == 'Unread') &
            (~df['DeletedBy'].astype(str).str.contains(user_id, na=False)) &
            (~df['PermanentlyDeletedBy'].astype(str).str.contains(user_id, na=False))
        ]
        return unread_df.shape[0]
    except:
        return 0


@app.route('/dashboard')
@log_event(event="عرض لوحة القيادة", request_type="عرض")
def dashboard():
    if 'id' not in session:
        return redirect('/login')

    role = session['role']
    user_id = session['id']
    unread_count = get_unread_count_for_user(user_id)  # ✅ عدد الرسائل غير المقروءة
    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')

    for col in ['تاريخ بداية الإجازة', 'تاريخ نهاية الإجازة']:
        if col not in df.columns:
            df[col] = ""

    # ---------------- الموظف ------------------
    if role == 'موظف':
        id_number = session['id']
        my_requests = df[df['رقم الهوية'].astype(str) == id_number]
        my_requests = my_requests.sort_values(by='تاريخ الطلب', ascending=False)

        emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        match = emp_df[emp_df['رقم الهوية'].astype(str) == id_number]
        if not match.empty and 'مدة الاستحقاق (بالأيام)' in match.columns:
            try:
                eligibility_days = int(match.iloc[0]['مدة الاستحقاق (بالأيام)'])
            except:
                eligibility_days = 0
        else:
            eligibility_days = 0

        decision_file = 'two_year_leave_decisions.csv'
        already_decided = False
        if os.path.exists(decision_file):
            decision_df = pd.read_csv(decision_file, encoding='utf-8-sig')
            employee_decisions = decision_df[decision_df['رقم الهوية / ID'].astype(str) == id_number]
            if not employee_decisions.empty:
                latest_decision = employee_decisions.iloc[-1]
                if latest_decision['القرار / Decision'] == 'لا أوافق / I Disagree':
                    already_decided = False if latest_decision.get('أُعيد الإرسال؟', '') == 'نعم' else True
                else:
                    already_decided = True

        return render_template(
            'employee_dashboard.html',
            name=session['name'],
            my_requests=my_requests.to_dict(orient='records'),
            eligibility_days=eligibility_days,
            already_decided=already_decided,
            unread_count=unread_count
        )

    # ---------------- المدير ------------------
    elif role == 'مدير':
        branch = session['branch']

        two_year_file = 'two_year_leave_decisions.csv'
        reject_count = 0
        if os.path.exists(two_year_file):
            df_two = pd.read_csv(two_year_file, encoding='utf-8-sig')
            df_rejected = df_two[
                (df_two['الفرع / Branch'] == branch) &
                (df_two['القرار / Decision'] == 'لا أوافق / I Disagree') &
                (df_two['أُعيد الإرسال؟'] != 'نعم')
            ]
            reject_count = df_rejected.shape[0]

        pending = df[(df['الحالة'] == 'معلق') & (df['الفرع'] == branch)]
        final = df[(df['الحالة'].isin([
            'مقبول', 'مقبول نهائيًا', 'مرفوض من المدير',
            'مرفوض من المشرف', 'مرفوض من الموارد البشرية', 'مرفوض من المشرف العام'
        ])) & (df['الفرع'] == branch)]

        vacation_pending = df[
            (df['نوع الطلب'] == 'إجازة') &
            (df['الفرع'] == branch) &
            (df['الحالة'] == 'مقبول نهائيًا') &
            ((df['تاريخ مباشرة العمل'].isna()) | (df['تاريخ مباشرة العمل'] == '')) &
            ((df['حالة المباشرة'].isna()) | (df['حالة المباشرة'] != 'لم يعد'))
        ]
        vacation_badge_count = vacation_pending.shape[0]

        vacation_confirmed = df[
            (df['نوع الطلب'] == 'إجازة') &
            (df['الفرع'] == branch) &
            (
                (df['تاريخ مباشرة العمل'].notna() & (df['تاريخ مباشرة العمل'] != '')) |
                (df['حالة المباشرة'] == 'لم يعد')
            )
        ]

        pending = pending.sort_values(by='تاريخ الطلب', ascending=False)
        final = final.sort_values(by='تاريخ الطلب', ascending=False)

        emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        emp_branch = emp_df[emp_df['الفرع'] == branch][['رقم الهوية', 'الاسم']]
        employees = emp_branch.to_dict(orient='records')

        return render_template(
            'manager_dashboard.html',
            name=session['name'],
            branch=branch,
            pending_requests=pending.to_dict(orient='records'),
            final_requests=final.to_dict(orient='records'),
            employees=employees,
            vacation_pending=vacation_pending.to_dict(orient='records'),
            vacation_confirmed=vacation_confirmed.to_dict(orient='records'),
            vacation_badge_count=vacation_badge_count,
            reject_count=reject_count,
            unread_count=unread_count
        )

    # ---------------- الموارد البشرية ------------------
    elif role == 'موارد بشرية':
        pending = df[(df['الحالة'] == 'مقبول') & (df['تاريخ الموافقة الأولى'].notna())]
        completed = df[df['الحالة'].isin([
            'مقبول نهائيًا', 'مرفوض من الموارد البشرية',
            'مرفوض من المدير', 'مرفوض من المشرف'
        ])]

        pending = pending.sort_values(by='تاريخ الطلب', ascending=False)
        completed = completed.sort_values(by='تاريخ الطلب', ascending=False)

        reject_count = 0
        two_year_file = 'two_year_leave_decisions.csv'
        if os.path.exists(two_year_file):
            df_two = pd.read_csv(two_year_file, encoding='utf-8-sig')
            df_rejected = df_two[
                (df_two['القرار / Decision'] == 'لا أوافق / I Disagree') &
                (df_two.get('أُعيد الإرسال؟', '') != 'نعم')
            ]
            reject_count = df_rejected.shape[0]

        vacation_notify_pending = df[
            (df['نوع الطلب'] == 'إجازة') &
            (df['تاريخ مباشرة العمل'].notna()) &
            ((df['تم إشعار الموارد بالمباشرة'].isna()) | (df['تم إشعار الموارد بالمباشرة'] == ""))
        ]

        return render_template(
            'hr_dashboard.html',
            name=session['name'],
            requests=pending.to_dict(orient='records'),
            completed_requests=completed.to_dict(orient='records'),
            vacation_notify_count=len(vacation_notify_pending),
            reject_count=reject_count,
            unread_count=unread_count
        )

    # ---------------- المشرف العام ------------------
    elif role == 'مشرف عام':
        df = df.sort_values(by='تاريخ الطلب', ascending=False)

        reject_count = 0
        two_year_file = 'two_year_leave_decisions.csv'
        if os.path.exists(two_year_file):
            df_two = pd.read_csv(two_year_file, encoding='utf-8-sig')
            df_rejected = df_two[
                (df_two['القرار / Decision'] == 'لا أوافق / I Disagree') &
                (df_two.get('أُعيد الإرسال؟', '') != 'نعم')
            ]
            reject_count = df_rejected.shape[0]

        return render_template(
            'admin_dashboard.html',
            name=session['name'],
            requests=df.to_dict(orient='records'),
            reject_count=reject_count,
            unread_count=unread_count
        )

    return 'دور غير معروف'
@app.route('/review_two_year_leave')
def review_two_year_leave():
    if 'id' not in session or session['role'] != 'مدير':
        return redirect('/login')

    branch = session['branch']
    decision_file = 'two_year_leave_decisions.csv'
    emp_file = 'employees.csv'

    df = pd.read_csv(decision_file, encoding='utf-8-sig')
    emp_df = pd.read_csv(emp_file, encoding='utf-8-sig')

    # دمج ملف القرارات مع ملف الموظفين لإحضار مدة الاستحقاق
    merged = df.merge(emp_df[['رقم الهوية', 'مدة الاستحقاق (بالأيام)']], how='left',
                      left_on='رقم الهوية / ID', right_on='رقم الهوية')

    # إعادة التسمية لعرضها في HTML
    merged.rename(columns={'مدة الاستحقاق (بالأيام)': 'مدة الاستحقاق / Eligibility Days'}, inplace=True)

    # تصفية الفرع الخاص بالمدير
    filtered = merged[merged['الفرع / Branch'] == branch]

    return render_template('two_year_decisions_manager.html', decisions=filtered.to_dict(orient='records'))

@app.route('/logs')
@log_event(event="عرض سجل الأحداث", request_type="عرض")
def view_logs():
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    logs = []
    columns = []
    
    if os.path.exists(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE, encoding='utf-8-sig')
            df.fillna('', inplace=True)
            logs = df.to_dict(orient='records')
            columns = df.columns.tolist()
        except Exception as e:
            flash(f"⚠️ تعذر قراءة سجل الأحداث: {e}", "danger")

    return render_template('logs.html', logs=logs, columns=columns)


@app.route('/manager_action', methods=['POST'])
def manager_action():
    if 'id' not in session or session['role'] != 'مدير':
        return redirect('/login')

    index = int(request.form['index'])
    action = request.form['action']
    today = datetime.today().strftime('%Y-%m-%d')

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    pending = df[(df['الحالة'] == 'معلق') & (df['الفرع'] == session['branch'])].reset_index()

    if index >= len(pending):
        return "طلب غير صالح"

    row_index = pending.loc[index, 'index']
    if action == 'approve':
        df.at[row_index, 'الحالة'] = 'مقبول'
        df.at[row_index, 'تاريخ الموافقة الأولى'] = today
    elif action == 'reject':
        df.at[row_index, 'الحالة'] = 'مرفوض من المدير'
        df.at[row_index, 'تاريخ الموافقة الأولى'] = today

    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    # ✅ مباشرة بعد الحفظ
    log_action(session['name'], session['id'], session['role'], session['branch'], f"{action} من المدير", df.at[row_index, 'نوع الطلب'], row_index)

    # ✅ إشعار بالبريد الإلكتروني للموظف
    try:
        emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        emp_name = df.at[row_index, 'اسم الموظف']
        emp_row = emp_df[emp_df['الاسم'] == emp_name]

        if not emp_row.empty:
            emp_email = emp_row.iloc[0].get('البريد', '')
            if emp_email:
                request_type = df.at[row_index, 'نوع الطلب']
                request_date = df.at[row_index, 'تاريخ الطلب']
                status_msg = (
                    "تمت الموافقة على طلبك مبدئيًا.\nYour request has been initially approved."
                    if action == 'approve' else
                    "تم رفض طلبك من المدير.\nYour request has been rejected by the manager."
                )
                subject = "🔔 تحديث حالة الطلب من المدير / Request Status Update"
                body = f"""مرحبًا {emp_name}،\n\n{status_msg}\n\nنوع الطلب / Request Type: {request_type}\nتاريخ الطلب / Request Date: {request_date}\n\nيرجى متابعة حالة الطلب من خلال النظام.\nPlease follow up your request status through the system."""
                send_email(emp_email, subject, body)
    except Exception as e:
        print("⚠️ فشل إرسال إشعار البريد:", str(e))

    return redirect('/dashboard')

@app.route('/submit_manager_bulk_request', methods=['POST'])
def submit_manager_bulk_request():
    if 'id' not in session or session['role'] != 'مدير':
        return redirect('/login')

    selected_ids = request.form.getlist('employee_ids[]')
    request_type = request.form.get('request_type')
    details = request.form.get('details', '')
    start_date = request.form.get('vacation_start', '') if request_type == 'إجازة' else ''
    end_date = request.form.get('vacation_end', '') if request_type == 'إجازة' else ''
    exec_date = ''
    hours = ''

    if request_type == 'استئذان':
         exec_date = request.form.get('permission_date', '')
         hours = request.form.get('permission_hours', '')
    elif request_type == 'أجر عمل إضافي':
         exec_date = request.form.get('overtime_date', '')
         hours = request.form.get('overtime_hours', '')
    elif request_type == 'خصم':
         hours = request.form.get('deduction_amount', '')  # ← حفظ مقدار الخصم في عمود عدد الساعات


    emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
    emp_df = emp_df[emp_df['الفرع'] == session['branch']]

    df_existing = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    current_max_id = df_existing['رقم الطلب'].max() if 'رقم الطلب' in df_existing.columns else 0
    rows = []
    for emp_id in selected_ids:
        emp = emp_df[emp_df['رقم الهوية'].astype(str) == emp_id]
        if not emp.empty:
            emp_row = emp.iloc[0]
            current_max_id += 1
            rows.append({
                'رقم الطلب': current_max_id,
                'رقم الهوية': emp_row['رقم الهوية'],
                'اسم الموظف': emp_row['الاسم'],
                'الدور': 'موظف',
                'الفرع': session['branch'],
                'نوع الطلب': request_type,
                'تاريخ البداية': start_date,
                'تاريخ النهاية': end_date,
                'عدد الساعات': hours,
                'تاريخ التنفيذ': exec_date,
                'تفاصيل': details,
                'الحالة': 'مقبول',
                'تاريخ الطلب': datetime.today().strftime('%Y-%m-%d'),
                'تاريخ الموافقة الأولى': datetime.today().strftime('%Y-%m-%d'),
                'تاريخ الموافقة الثانية': ''
            })

    df = pd.concat([df_existing, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')

    return redirect('/dashboard')


@app.route('/upload_excel_requests', methods=['POST'])
def upload_excel_requests():
    if 'id' not in session or session['role'] != 'مدير':
        return redirect('/login')

    file = request.files['excel_file']
    if not file:
        return 'لم يتم اختيار ملف'

    try:
        df_excel = pd.read_excel(file)
    except Exception as e:
        return f'حدث خطأ أثناء قراءة الملف: {str(e)}'

    # ✅ التحقق من أن الأعمدة بعد "تفاصيل" فارغة
    after_details_cols = ['رقم الطلب', 'تاريخ الطلب', 'تاريخ الموافقة الأولى', 'تاريخ الموافقة الثانية']
    for col in after_details_cols:
        if col in df_excel.columns and df_excel[col].notna().any():
            return f"تم رفض الملف: لا يُسمح بملء العمود '{col}'، يُرجى تركه فارغًا."

    if 'رقم الهوية' not in df_excel.columns:
        return 'الملف لا يحتوي على عمود "رقم الهوية"'

    emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
    emp_df = emp_df[emp_df['الفرع'] == session['branch']]

    valid_ids = set(emp_df['رقم الهوية'].astype(str))
    uploaded_ids = set(df_excel['رقم الهوية'].astype(str))
    invalid_ids = uploaded_ids - valid_ids

    if invalid_ids:
        return f"تم رفض الملف: يحتوي على أرقام هوية غير مسجلة في الفرع ({session['branch']}): {', '.join(invalid_ids)}"

    df_existing = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    current_max_id = df_existing['رقم الطلب'].max() if 'رقم الطلب' in df_existing.columns else 0
    rows = []

    for _, row in df_excel.iterrows():
        emp = emp_df[emp_df['رقم الهوية'].astype(str) == str(row['رقم الهوية'])]
        if emp.empty:
            continue

        emp_name = emp.iloc[0]['الاسم']
        request_type = row['نوع الطلب']
        start = row.get('تاريخ البداية', '')
        end = row.get('تاريخ النهاية', '')
        exec_date = row.get('تاريخ التنفيذ', '')
        hours = row.get('عدد الساعات', '')
        details = row.get('تفاصيل', '')
        current_max_id += 1

        # ✅ التحقق الدقيق من المتطلبات حسب نوع الطلب
        if request_type == 'إجازة':
            if pd.isna(start) or pd.isna(end) or str(start).strip() == '' or str(end).strip() == '':
                return f"تم رفض الطلب رقم {current_max_id}: يجب إدخال تاريخ البداية والنهاية للإجازة."
        elif request_type == 'استئذان':
            if pd.isna(exec_date) or pd.isna(hours) or str(exec_date).strip() == '' or str(hours).strip() == '':
                return f"تم رفض الطلب رقم {current_max_id}: يجب إدخال تاريخ الاستئذان وعدد الساعات."
        elif request_type == 'أجر عمل إضافي':
            if pd.isna(exec_date) or pd.isna(hours) or str(exec_date).strip() == '' or str(hours).strip() == '':
                return f"تم رفض الطلب رقم {current_max_id}: يجب إدخال تاريخ وعدد ساعات العمل الإضافي."
        elif request_type == 'خصم':
            if pd.isna(hours) or str(hours).strip() == '' or str(details).strip() == '':
                return f"تم رفض الطلب رقم {current_max_id}: يجب إدخال مقدار الخصم وسبب الخصم في التفاصيل."

        rows.append({
            'رقم الطلب': current_max_id,
            'رقم الهوية': row['رقم الهوية'],
            'اسم الموظف': emp_name,
            'الدور': 'موظف',
            'الفرع': session['branch'],
            'نوع الطلب': request_type,
            'تاريخ البداية': start,
            'تاريخ النهاية': end,
            'عدد الساعات': hours,
            'تاريخ التنفيذ': exec_date,
            'تفاصيل': details,
            'الحالة': 'مقبول',
            'تاريخ الطلب': datetime.today().strftime('%Y-%m-%d'),
            'تاريخ الموافقة الأولى': datetime.today().strftime('%Y-%m-%d'),
            'تاريخ الموافقة الثانية': ''
        })

    df = pd.concat([df_existing, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    # ✅ هنا بعد الحفظ
    log_action(session['name'], session['id'], session['role'], session['branch'], 'رفع طلبات Excel', '', 'متعدد')
    return redirect('/dashboard')


@app.route('/download_template')
def download_template():
    return send_from_directory(directory='.', path='bulk_template.xlsx', as_attachment=True)


@app.route('/statistics')
def statistics():
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    try:
        df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
        df = df[df['الحالة'].isin(['مقبول', 'مقبول نهائيًا'])]
        df['تاريخ الطلب'] = pd.to_datetime(df['تاريخ الطلب'], errors='coerce')
        df['الشهر'] = df['تاريخ الطلب'].dt.strftime('%Y-%m')

        # توحيد اسم نوع الطلب
        df['نوع الطلب'] = df['نوع الطلب'].replace({'أجر عمل إضافي': 'ساعات إضافية'})

        # الإحصائيات الأساسية: عدد الطلبات من كل نوع
        grouped = df.groupby(['الشهر', 'الفرع', 'نوع الطلب']).size().unstack(fill_value=0).reset_index()
        for col in ['إجازة', 'استئذان', 'ساعات إضافية', 'خصم']:
            if col not in grouped.columns:
                grouped[col] = 0

        # حساب إجمالي الخصومات بالريال
        df_deductions = df[df['نوع الطلب'] == 'خصم'].copy()
        df_deductions['عدد الساعات'] = pd.to_numeric(df_deductions['عدد الساعات'], errors='coerce')

        deductions_sum = df_deductions.groupby(['الشهر', 'الفرع'])['عدد الساعات'].sum().reset_index()
        deductions_avg = df_deductions.groupby(['الشهر', 'الفرع'])['عدد الساعات'].mean().reset_index()

        deductions_sum.rename(columns={'عدد الساعات': 'إجمالي الخصومات (ريال)'}, inplace=True)
        deductions_avg.rename(columns={'عدد الساعات': 'متوسط الخصم (ريال)'}, inplace=True)

        # دمجها مع الإحصائيات العامة
        grouped = pd.merge(grouped, deductions_sum, on=['الشهر', 'الفرع'], how='left')
        grouped = pd.merge(grouped, deductions_avg, on=['الشهر', 'الفرع'], how='left')

        grouped['إجمالي الخصومات (ريال)'] = grouped['إجمالي الخصومات (ريال)'].fillna(0)
        grouped['متوسط الخصم (ريال)'] = grouped['متوسط الخصم (ريال)'].fillna(0).round(2)

        stats = grouped.to_dict(orient='records')
        return render_template('statistics.html', stats=stats)

    except Exception as e:
        return f"خطأ أثناء تحميل الإحصائيات: {str(e)}",


@app.route('/submit_request', methods=['POST'])
def submit_request():
    if 'id' not in session:
        return redirect('/login')

    request_type = request.form['request_type']
    details = request.form.get('details', '')
    start_date = request.form.get('vacation_start', '') if request_type == 'إجازة' else ''
    end_date = request.form.get('vacation_end', '') if request_type == 'إجازة' else ''
    exec_date = ''
    hours = ''

    if request_type == 'استئذان':
        exec_date = request.form.get('permission_date', '')
        hours = request.form.get('permission_hours', '')
    elif request_type == 'أجر عمل إضافي':
        exec_date = request.form.get('overtime_date', '')
        hours = request.form.get('overtime_hours', '')
    elif request_type == 'خصم':
        hours = request.form.get('deduction_amount', '')
        reason = request.form.get('deduction_reason', '')
        details = f"{details} (سبب الخصم: {reason})"

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    new_id = 1 if df.empty else df['رقم الطلب'].max() + 1

    new_row = {
        'رقم الطلب': new_id,
        'رقم الهوية': session['id'],
        'اسم الموظف': session['name'],
        'الدور': session['role'],
        'الفرع': session['branch'],
        'نوع الطلب': request_type,
        'تاريخ البداية': start_date,
        'تاريخ النهاية': end_date,
        'عدد الساعات': hours,
        'تاريخ التنفيذ': exec_date,
        'تفاصيل': details,
        'الحالة': 'معلق',
        'تاريخ الطلب': datetime.today().strftime('%Y-%m-%d'),
        'تاريخ الموافقة الأولى': '',
        'تاريخ الموافقة الثانية': ''
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    log_action(session['name'], session['id'], session['role'], session['branch'], 'تقديم طلب جديد', request.form.get('نوع الطلب', ''), new_id)
        # ✅ إرسال إشعار بالبريد الإلكتروني بعد إنشاء الطلب
    try:
        print("🚀 بدأ تنفيذ الإشعار...")
        emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        employee = emp_df[emp_df['رقم الهوية'].astype(str) == str(session['id'])]
        print("📄 تم تحميل بيانات الموظف")

        if not employee.empty:
            emp_email = employee.iloc[0].get('البريد', '')
            emp_name = employee.iloc[0].get('الاسم', session['name'])
            print(f"📧 البريد الإلكتروني المستهدف: {emp_email}")
            if emp_email:
                subject = "📥  New request تم تقديم طلب جديد"
                body = f"""مرحبًا {emp_name}،\n\nتم تقديم طلب جديد من نوع- Type: {request_type}\nبتاريخ البداية-Start date: {start_date} وحتى till {end_date if end_date else '—'}\nالحالة الحالية للطلب-status: معلق\n\nسنقوم بإعلامك في حال تغيّر حالة الطلب will inform you about status.\n"""
                print("✉️ جاري إرسال الإيميل...")
                send_email(emp_email, subject, body)
                print("✅ تم تنفيذ send_email()")
            else:
                print("⚠️ لا يوجد بريد إلكتروني")
        else:
            print("❌ لم يتم العثور على الموظف في ملف employees.csv")
    except Exception as e:
        print("❌ تعذر إرسال إشعار الإيميل:", str(e))
        import traceback
        traceback.print_exc()

    return redirect('/dashboard')

@app.route('/hr_action', methods=['POST'])
def hr_action():
    if 'id' not in session or session['role'] != 'موارد بشرية':
        return redirect('/login')

    index = int(request.form['index'])
    action = request.form['action']

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    pending = df[(df['الحالة'] == 'مقبول') & (df['تاريخ الموافقة الأولى'].notna())].reset_index()

    if index >= len(pending):
        return "طلب غير صالح"

    row_index = pending.loc[index, 'index']
    today = datetime.today().strftime('%Y-%m-%d')

    if action == 'approve':
        df.at[row_index, 'الحالة'] = 'مقبول نهائيًا'
        df.at[row_index, 'تاريخ الموافقة الثانية'] = today

        # ✅ تحديث تاريخ آخر إجازة في ملف الموظفين
        if df.at[row_index, 'نوع الطلب'] == 'إجازة':
            emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
            emp_name = df.at[row_index, 'اسم الموظف']
            end_date = df.at[row_index, 'تاريخ النهاية']

            if emp_name in emp_df['الاسم'].values:
                emp_df.loc[emp_df['الاسم'] == emp_name, 'تاريخ آخر إجازة'] = end_date
                emp_df.to_csv(EMPLOYEE_FILE, index=False, encoding='utf-8-sig')

    elif action == 'reject':
        df.at[row_index, 'الحالة'] = 'مرفوض من الموارد البشرية'
        df.at[row_index, 'تاريخ الموافقة الثانية'] = today

    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    log_action(session['name'], session['id'], session['role'], session['branch'], f"{action} من الموارد البشرية", df.at[row_index, 'نوع الطلب'], row_index)

    # ✉️ إشعار البريد الإلكتروني
    try:
        emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        emp_name = df.at[row_index, 'اسم الموظف']
        emp_email = emp_df.loc[emp_df['الاسم'] == emp_name, 'البريد'].values[0]

        if emp_email:
            request_type = df.at[row_index, 'نوع الطلب']
            status = df.at[row_index, 'الحالة']
            start_date = df.at[row_index, 'تاريخ البداية']

            if action == 'approve':
                subject = "✅ تمت الموافقة النهائية على طلبك"
                body = f"""مرحبًا {emp_name}،\n\nتمّت الموافقة النهائية على طلبك من نوع: {request_type}
تاريخ بداية الطلب: {start_date}
الحالة: {status}

✅ Your request has been fully approved:
Type: {request_type}
Start Date: {start_date}
Status: {status}
"""
            else:
                subject = "❌ تم رفض طلبك"
                body = f"""مرحبًا {emp_name}،\n\nتم رفض طلبك من نوع: {request_type}

❌ Your request has been rejected:
Type: {request_type}
"""

            send_email(emp_email, subject, body)
    except Exception as e:
        print("❌ فشل إرسال إشعار الإيميل:", str(e))

    return redirect('/dashboard')

@app.route('/admin_action', methods=['POST'])
def admin_action():
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    request_id = int(request.form['request_id'])  # ← نستخدم رقم الطلب
    action = request.form['action']

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')

    # البحث عن الصف المطابق لرقم الطلب
    row_index_list = df.index[df['رقم الطلب'] == request_id].tolist()
    if not row_index_list:
        return "طلب غير موجود"
    row_index = row_index_list[0]

    today = datetime.today().strftime('%Y-%m-%d')

    if action == 'approve':
        df.at[row_index, 'الحالة'] = 'مقبول نهائيًا'
        df.at[row_index, 'تاريخ الموافقة الثانية'] = today

        # ✅ تحديث تاريخ آخر إجازة
        if df.at[row_index, 'نوع الطلب'] == 'إجازة':
            emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
            emp_name = df.at[row_index, 'اسم الموظف']
            end_date = df.at[row_index, 'تاريخ النهاية']
            if emp_name in emp_df['الاسم'].values:
                emp_df.loc[emp_df['الاسم'] == emp_name, 'تاريخ آخر إجازة'] = end_date
                emp_df.to_csv(EMPLOYEE_FILE, index=False, encoding='utf-8-sig')

        log_action(
            session['name'], session['id'], session['role'], session['branch'],
            'موافقة المشرف العام', df.at[row_index, 'نوع الطلب'], request_id
        )

    elif action == 'reject':
        df.at[row_index, 'الحالة'] = 'مرفوض من المشرف العام'
        df.at[row_index, 'تاريخ الموافقة الثانية'] = today

        log_action(
            session['name'], session['id'], session['role'], session['branch'],
            'رفض المشرف العام', df.at[row_index, 'نوع الطلب'], request_id
        )

    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')

    # ✉️ إشعار البريد الإلكتروني
    try:
        emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        emp_name = df.at[row_index, 'اسم الموظف']
        emp_email = emp_df.loc[emp_df['الاسم'] == emp_name, 'البريد'].values[0]

        if emp_email:
            request_type = df.at[row_index, 'نوع الطلب']
            status = df.at[row_index, 'الحالة']
            start_date = df.at[row_index, 'تاريخ البداية']

            if action == 'approve':
                subject = "✅ تمت الموافقة النهائية على طلبك"
                body = f"""مرحبًا {emp_name}،\n\nتمّت الموافقة النهائية على طلبك من نوع: {request_type}
تاريخ بداية الطلب: {start_date}
الحالة: {status}

✅ Your request has been fully approved:
Type: {request_type}
Start Date: {start_date}
Status: {status}
"""
            else:
                subject = "❌ تم رفض طلبك"
                body = f"""مرحبًا {emp_name}،\n\nتم رفض طلبك من نوع: {request_type}

❌ Your request has been rejected:
Type: {request_type}
"""

            send_email(emp_email, subject, body)
    except Exception as e:
        print("❌ فشل إرسال إشعار الإيميل:", str(e))

    return redirect('/dashboard')
@app.route('/edit_request/<int:request_id>', methods=['GET', 'POST'])
def edit_request(request_id):
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    row_index_list = df.index[df['رقم الطلب'] == request_id].tolist()

    if not row_index_list:
        return "طلب غير موجود"

    i = row_index_list[0]

    if request.method == 'POST':
        df.at[i, 'نوع الطلب'] = request.form.get('نوع الطلب', df.at[i, 'نوع الطلب'])
        df.at[i, 'تفاصيل'] = request.form.get('تفاصيل', df.at[i, 'تفاصيل'])
        df.at[i, 'تاريخ البداية'] = request.form.get('تاريخ البداية', df.at[i, 'تاريخ البداية'])
        df.at[i, 'تاريخ النهاية'] = request.form.get('تاريخ النهاية', df.at[i, 'تاريخ النهاية'])
        df.at[i, 'عدد الساعات'] = request.form.get('عدد الساعات', df.at[i, 'عدد الساعات'])
        df.at[i, 'تاريخ التنفيذ'] = request.form.get('تاريخ التنفيذ', df.at[i, 'تاريخ التنفيذ'])

        df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
        # ✅ بعد الحفظ
        log_action(session['name'], session['id'], session['role'], session['branch'], 'تعديل طلب', df.at[i, 'نوع الطلب'], id)
        return redirect('/dashboard')

    current_request = df.loc[i].to_dict()
    return render_template('edit_request.html', req=current_request)


@app.route('/delete_request/<int:request_id>', methods=['POST'])
def delete_request(request_id):
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    df = df[df['رقم الطلب'] != request_id]
    df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    # ✅ بعد الحذف
    log_action(session['name'], session['id'], session['role'], session['branch'], 'حذف طلب', '', id)
    return redirect('/dashboard')
@app.route('/manager_vacations')
def manager_vacations():
    if 'role' not in session or session['role'] != 'مدير':
        return redirect('/login')

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    branch = session['branch']

    # ✅ تصفية فقط الطلبات التي تم اعتمادها نهائيًا
    df = df[
        (df['نوع الطلب'] == 'إجازة') &
        (df['الحالة'] == 'مقبول نهائيًا') &
        (df['الفرع'] == branch)
    ]

    # ✅ الطلبات المعلقة على المباشرة (لم يتم تأكيدها بعد)
    vacation_pending = df[
        (df['تاريخ مباشرة العمل'].isna() | (df['تاريخ مباشرة العمل'] == '')) &
        ((df['حالة المباشرة'].isna()) | (df['حالة المباشرة'] != 'لم يعد'))
    ]

    # ✅ الطلبات التي تم تأكيد مباشرتها أو تم الضغط على "لم يعد"
    vacation_confirmed = df[
        ((df['تاريخ مباشرة العمل'].notna()) & (df['تاريخ مباشرة العمل'] != '')) |
        (df['حالة المباشرة'] == 'لم يعد')
    ]

    return render_template('manager_vacations.html',
        name=session['name'],
        vacation_pending=vacation_pending.to_dict(orient='records'),
        vacation_confirmed=vacation_confirmed.to_dict(orient='records')
    )

@app.route('/hr_vacation')
def hr_vacation():
    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')

    # الطلبات المعلقة: فيها تاريخ مباشرة، ولم يتم إشعار الموارد
    pending = df[
        (df['نوع الطلب'] == 'إجازة') &
        (df['تاريخ مباشرة العمل'].notna()) &
        ((df['تم إشعار الموارد بالمباشرة'].isna()) | (df['تم إشعار الموارد بالمباشرة'] == ""))
    ]

    # الطلبات المنتهية: تم إشعار الموارد بها
    completed = df[
        (df['نوع الطلب'] == 'إجازة') &
        (df['تم إشعار الموارد بالمباشرة'].notna()) &
        (df['تم إشعار الموارد بالمباشرة'] != "")
    ]

    return render_template('hr_vacation.html', pending=pending.to_dict(orient='records'), completed=completed.to_dict(orient='records'))
@app.route('/hr_notify_return', methods=['POST'])
def hr_notify_return():
    if 'id' not in session or session['role'] != 'موارد بشرية':
        return redirect('/login')

    req_id = int(request.form['request_id'])

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    index = df[df['رقم الطلب'] == req_id].index

    if not index.empty:
        i = index[0]
        today = datetime.today().strftime('%Y-%m-%d')
        df.at[i, 'تم إشعار الموارد بالمباشرة'] = today

        df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')

        # 🟢 تسجيل في السجل
        log_action(session['name'], session['id'], session['role'], session['branch'],
                   'إشعار الموارد بالمباشرة', df.at[i, 'نوع الطلب'], req_id)

    return redirect('/hr_vacation')

@app.route('/admin_vacations')
def admin_vacations():
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')

    # تأكد أن كل الأعمدة موجودة
    for col in ['نوع الطلب', 'الحالة', 'تاريخ مباشرة العمل', 'حالة المباشرة', 'تم إشعار الموارد بالمباشرة']:
        if col not in df.columns:
            df[col] = ''

    df.fillna('', inplace=True)
    df = df[df['نوع الطلب'] == 'إجازة']

    vacation_requests = df[
        # ✅ لم تتم مباشرة العمل ولا الضغط على \"لم يعد\"
        ((df['الحالة'] == 'مقبول نهائيًا') &
         (df['تاريخ مباشرة العمل'] == '') &
         ((df['حالة المباشرة'] == '') | (df['حالة المباشرة'] == 'nan'))) |

        # ✅ تمت مباشرة العمل لكن لم يتم إشعار الموارد
        ((df['الحالة'] == 'مقبول نهائيًا') &
         (df['تاريخ مباشرة العمل'] != '') &
         ((df['تم إشعار الموارد بالمباشرة'] == '') | (df['تم إشعار الموارد بالمباشرة'] == 'nan'))) |

        # ✅ تم إشعار الموارد (توثيق)
        (df['تم إشعار الموارد بالمباشرة'] != '')
    ]

    vacation_requests = vacation_requests.sort_values(by='تاريخ الطلب', ascending=False)

    return render_template(
        'admin_vacation.html',
        requests=vacation_requests.to_dict(orient='records')
    )

@app.route('/admin_confirm_return', methods=['POST'])
@log_event(event="تأكيد عودة الموظف", request_type="عملية", request_id_key="id_number")
def admin_confirm_return():
    request_id = int(request.form['request_id'])
    action = request.form['action']
    return_date = request.form.get('return_date', '')

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')

    # تحديد الصف المطلوب
    row_index = df[df['رقم الطلب'] == request_id].index
    if not row_index.empty:
        i = row_index[0]
        if action == 'returned':
            df.at[i, 'تاريخ مباشرة العمل'] = return_date
            df.at[i, 'حالة المباشرة'] = 'مباشر'
        elif action == 'not_returned':
            df.at[i, 'تاريخ مباشرة العمل'] = return_date
            df.at[i, 'حالة المباشرة'] = 'لم يعد'
        df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
    return redirect('/admin_vacations')

@app.route('/admin_notify_hr', methods=['POST'])
def admin_notify_hr():
    request_id = int(request.form['request_id'])

    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    if 'رقم الطلب' not in df.columns:
        flash('الملف لا يحتوي على رقم الطلبات')
        return redirect('/admin_vacations')

    # البحث عن الصف المطلوب بناءً على رقم الطلب
    row_index = df[df['رقم الطلب'] == request_id].index
    if not row_index.empty:
        index = row_index[0]
        # كتابة التاريخ بدل "تم"
        df.at[index, 'تم إشعار الموارد بالمباشرة'] = datetime.now().strftime('%Y-%m-%d')
        df.to_csv(REQUEST_FILE, index=False, encoding='utf-8-sig')
        flash('تم إشعار الموارد البشرية بنجاح')
        # ✅ بعد التحديث مباشرة
        log_action(session['name'], session['id'], session['role'], session['branch'], 'إشعار الموارد من المشرف العام', '', request.form.get('id', ''))
    else:
        flash('لم يتم العثور على الطلب المحدد')

    return redirect('/admin_vacations')
@app.route('/leave_priority')
def leave_priority():
    df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')

    if 'تاريخ آخر إجازة' not in df.columns:
        df['تاريخ آخر إجازة'] = ''
    if 'مدة الاستحقاق (بالأيام)' not in df.columns:
        df['مدة الاستحقاق (بالأيام)'] = 730

    today = datetime.today()
    df['أيام منذ آخر إجازة'] = df['تاريخ آخر إجازة'].apply(
        lambda d: (today - pd.to_datetime(d)).days if d else 9999
    )
    df['نسبة الاستحقاق'] = df['أيام منذ آخر إجازة'] / df['مدة الاستحقاق (بالأيام)']

    # ✅ تصفية الفرع في حالة المدير فقط
    role = session.get('role')
    user_branch = session.get('branch')

    if role == 'مدير':
        df = df[df['الفرع'] == user_branch]

    df = df.sort_values(by='نسبة الاستحقاق', ascending=False)
    top_name = df.iloc[0]['الاسم'] if not df.empty else 'لا يوجد موظف'

    # ✅ تعديل أسماء الأعمدة لتطابق HTML
    df.rename(columns={
        'أيام منذ آخر إجازة': 'عدد الأيام منذ الإجازة الأخيرة',
        'مدة الاستحقاق (بالأيام)': 'مدة الاستحقاق'
    }, inplace=True)

    return render_template(
        'leave_priority.html',
        employees=df.to_dict(orient='records'),
        top_employee_name=top_name
    )

@app.route('/update_entitlement', methods=['POST'])
def update_entitlement():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام', 'مدير']:
        return redirect('/login')

    id_number = request.form['id_number']
    new_entitlement = request.form['new_entitlement']

    df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')

    if id_number in df['رقم الهوية'].astype(str).values:
        df.loc[df['رقم الهوية'].astype(str) == id_number, 'مدة الاستحقاق (بالأيام)'] = int(new_entitlement)
        df.to_csv(EMPLOYEE_FILE, index=False, encoding='utf-8-sig')
        # ✅ بعد التحديث
        log_action(session['name'], session['id'], session['role'], session['branch'], 'تحديث الاستحقاق', '', request.form.get('رقم الهوية', ''))
    return redirect('/leave_priority')
@app.route('/confirm_two_year_leave', methods=['POST'])
def confirm_two_year_leave():
    id_number = request.form['id_number']
    name = request.form['name']
    branch = request.form['branch']
    eligibility_days = request.form['eligibility_days']
    decision = request.form['decision']
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    file_path = 'two_year_leave_decisions.csv'

    if not os.path.exists(file_path):
        df_init = pd.DataFrame(columns=[
            'رقم الهوية / ID',
            'الاسم / Name',
            'الفرع / Branch',
            'عدد أيام الاستحقاق / Eligibility Days',
            'القرار / Decision',
            'تاريخ الرد / Decision Date',
            'أُعيد الإرسال؟'
        ])
        df_init.to_csv(file_path, index=False, encoding='utf-8-sig')

    new_row = pd.DataFrame([{
        'رقم الهوية / ID': id_number,
        'الاسم / Name': name,
        'الفرع / Branch': branch,
        'عدد أيام الاستحقاق / Eligibility Days': eligibility_days,
        'القرار / Decision': decision,
        'تاريخ الرد / Decision Date': date,
        'أُعيد الإرسال؟': ''
    }])

    df_existing = pd.read_csv(file_path, encoding='utf-8-sig')
    df_combined = pd.concat([df_existing, new_row], ignore_index=True)
    df_combined.to_csv(file_path, index=False, encoding='utf-8-sig')

    return redirect('/dashboard')

@app.route('/resend_two_year_decision', methods=['POST'])
def resend_two_year_decision():
    id_number = request.form['id_number']
    branch = request.form['branch']
    decision_file = 'two_year_leave_decisions.csv'

    if not os.path.exists(decision_file):
        return 'الملف غير موجود'

    df = pd.read_csv(decision_file, encoding='utf-8-sig')
    condition = (
        (df['رقم الهوية / ID'].astype(str) == id_number) &
        (df['الفرع / Branch'] == branch) &
        (df['القرار / Decision'] == 'لا أوافق / I Disagree')
    )

    if condition.any():
        latest_index = df[condition].index[-1]
        df.at[latest_index, 'أُعيد الإرسال؟'] = 'نعم'
        df.to_csv(decision_file, index=False, encoding='utf-8-sig')
        return redirect('/review_two_year_leave')
    else:
        return 'لم يتم العثور على القرار المناسب'

@app.route('/two_year_decisions')
def two_year_decisions():
    if 'id' not in session or session['role'] not in ['مدير', 'مشرف عام', 'موارد بشرية']:
        return redirect('/login')

    file_path = 'two_year_leave_decisions.csv'
    emp_df = pd.read_csv('employees.csv', encoding='utf-8-sig')

    if not os.path.exists(file_path):
        decisions = []
    else:
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        if session['role'] == 'مدير':
            df = df[df['الفرع / Branch'] == session['branch']]
        decisions = df.to_dict(orient='records')

    return render_template('two_year_decisions_manager.html', decisions=decisions)

@app.route('/resend_two_year_request', methods=['POST'])
def resend_two_year_request():
    if 'id' not in session or session['role'] not in ['مدير', 'مشرف عام', 'موارد بشرية']:
        return redirect('/login')

    id_number = request.form['id_number']
    file_path = 'two_year_leave_decisions.csv'

    if os.path.exists(file_path):
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        df = df[df['رقم الهوية / ID'].astype(str) != str(id_number)]
        df.to_csv(file_path, index=False, encoding='utf-8-sig')
    return redirect('/two_year_decisions')

@app.route('/employee_view')
@log_event(event="عرض لوحة الموظف", request_type="عرض")
def employee_view():
    if 'id' not in session:
        return redirect('/login')

    id_number = session['id']
    role = session['role']

    if role not in ['مدير', 'موارد بشرية', 'مشرف عام']:
        return "غير مصرح لك بالدخول هنا", 403

    # جلب الطلبات الخاصة بالموظف
    df = pd.read_csv(REQUEST_FILE, encoding='utf-8-sig')
    my_requests = df[df['رقم الهوية'].astype(str) == id_number]
    my_requests = my_requests.sort_values(by='تاريخ الطلب', ascending=False)

    # تحميل بيانات الموظف
    emp_df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
    emp_info = emp_df[emp_df['رقم الهوية'].astype(str) == id_number].iloc[0]

    # ✅ حساب عدد الرسائل غير المقروءة (مطلوب للزر العلوي)
    unread_count = get_unread_count_for_user(session.get("email", ""))  # ← يجب أن تكون الدالة موجودة

    return render_template(
        'employee_dashboard.html',
        name=session['name'],
        my_requests=my_requests.to_dict(orient='records'),
        eligibility_days=int(emp_info.get('مدة الاستحقاق (بالأيام)', 0)),
        already_decided=False,
        unread_count=unread_count  # ← حل المشكلة هنا
    )

@app.route('/create_messages_file')
def create_messages_file():
    filename = "messages.xlsx"

    if os.path.exists(filename):
        os.remove(filename)

    wb = Workbook()
    ws = wb.active
    ws.title = "Messages"

    headers = [
        "ID",
        "Type",
        "SenderID",  
        "SenderName",
        "SenderBranch",
        "SenderRole",
        "ReceiverID",    # ✅ بديل عن ReceiverEmail
        "ReceiverName",
        "ReceiverBranch",
        "ReceiverRole",
        "Subject",
        "Content",
        "RequiresApproval",
        "ApprovalType",
        "DateSent",
        "DateRead",
        "DateApproved",
        "Status",
        "DeletedBy",
        "ForwardedFrom",
        "RepliedTo"
    ]

    ws.append(headers)
    wb.save(filename)

    return f"✅ messages.xlsx created successfully with updated columns."
@app.route('/messages')
@log_event(event="عرض صفحة الرسائل", request_type="رسائل")
def view_messages():
    if 'id' not in session or 'role' not in session:
        return redirect(url_for('login'))

    user_id = str(session['id'])
    user_role = session['role']
    user_branch = session.get('branch', '')

    # تحديد رابط العودة حسب الدور
    return_url = '/dashboard'

    # قراءة الرسائل
    try:
        df = pd.read_excel('messages.xlsx')
    except FileNotFoundError:
        return '📭 ملف الرسائل غير موجود'

    df.fillna('', inplace=True)

    # ✅ تأكد من وجود الأعمدة اللازمة
    if 'PermanentlyDeletedBy' not in df.columns:
        df['PermanentlyDeletedBy'] = ''
    if 'DeletedBy' not in df.columns:
        df['DeletedBy'] = ''

    # ✅ استبعاد الرسائل المحذوفة نهائيًا لهذا المستخدم فقط
    inbox_df = df[
        (df['ReceiverID'].astype(str) == user_id) &
        (~df['DeletedBy'].astype(str).str.contains(user_id, na=False)) &
        (~df['PermanentlyDeletedBy'].astype(str).str.contains(user_id, na=False))
    ]

    sent_df = df[
        (df['SenderID'].astype(str) == user_id) &
        (~df['DeletedBy'].astype(str).str.contains(user_id, na=False)) &
        (~df['PermanentlyDeletedBy'].astype(str).str.contains(user_id, na=False))
    ]

    trash_df = df[
        (df['DeletedBy'].astype(str).str.contains(user_id, na=False)) &
        (~df['PermanentlyDeletedBy'].astype(str).str.contains(user_id, na=False))
    ]

    inbox_messages = inbox_df.sort_values(by='DateSent', ascending=False).to_dict(orient='records')
    sent_messages = sent_df.sort_values(by='DateSent', ascending=False).to_dict(orient='records')
    trash_messages = trash_df.sort_values(by='DateSent', ascending=False).to_dict(orient='records')

    # ✅ سجل كامل للمشرف العام مع عمود حالة الحذف
    all_messages = []
    if user_role == 'مشرف عام':
        df['DeleteStatus'] = df.apply(
            lambda row: 'محذوفة نهائيًا' if row['PermanentlyDeletedBy'] else (
                        'محذوفة' if row['DeletedBy'] else 'مرئية'),
            axis=1
        )
        all_messages = df.sort_values(by='DateSent', ascending=False).to_dict(orient='records')

    # قراءة بيانات الموظفين من employees.csv
    try:
        employees_df = pd.read_csv('employees.csv')
    except FileNotFoundError:
        employees_df = pd.DataFrame(columns=['رقم الهوية', 'الاسم', 'الفرع', 'الدور'])

    employees = employees_df[['رقم الهوية', 'الاسم', 'الفرع', 'الدور']].dropna().to_dict(orient='records')

    # استخراج الفروع الفريدة لعرضها في واجهة الفلترة
    branches = sorted(employees_df['الفرع'].dropna().unique())

    return render_template(
        'messages.html',
        inbox_messages=inbox_messages,
        sent_messages=sent_messages,
        trash_messages=trash_messages,
        all_messages=all_messages,
        return_url=return_url,
        employees_json=employees,
        branches=branches
    )


@app.route('/send_message', methods=['POST', 'GET'])
@log_event(event="إرسال رسالة", request_type="رسائل")
def send_message():
    if 'id' not in session or 'role' not in session or 'name' not in session or 'branch' not in session:
        return redirect(url_for('login'))

    sender_id = session.get('id')
    sender_name = session.get('name')
    sender_branch = session.get('branch')
    sender_role = session.get('role')

    receiver_ids = request.form.getlist('receiver_ids')
    message_type = request.form.get('type')
    approval_type = request.form.get('approval_type') if message_type in ['ContractRenewal', 'TransferRequest', 'ViolationExplanation'] else ''
    subject = request.form.get('subject')
    content = request.form.get('content')
    reply_to = request.form.get('reply_to')
    forward_from = request.form.get('forward_from')

    try:
        df = pd.read_excel('messages.xlsx')
    except FileNotFoundError:
        df = pd.DataFrame()

    try:
        employees_df = pd.read_csv('employees.csv')
    except FileNotFoundError:
        employees_df = pd.DataFrame(columns=['رقم الهوية', 'الاسم', 'الفرع', 'الدور', 'البريد'])

    next_id = int(df['ID'].max() + 1) if not df.empty and 'ID' in df.columns else 1

    for rid in receiver_ids:
        emp = employees_df[employees_df['رقم الهوية'].astype(str) == str(rid)]
        if not emp.empty:
            emp_data = emp.iloc[0]

            new_row = {
                "ID": next_id,
                "Type": message_type,
                "SenderEmail": '',
                "SenderID": sender_id,
                "SenderName": sender_name,
                "SenderBranch": sender_branch,
                "SenderRole": sender_role,
                "ReceiverID": rid,
                "ReceiverEmail": '',
                "ReceiverName": emp_data['الاسم'],
                "ReceiverBranch": emp_data['الفرع'],
                "ReceiverRole": emp_data['الدور'],
                "Subject": subject,
                "Content": content,
                "RequiresApproval": 'Yes' if message_type in ['ContractRenewal', 'TransferRequest', 'ViolationExplanation'] else 'No',
                "ApprovalType": approval_type,
                "DateSent": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "DateRead": '',
                "DateApproved": '',
                "Status": 'Unread',
                "DeletedBy": '',
                "PermanentlyDeletedBy": '',
                "ForwardedFrom": forward_from or '',
                "RepliedTo": reply_to or ''
            }

            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            next_id += 1

            # ✅ إرسال الإشعار عبر البريد الإلكتروني
            try:
                emp_email = emp_data.get('البريد', '')
                receiver_name = emp_data.get('الاسم', '')

                if emp_email:
                    subject_email = f"📨 رسالة جديدة / New Message from {sender_name}"
                    body_email = f"""مرحبًا {receiver_name},

لقد استلمت رسالة جديدة من {sender_name} (الدور: {sender_role}).

📝 عنوان الرسالة: {subject}

يرجى تسجيل الدخول إلى النظام لعرض الرسالة والرد عليها إن لزم.

---

Hello {receiver_name},

You have received a new message from {sender_name} (Role: {sender_role}).

📝 Subject: {subject}

Please log in to the system to view and reply to the message if needed.

مع تحيات فريق النظام / 
Best regards,  
System Team
"""
                    send_email(emp_email, subject_email, body_email)
            except Exception as e:
                print(f"❌ فشل إرسال الإشعار للمستلم {rid}: {str(e)}")

    df.to_excel('messages.xlsx', index=False)
    return redirect(url_for('view_messages'))

@app.route('/reply/<int:message_id>')
@log_event(event="الرد على رسالة", request_type="رسائل")
def reply(message_id):
    if 'id' not in session:
        return redirect(url_for('login'))

    try:
        df = pd.read_excel('messages.xlsx')
        df.fillna('', inplace=True)
    except FileNotFoundError:
        return '❌ ملف الرسائل غير موجود'

    # إيجاد الرسالة المطلوبة
    message = df[df['ID'] == message_id]
    if message.empty:
        return '❌ لم يتم العثور على الرسالة المطلوبة'
    
    msg = message.iloc[0]

    # تحميل جميع الرسائل الخاصة بالمستخدم الحالي
    user_id = str(session['id'])
    inbox_df = df[(df['ReceiverID'].astype(str) == user_id) & (df['DeletedBy'].astype(str) != user_id)]
    sent_df = df[(df['SenderID'].astype(str) == user_id) & (df['DeletedBy'].astype(str) != user_id)]
    trash_df = df[df['DeletedBy'].astype(str) == user_id]

    # قراءة ملف الموظفين لتوليد employees_json
    try:
        employees_df = pd.read_csv('employees.csv')
        employees_df.fillna('', inplace=True)
        employees_json = employees_df.to_dict(orient='records')
    except FileNotFoundError:
        employees_json = []

    # استخراج الفروع من الرسائل لضمان ظهورها في قائمة الفروع
    all_branches = sorted(df['ReceiverBranch'].dropna().unique())

    return render_template(
        'messages.html',
        compose_mode='reply',
        reply_to=msg['ID'],
        receiver_id=msg['SenderID'],
        receiver_name=msg['SenderName'],
        receiver_branch=msg['SenderBranch'],
        receiver_role=msg['SenderRole'],
        subject=f"رد على: {msg['Subject']}",
        content=f"\n\n--------------------\n{msg['SenderName']}:\n{msg['Content']}",
        inbox_messages=inbox_df.to_dict(orient='records'),
        sent_messages=sent_df.to_dict(orient='records'),
        trash_messages=trash_df.to_dict(orient='records'),
        return_url=url_for('view_messages'),
        branches=all_branches,
        employees_json=json.dumps(employees_json, ensure_ascii=False)
    )


@app.route('/forward/<int:message_id>')
@log_event(event="إعادة توجيه رسالة", request_type="رسائل")
def forward(message_id):
    if 'id' not in session:
        return redirect(url_for('login'))

    try:
        df = pd.read_excel('messages.xlsx')
        df.fillna('', inplace=True)
    except FileNotFoundError:
        return '📭 ملف الرسائل غير موجود'

    # البحث عن الرسالة
    message = df[df['ID'] == message_id]
    if message.empty:
        return '❌ لم يتم العثور على الرسالة'

    msg = message.iloc[0]

    # جلب الرسائل الخاصة بالمستخدم الحالي
    user_id = str(session['id'])
    inbox_df = df[(df['ReceiverID'].astype(str) == user_id) & (df['DeletedBy'].astype(str) != user_id)]
    sent_df = df[(df['SenderID'].astype(str) == user_id) & (df['DeletedBy'].astype(str) != user_id)]
    trash_df = df[df['DeletedBy'].astype(str) == user_id]

    # تحميل الموظفين
    try:
        employees_df = pd.read_csv('employees.csv')
        employees_df.fillna('', inplace=True)
        employees_json = employees_df.to_dict(orient='records')
    except FileNotFoundError:
        employees_json = []

    return render_template(
        'messages.html',
        compose_mode='forward',
        forward_from=msg['ID'],
        subject="إعادة توجيه: " + msg['Subject'],
        content=f"\n\n----- الرسالة الأصلية من {msg['SenderName']} -----\n{msg['Content']}",
        inbox_messages=inbox_df.to_dict(orient='records'),
        sent_messages=sent_df.to_dict(orient='records'),
        trash_messages=trash_df.to_dict(orient='records'),
        return_url=url_for('view_messages'),
        branches=sorted(df['ReceiverBranch'].dropna().unique()),
        employees_json=json.dumps(employees_json, ensure_ascii=False)
    )

# 📖 عرض الرسالة (وتحديث الحالة لمقروءة)
@app.route('/view_message/<int:message_id>')
@log_event(event="عرض رسالة", request_type="رسائل")
def view_message(message_id):
    if 'id' not in session or 'role' not in session:
        return redirect(url_for('login'))

    try:
        df = pd.read_excel('messages.xlsx')
        df.fillna('', inplace=True)
    except FileNotFoundError:
        return "📭 ملف الرسائل غير موجود", 404

    message = df[df['ID'] == message_id]
    if message.empty:
        return "🚫 لم يتم العثور على الرسالة", 404

    message_data = message.iloc[0].to_dict()

    user_id = str(session.get('id'))

    # ✅ السماح للعرض حتى لو كانت الرسالة محذوفة من قبل المستخدم
    # لكن لا نغير حالتها إلا إذا لم تكن محذوفة فعلاً
    if str(message_data['ReceiverID']) == user_id and message_data['Status'] == 'Unread':
        # لا نغير الحالة إن كانت محذوفة فعلاً من قبل المستخدم
        if str(message_data['DeletedBy']) != user_id:
            df.loc[df['ID'] == message_id, 'Status'] = 'Read'
            df.loc[df['ID'] == message_id, 'DateRead'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df.to_excel('messages.xlsx', index=False)

    return render_template('view_message.html', message=message_data)

# 🗑️ حذف الرسالة (نقلها إلى صندوق المحذوفات)
@app.route('/delete_message/<int:message_id>')
@log_event(event="حذف رسالة مؤقتًا", request_type="رسائل")
def delete_message(message_id):
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = str(session['id'])

    try:
        df = pd.read_excel('messages.xlsx')
    except FileNotFoundError:
        return '📭 ملف الرسائل غير موجود'

    df.fillna('', inplace=True)

    # تأكد من وجود عمود DeletedBy
    if 'DeletedBy' not in df.columns:
        df['DeletedBy'] = ''

    # تحديث عمود "DeletedBy" بإضافة المستخدم إذا لم يكن موجودًا
    idx = df[df['ID'] == message_id].index
    if not idx.empty:
        i = idx[0]
        current = str(df.at[i, 'DeletedBy'])
        deleted_by = set(filter(None, current.split(',')))
        deleted_by.add(user_id)
        df.at[i, 'DeletedBy'] = ','.join(deleted_by)

        df.to_excel('messages.xlsx', index=False)

    return redirect(url_for('view_messages') + '#trash')

@app.route('/delete_permanently/<int:message_id>')
@log_event(event="حذف رسالة نهائيًا", request_type="رسائل")
def delete_permanently(message_id):
    if 'id' not in session:
        return redirect('/login')

    user_id = str(session['id'])

    try:
        df = pd.read_excel('messages.xlsx')
        df.fillna('', inplace=True)
    except FileNotFoundError:
        return '📭 ملف الرسائل غير موجود'

    # إنشاء العمود إذا لم يكن موجودًا
    if 'PermanentlyDeletedBy' not in df.columns:
        df['PermanentlyDeletedBy'] = ''

    # تحديد الرسالة
    idx = df[df['ID'] == message_id].index
    if not idx.empty:
        i = idx[0]
        current = str(df.at[i, 'PermanentlyDeletedBy'])
        deleted_by = set(filter(None, current.split(',')))
        deleted_by.add(user_id)  # ✅ أضف المستخدم الحالي إلى المحذوفين
        df.at[i, 'PermanentlyDeletedBy'] = ','.join(deleted_by)
        df.to_excel('messages.xlsx', index=False)

    return redirect('/messages#trash')

@app.route('/approve_message/<int:message_id>')
@log_event(event="الموافقة على رسالة", request_type="رسائل")
def approve_message(message_id):
    if 'id' not in session:
        return redirect('/login')

    try:
        df = pd.read_excel("messages.xlsx")
        message = df[df['ID'] == message_id]

        if not message.empty:
            idx = message.index[0]
            # تحديث حالة القراءة إذا كانت غير مقروءة
            if df.at[idx, 'Status'] == 'Unread':
                df.at[idx, 'Status'] = 'Read'
                df.at[idx, 'DateRead'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            df.at[idx, 'DateApproved'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        df.to_excel("messages.xlsx", index=False)
        print(f"✅ تمت الموافقة على الرسالة رقم {message_id}")
    except Exception as e:
        print(f"❌ خطأ أثناء الموافقة: {e}")

    return redirect('/messages')
@app.route('/reject_message/<int:message_id>')
@log_event(event="رفض رسالة", request_type="رسائل")
def reject_message(message_id):
    if 'id' not in session:
        return redirect('/login')

    try:
        df = pd.read_excel("messages.xlsx")
        message = df[df['ID'] == message_id]

        if not message.empty:
            idx = message.index[0]
            # تحديث حالة القراءة إذا كانت غير مقروءة
            if df.at[idx, 'Status'] == 'Unread':
                df.at[idx, 'Status'] = 'Read'
                df.at[idx, 'DateRead'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            df.at[idx, 'DateApproved'] = '❌ مرفوض'

        df.to_excel("messages.xlsx", index=False)
        print(f"🚫 تم رفض الرسالة رقم {message_id}")
    except Exception as e:
        print(f"❌ خطأ أثناء الرفض: {e}")

    return redirect('/messages')

@app.route('/bulk_approval_by_filter', methods=['POST'])
@log_event(event="موافقة جماعية بالفلترة", request_type="موافقة")
def bulk_approval_by_filter():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    role = session['role']

    # ✅ تعديل مهم: أخذ الفرع من النموذج دائمًا، حتى للموارد
    branch_filter = request.form.get('branch')

    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    req_type = request.form.get('request_type')
    action = request.form.get('action')  # approve أو reject

    df = pd.read_csv('requests.csv', encoding='utf-8-sig')
    df.fillna('', inplace=True)

    filtered = df.copy()

    if branch_filter:
        filtered = filtered[filtered['الفرع'] == branch_filter]
    if start_date:
        filtered = filtered[filtered['تاريخ الطلب'] >= start_date]
    if end_date:
        filtered = filtered[filtered['تاريخ الطلب'] <= end_date]
    if req_type:
        filtered = filtered[filtered['نوع الطلب'] == req_type]

    # ✅ الفلترة حسب الدور
    if role == 'موارد بشرية':
        filtered = filtered[(filtered['الحالة'] == 'مقبول') & (filtered['تاريخ الموافقة الأولى'] != '')]
    elif role == 'مشرف عام':
        filtered = filtered[filtered['الحالة'].isin(['معلق', 'مقبول'])]

    today = datetime.today().strftime('%Y-%m-%d')

    for i in filtered.index:
        if action == 'approve':
            df.at[i, 'الحالة'] = 'مقبول نهائيًا'
            df.at[i, 'تاريخ الموافقة الثانية'] = today
        elif action == 'reject':
            df.at[i, 'الحالة'] = 'مرفوض من الموارد البشرية' if role == 'موارد بشرية' else 'مرفوض من المشرف العام'
            df.at[i, 'تاريخ الموافقة الثانية'] = today

    df.to_csv('requests.csv', index=False, encoding='utf-8-sig')
    flash('✅ تم تنفيذ الإجراء الجماعي بنجاح.')
    return redirect('/dashboard')

@app.route('/save_evaluation', methods=['POST'])
@log_event(event="حفظ تقييم", request_type="تقييم")
def save_evaluation():
    if 'id' not in session or 'name' not in session or 'role' not in session:
        return redirect(url_for('login'))

    # استقبال البيانات من النموذج
    employee_id = request.form.get('رقم الهوية')
    period = request.form.get('period')
    punctuality = float(request.form.get('punctuality') or 0)
    discipline = float(request.form.get('discipline') or 0)
    behavior = float(request.form.get('behavior') or 0)
    attendance = float(request.form.get('attendance') or 0)

    # حساب المجموع
    total_score = round(punctuality + discipline + behavior + attendance, 2)

    # تحميل قواعد العلاوة
    try:
        with open('bonus_rules.json', 'r', encoding='utf-8') as f:
            rules = json.load(f)
    except:
        # إذا لم يتم العثور على الملف، استخدم القيم الافتراضية
        rules = {
            '100': 10,
            '95-99': 5,
            '90-94': 4,
            '85-89': 3,
            '80-84': 2,
            '70-79': 1
        }

    def get_bonus(score):
        if score == 100:
            return rules.get('100', 0)
        elif 95 <= score <= 99:
            return rules.get('95-99', 0)
        elif 90 <= score <= 94:
            return rules.get('90-94', 0)
        elif 85 <= score <= 89:
            return rules.get('85-89', 0)
        elif 80 <= score <= 84:
            return rules.get('80-84', 0)
        elif 70 <= score <= 79:
            return rules.get('70-79', 0)
        else:
            return 0

    bonus = get_bonus(total_score)
    evaluator = session['name']
    evaluation_date = datetime.now().strftime('%Y-%m-%d')

    # تحميل ملف التقييمات
    df = pd.read_csv('evaluations.csv', encoding='utf-8-sig')
    df.fillna('', inplace=True)

    # الفلترة للصف المطلوب
    mask = (df['رقم الهوية'].astype(str) == str(employee_id)) & (df['period'] == period)

    # تحديث القيم
    df.loc[mask, 'punctuality'] = punctuality
    df.loc[mask, 'discipline'] = discipline
    df.loc[mask, 'behavior'] = behavior
    df.loc[mask, 'attendance'] = attendance
    df.loc[mask, 'total_score'] = total_score
    df.loc[mask, 'bonus_percentage'] = bonus
    df.loc[mask, 'evaluator'] = evaluator
    df.loc[mask, 'evaluation_date'] = evaluation_date

    # حفظ الملف
    df.to_csv('evaluations.csv', index=False, encoding='utf-8-sig')

    flash('✅ تم حفظ التقييم بنجاح', 'success')
    return redirect('/evaluations')
@app.route('/evaluations')
@log_event(event="عرض التقييمات", request_type="عرض")
def evaluations():
    if 'id' not in session or 'role' not in session:
        return redirect(url_for('login'))

    sync_evaluations()  # تحديث التقييمات حسب الفترة الحالية

    role = session['role']
    branch = session.get('branch')
    user_id = session.get('id')
    name = session.get('name')

    df = pd.read_csv('evaluations.csv', encoding='utf-8-sig')
    df.fillna('', inplace=True)

    # فلترة حسب الدور
    if role == 'مدير':
        df = df[df['الفرع'] == branch]
    elif role == 'موظف':
        df = df[df['رقم الهوية'].astype(str) == str(user_id)]

        # ✅ تحديث العمود "read" عند دخول الموظف
        if not df.empty and 'read' in df.columns:
            df_all = pd.read_csv('evaluations.csv', encoding='utf-8-sig')
            df_all['read'] = df_all['read'].fillna('')
            updated = False
            for i in df_all.index:
                if str(df_all.at[i, 'رقم الهوية']) == str(user_id) and df_all.at[i, 'read'] != 'نعم':
                    df_all.at[i, 'read'] = 'نعم'
                    updated = True
            if updated:
                df_all.to_csv('evaluations.csv', index=False, encoding='utf-8-sig')

    # التحقق هل للموظف تقييم (نستخدمها لاحقًا في الزر)
    has_eval = False
    if role == 'موظف':
        employee_evals = df[df['رقم الهوية'].astype(str) == str(user_id)]
        unread = employee_evals['read'].astype(str).str.strip() == ''
        has_eval = not employee_evals.empty and unread.any()

    # حساب الفترة الحالية
    now = datetime.now()
    current_period = f"{now.year}-H1" if now.month <= 6 else f"{now.year}-H2"

    # تحميل قواعد العلاوة
    try:
        with open('bonus_rules.json', 'r', encoding='utf-8') as f:
            bonus_rules = json.load(f)
    except:
        bonus_rules = {}

    return render_template(
        'evaluations.html',
        evaluations=df.to_dict(orient='records'),
        user_role=role,
        user_branch=branch,
        user_name=name,
        bonus_rules=bonus_rules,
        current_period=current_period,
        has_eval=has_eval
    )

@app.route('/sync_evaluations', methods=['POST'])
@log_event(event="مزامنة التقييمات", request_type="مزامنة")
def sync_evaluations_route():
    sync_evaluations()
    flash("✅ تمت مزامنة التقييمات بنجاح", "success")
    return redirect('/evaluations')

@app.route('/update_bonus_rules', methods=['POST'])
@log_event(event="تحديث شرائح العلاوة", request_type="تعديل")
def update_bonus_rules():
    if session.get('role') != 'مشرف عام':
        return redirect(url_for('login'))

    rules = {}
    for key in ['100', '95-99', '90-94', '85-89', '80-84', '70-79']:
        value = request.form.get(key)
        if value:
            try:
                value_float = float(value)
                if 0 <= value_float <= 200:
                    rules[key] = value_float
            except:
                continue

    with open('bonus_rules.json', 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    flash('✅ تم تحديث شرائح العلاوة بنجاح', 'success')
    return redirect('/evaluations')
@app.route('/add_employee', methods=['POST'])
@log_event(event="إضافة موظف", request_type="تعديل")
def add_employee():
    if session.get("role") not in ['موارد بشرية', 'مشرف عام']:
        return "غير مصرح", 403

    df = pd.read_csv("employees.csv", encoding="utf-8-sig")
    new_row = {
        'رقم الهوية': request.form['employee_id'],
        'الاسم': request.form['employee_name'],
        'البريد': request.form['email'],
        'كلمة المرور': request.form['password'],
        'الدور': request.form['role'],
        'الفرع': request.form['branch'],
        'رقم الهاتف': request.form['phone'],
        'تاريخ آخر إجازة': request.form.get('last_leave', ''),
        'مدة الاستحقاق (بالأيام)': request.form['entitlement_days'],
        'عدد الطلبات': 0,
        'آخر تقييم (مجموع النسبة)': '',
        'سجل الإضافة/الحذف': f"تمت الإضافة بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        'مهنة': request.form.get('job_title', ''),
        'سجل تجاري': request.form.get('commercial_record', ''),
        'جنسية': request.form.get('nationality', ''),
        'جنس': request.form.get('gender', ''),
        'تاريخ ميلاد': request.form.get('birth_date', ''),
        'رمز الكفالة': request.form.get('sponsor_code', ''),
        'الأجر': request.form.get('salary', ''),
        'رقم حدود': request.form.get('border_number', ''),
        'تاريخ التحاق': request.form.get('joining_date', '')
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv("employees.csv", index=False, encoding='utf-8-sig')
    return redirect('/manage_employees')

@app.route('/delete_employee', methods=['POST'])
@log_event(event="حذف موظف", request_type="تعديل")
def delete_employee():
    if session.get("role") not in ['موارد بشرية', 'مشرف عام']:
        return "غير مصرح", 403

    emp_id = request.form['employee_id']
    df = pd.read_csv("employees.csv")

    # المقارنة بين النصوص
    idx = df[df['رقم الهوية'].astype(str) == str(emp_id)].index

    if not idx.empty:
        # التأكد من أن العمود نصي وليس NaN
        current_log = df.at[idx[0], 'سجل الإضافة/الحذف']
        if pd.isna(current_log):
            current_log = ""  # إذا كانت الخلية فارغة

        # تحديث السجل
        df.at[idx[0], 'سجل الإضافة/الحذف'] = (
            f"{current_log} | تم الحذف بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        # حذف الصف
        df.drop(idx, inplace=True)

        # حفظ الملف
        df.to_csv("employees.csv", index=False, encoding="utf-8-sig")

    return redirect('/manage_employees')

@app.route('/manage_employees')
@log_event(event="عرض إدارة الموظفين", request_type="عرض")
def manage_employees():
    role = session.get("role")
    branch = session.get("branch")

    df = pd.read_csv("employees.csv")
    df = df.fillna('')

    if role == 'مدير':
        df = df[df['الفرع'] == branch]

    # تحميل قائمة الفروع
    if os.path.exists("branches.json"):
        with open("branches.json", "r", encoding="utf-8") as f:
            branches = json.load(f)
    else:
        branches = []

    employees = df.to_dict(orient='records')
    return render_template("manage_employees.html", employees=employees, branches=branches)
@app.route('/update_employee', methods=['POST'])
@log_event(event="تحديث بيانات موظف", request_type="تعديل")
def update_employee():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    index = int(request.form['index'])
    df = pd.read_csv('employees.csv', encoding='utf-8-sig')

    # تأمين: تحقق من أن الفهرس موجود
    if index >= len(df):
        flash("⚠️ الموظف غير موجود", "danger")
        return redirect('/manage_employees')

    # قائمة الحقول المطلوب تعديلها
    fields = {
        'الاسم': 'employee_name',
        'البريد': 'email',
        'كلمة المرور': 'password',
        'الدور': 'role',
        'الفرع': 'branch',
        'رقم الهاتف': 'phone',
        'تاريخ آخر إجازة': 'last_leave',
        'مدة الاستحقاق (بالأيام)': 'entitlement_days',
        'مهنة': 'job_title',
        'سجل تجاري': 'commercial_record',
        'جنسية': 'nationality',
        'جنس': 'gender',
        'تاريخ ميلاد': 'birth_date',
        'رمز الكفالة': 'sponsor_code',
        'الاجر': 'salary',
        'رقم حدود': 'border_number',
        'تاريخ التحاق': 'joining_date'
    }

    for col_name, form_key in fields.items():
        if form_key in request.form:
            value = request.form[form_key]
            if col_name in ['الاجر', 'مدة الاستحقاق (بالأيام)', 'رقم الهاتف', 'رقم حدود']:
                try:
                    df.at[index, col_name] = int(float(value))
                except:
                    df.at[index, col_name] = 0
            else:
                df.at[index, col_name] = value

    df.to_csv('employees.csv', index=False, encoding='utf-8-sig')
    flash("✅ تم تحديث بيانات الموظف بنجاح", "success")
    return redirect('/manage_employees')

@app.route('/update_branches', methods=['POST'])
@log_event(event="تحديث الفروع", request_type="تعديل")
def update_branches():
    if session.get("role") not in ['موارد بشرية', 'مشرف عام']:
        return "غير مصرح", 403

    raw = request.form['branches']
    branches = [b.strip() for b in raw.split(',') if b.strip()]
    with open("branches.json", "w", encoding="utf-8") as f:
        json.dump(branches, f, ensure_ascii=False)

    flash("تم تحديث الفروع بنجاح")
    return redirect('/manage_employees')
# قسم الموارد البشرية وبياناتهم 
from flask import render_template, session, request, redirect, flash, jsonify
import pandas as pd
from datetime import datetime
from pathlib import Path

@app.route("/employee_status")
@log_event(event="عرض حالة الموظفين", request_type="عرض")
def employee_status():
    role = session.get("role", "")
    if role not in ["موارد بشرية", "مشرف عام"]:
        flash("غير مصرح لك بعرض هذه الصفحة", "danger")
        return redirect("/")

    try:
        # تشغيل دالة التحديث التلقائي من ملف الموظفين
        generate_employee_status_internal()

        # قراءة الملف المحدث
        df = pd.read_csv("employee_status.csv", encoding="utf-8-sig")
        data = df.to_dict(orient="records")
    except Exception as e:
        flash(f"خطأ في تحميل البيانات: {str(e)}", "danger")
        data = []

    return render_template("employee_status.html", data=data, role=role)

def generate_employee_status_internal():
    status_file = "employee_status.csv"

    # إذا الملف موجود نعمل مزامنة بدلاً من الإنشاء فقط
    if Path(status_file).exists():
        try:
            df_status = pd.read_csv(status_file, encoding="utf-8-sig")
            df_emp = pd.read_csv("employees.csv", encoding="utf-8-sig")

            # حذف أي موظف لم يعد موجودًا
            emp_ids = set(df_emp['رقم الهوية'].astype(str))
            df_status = df_status[df_status['رقم الهوية'].astype(str).isin(emp_ids)]

            # إضافة أي موظف جديد غير موجود في status
            existing_ids = set(df_status['رقم الهوية'].astype(str))
            new_emps = df_emp[~df_emp['رقم الهوية'].astype(str).isin(existing_ids)]
            for _, row in new_emps.iterrows():
                df_status = pd.concat([df_status, pd.DataFrame([{
                    "رقم الهوية": row['رقم الهوية'],
                    "الاسم": row['الاسم'],
                    "الفرع": row['الفرع'],
                    "الدور": row['الدور'],
                    "رمز الكفالة": row.get('رمز الكفالة', ""),
                    "سجل تجاري": row.get('سجل تجاري', ""),
                    "تاريخ انتهاء الإقامة": "",
                    "هل يستحق البطاقة؟": "نعم",
                    "تاريخ انتهاء البطاقة الصحية": "",
                    "هل يستحق التأمين؟": "نعم",
                    "تاريخ انتهاء التأمين": "",
                    "تاريخ انتهاء العقد": "",
                    "ملاحظات عامة": "",
                    "هل ترك العمل؟": "لا",
                    "هل يحتاج تجديد الإقامة؟": "لا",
                    "هل يحتاج تجديد البطاقة؟": "لا",
                    "هل يحتاج تجديد التأمين؟": "لا",
                    "هل يحتاج تجديد العقد؟": "لا",
                    "هل رُفع من المنصات؟": "",
                    "هل رُفع من التأمين؟": ""
                }])], ignore_index=True)

            df_status.to_csv(status_file, index=False, encoding="utf-8-sig")
            return
        except Exception as e:
            print(f"خطأ في المزامنة: {e}")
            return

    # إنشاء الملف إذا غير موجود
    df_emp = pd.read_csv('employees.csv', encoding='utf-8-sig')

    if "الكفالة" in df_emp.columns:
        df_emp.rename(columns={"الكفالة": "رمز الكفالة"}, inplace=True)

    columns_to_copy = [
        "رقم الهوية", "الاسم", "الفرع", "الدور", "رمز الكفالة", "سجل تجاري",
        "تاريخ انتهاء الإقامة", "هل يستحق البطاقة؟", "تاريخ انتهاء البطاقة الصحية",
        "هل يستحق التأمين؟", "تاريخ انتهاء التأمين",
        "تاريخ انتهاء العقد", "ملاحظات عامة", "هل ترك العمل؟"
    ]

    for col in columns_to_copy:
        if col not in df_emp.columns:
            df_emp[col] = ""

    df = df_emp[columns_to_copy].copy()

    df['هل يحتاج تجديد الإقامة؟'] = "لا"
    df['هل يحتاج تجديد البطاقة؟'] = "لا"
    df['هل يحتاج تجديد التأمين؟'] = "لا"
    df['هل يحتاج تجديد العقد؟'] = "لا"
    df['هل رُفع من المنصات؟'] = ""
    df['هل رُفع من التأمين؟'] = ""

    df.to_csv("employee_status.csv", index=False, encoding='utf-8-sig')

@app.route("/update_employee_status", methods=["POST"])
@log_event(event="تحديث حالة الموظفين", request_type="تعديل")
def update_employee_status():
    role = session.get("role", "")
    if role not in ["موارد بشرية", "مشرف عام"]:
        return "غير مصرح", 403

    try:
        df = pd.read_csv("employee_status.csv", encoding="utf-8-sig")
        updated_data = request.json

        for i, row in enumerate(updated_data):
            for col in df.columns:
                if col in row:
                    value = row[col]
                    if isinstance(value, str):
                        df.at[i, col] = value
                    elif value is None or pd.isna(value):
                        df.at[i, col] = ""
                    else:
                        df.at[i, col] = str(value)

        df.to_csv("employee_status.csv", index=False, encoding="utf-8-sig")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/generate_employee_status')
@log_event(event="توليد حالة الموظفين", request_type="تحديث")
def generate_employee_status():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    try:
        generate_employee_status_internal()
        return redirect('/employee_status')
    except Exception as e:
        return f"❌ خطأ أثناء التوليد: {str(e)}"


@app.route('/hr_tasks')
@log_event(event="عرض مهام الموارد البشرية", request_type="عرض")
def hr_tasks():
    if 'id' not in session or session['role'] not in ['موارد بشرية','مشرف عام']:
        return redirect('/login')

    try:
        df = pd.read_excel('hr_tasks.xlsx')
    except FileNotFoundError:
        df = pd.DataFrame(columns=['task_id','task_name','task_details','assigned_by','status','due_date','supervisor_evaluation'])

    tasks = df.to_dict(orient='records')
    return render_template('hr_tasks.html', tasks=tasks)
@app.route('/add_or_update_task', methods=['POST'])
def add_or_update_task():
    if 'id' not in session or session['role'] not in ['موارد بشرية','مشرف عام']:
        return redirect('/login')

    action = request.form['action']

    try:
        df = pd.read_excel('hr_tasks.xlsx')
    except FileNotFoundError:
        df = pd.DataFrame(columns=['task_id','task_name','task_details','assigned_by','status','due_date','added_date','supervisor_evaluation'])

    if action == 'add':
        task_name = request.form['task_name']
        task_details = request.form['task_details']
        due_date = request.form['due_date']
        assigned_by = session['name']
        added_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_id = int(df['task_id'].max() + 1) if not df.empty else 1
        new_row = {
            'task_id': new_id,
            'task_name': task_name,
            'task_details': task_details,
            'assigned_by': assigned_by,
            'status': 'جديد / New',
            'due_date': due_date,
            'added_date': added_date,
            'supervisor_evaluation': ''
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        # ✅ تسجيل الإضافة
        log_action(session['name'], session['id'], session['role'], session['branch'], 'إضافة مهمة جديدة', '', str(new_id))

    elif action == 'evaluate' and session['role'] == 'مشرف عام':
        task_id = int(request.form['task_id'])
        evaluation = request.form['evaluation']
        df.loc[df['task_id'] == task_id, 'supervisor_evaluation'] = evaluation

        # ✅ تسجيل التقييم
        log_action(session['name'], session['id'], session['role'], session['branch'], 'تقييم مهمة', '', str(task_id))

    elif action == 'delete' and session['role'] == 'مشرف عام':
        task_id = int(request.form['task_id'])
        df = df[df['task_id'] != task_id]

        # ✅ تسجيل الحذف
        log_action(session['name'], session['id'], session['role'], session['branch'], 'حذف مهمة', '', str(task_id))

    elif action == 'complete' and session['role'] == 'موارد بشرية':
        task_id = int(request.form['task_id'])
        df.loc[df['task_id'] == task_id, 'status'] = 'تمت'

        # ✅ تسجيل الإنجاز
        log_action(session['name'], session['id'], session['role'], session['branch'], 'إنهاء مهمة', '', str(task_id))

    df.to_excel('hr_tasks.xlsx', index=False)
    return redirect('/hr_tasks')

ATTENDANCE_FILE = 'attendance.csv'

@app.route('/attendance', methods=['GET'])
@log_event(event="عرض صفحة الحضور", request_type="عرض")
def attendance():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    table = []
    grouped_stats_dict = []
    selected_month = request.args.get("month")
    selected_branch = request.args.get("branch")

    try:
        df = pd.read_csv("attendance.csv", encoding='utf-8-sig')
        df.fillna('', inplace=True)

        # قائمة الفروع والأشهر المتوفرة
        all_months = sorted(df["الشهر"].dropna().unique().tolist()) if "الشهر" in df.columns else []
        all_branches = sorted(df["الفرع"].dropna().unique().tolist()) if "الفرع" in df.columns else []

        # فلترة حسب الشهر
        if selected_month:
            df = df[df["الشهر"] == selected_month]

        # فلترة حسب الفرع
        if selected_branch:
            df = df[df["الفرع"] == selected_branch]

        # جدول العرض بعد الفلترة
        table = df.to_dict(orient='records')

        # جدول الإحصائيات حسب الفرع
        if "الفرع" in df.columns:
           # تحويل العمود قبل الحساب
           df["ساعات عمل الموظف"] = pd.to_numeric(df["ساعات عمل الموظف"], errors='coerce')

           grouped_stats = df.groupby("الفرع").agg({
               "رقم الهوية": pd.Series.nunique,
               "غياب": lambda x: pd.to_numeric(x, errors='coerce').sum(),
               "تأخير": lambda x: pd.to_numeric(x, errors='coerce').sum(),
               "إجمالي استقطاع": lambda x: pd.to_numeric(x, errors='coerce').sum(),
               "ساعات عمل الموظف": 'mean'  # ✅ معدل ساعات عمل الموظف
           }).reset_index()

           grouped_stats.rename(columns={
               "الفرع": "الفرع",
               "رقم الهوية": "عدد الموظفين",
               "غياب": "مجموع الغياب",
               "تأخير": "ساعات التأخير",
               "إجمالي استقطاع": "إجمالي الاستقطاع",
               "ساعات عمل الموظف": "معدل ساعات العمل"
           }, inplace=True)

           # تقريب المعدل إلى رقم عشري واحد
           grouped_stats["معدل ساعات العمل"] = grouped_stats["معدل ساعات العمل"].round(1)

           grouped_stats_dict = grouped_stats.to_dict(orient="records")

    except Exception as e:
        flash(f"⚠️ خطأ أثناء قراءة الملف: {e}", "danger")
        all_months = []
        all_branches = []

    return render_template(
        'attendance.html',
        table=table,
        grouped_stats=grouped_stats_dict,
        all_months=all_months,
        all_branches=all_branches,
        selected_month=selected_month,
        selected_branch=selected_branch
    )

@app.route('/upload_attendance', methods=['POST'])
@log_event(event="رفع ملف الحضور", request_type="الحضور")
def upload_attendance():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    file = request.files.get('file')
    if not file:
        flash('📁 لم يتم اختيار ملف', 'danger')
        return redirect('/attendance')

    try:
        new_df = pd.read_excel(file, dtype={'رقم الهوية': str})
        new_df["رقم الهوية"] = new_df["رقم الهوية"].astype(str).str.strip().str.zfill(12)

        # ✅ تحقق من ملف الموظفين الحالي مباشرة
        employees_df = pd.read_csv("employees.csv", dtype=str)
        valid_ids = employees_df["رقم الهوية"].astype(str).str.strip().unique()

        # ✅ التحقق من أرقام الهوية
        invalid_ids = new_df[~new_df["رقم الهوية"].isin(valid_ids)]["رقم الهوية"].unique()
        if len(invalid_ids) > 0:
            msg = "❌ أرقام هوية غير معروفة: " + ", ".join(invalid_ids)
            flash(msg, "danger")
            return redirect('/attendance')

        # ✅ دمج مع البيانات السابقة إن وجدت
        if os.path.exists("attendance.csv"):
            old_df = pd.read_csv("attendance.csv", dtype=str)
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        # حفظ البيانات
        combined_df.to_csv("attendance.csv", index=False, encoding="utf-8-sig")
        flash('✅ تم رفع الملف ودمجه بنجاح', 'success')

    except Exception as e:
        flash(f'❌ حدث خطأ أثناء رفع الملف: {str(e)}', 'danger')

    return redirect('/attendance')

@app.route('/download_bulk_template')
def download_bulk_template():
    path = os.path.abspath("attendance_bulk_template.xlsx")
    directory = os.path.dirname(path)
    filename = os.path.basename(path)
    return send_from_directory(directory, filename, as_attachment=True)
@app.route('/delete_attendance', methods=['POST'])
@log_event(event="حذف صف من الحضور", request_type="الحضور", request_id_key="id_number")
def delete_attendance():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    emp_id = request.form.get("رقم الهوية")
    month = request.form.get("الشهر")

    try:
        df = pd.read_csv("attendance.csv", dtype=str)

        # حذف السطر المطابق (حسب رقم الهوية والشهر فقط)
        df = df[~((df["رقم الهوية"] == emp_id) & (df["الشهر"] == month))]

        df.to_csv("attendance.csv", index=False, encoding="utf-8-sig")
        flash("✅ تم حذف السجل بنجاح", "success")
    except Exception as e:
        flash(f"❌ حدث خطأ أثناء الحذف: {str(e)}", "danger")

    return redirect('/attendance')

@app.route('/send_reset_link', methods=['POST'])
def send_reset_link():
    email = request.form['email']
    df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')

    if email not in df['البريد'].values:
        return "❌ البريد غير مسجل لدينا"

    token = generate_reset_token(email)
    reset_url = url_for('reset_password_token', token=token, _external=True)

    subject = "🔐 رابط تغيير كلمة المرور"
    body = f"""مرحبًا،

طلبت استعادة كلمة المرور. اضغط على الرابط التالي لتعيين كلمة مرور جديدة (صالح لمدة ساعة):

{reset_url}

إذا لم تطلب هذا الرابط، تجاهل هذه الرسالة.
"""

    send_email(email, subject, body)  # الدالة موجودة لديك مسبقًا
    return "✅ تم إرسال الرابط إلى بريدك الإلكتروني"
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    email = verify_reset_token(token)
    if not email:
        return "❌ الرابط منتهي أو غير صالح"

    message = ""
    if request.method == 'POST':
        new_password = request.form['new_password']
        df = pd.read_csv(EMPLOYEE_FILE, encoding='utf-8-sig')
        df.loc[df['البريد'] == email, 'كلمة المرور'] = new_password
        df.to_csv(EMPLOYEE_FILE, index=False, encoding='utf-8-sig')
        message = "✅ تم تغيير كلمة المرور بنجاح"
        return redirect('/login')

    return render_template('reset_password.html', message=message)

def log_event(event_name=None, request_type=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_id = session.get('id', 'غير معروف')
            role = session.get('role', 'غير معروف')
            ip = request.remote_addr
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with open('logs.csv', mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([timestamp, user_id, role, ip, event_name, request_type, request.path])

            return f(*args, **kwargs)
        return wrapper
    return decorator
@app.route('/full_employee_info', methods=['GET', 'POST'])
@log_event(event_name="عرض ملف الموظف الكامل", request_type="عرض")
def full_employee_info():
    if 'id' not in session or session['role'] != 'مشرف عام':
        return redirect('/login')

    emp_df = pd.read_csv('employees.csv', dtype=str)
    req_df = pd.read_csv('requests.csv', dtype=str)
    eval_df = pd.read_csv('evaluations.csv', dtype=str)
    att_df = pd.read_csv('attendance.csv', dtype=str)
    status_df = pd.read_csv('employee_status.csv', dtype=str)

    # ملفات غير مستخدمة الآن
    # leave_dec_df = pd.read_csv('two_year_leave_decisions.csv', dtype=str)
    # logs_df = pd.read_csv('logs.csv', dtype=str)
    # msg_df = pd.read_excel('messages.xlsx', dtype=str)

    selected_branch = request.form.get('branch') if request.method == 'POST' else None
    selected_id = request.form.get('employee_id') if request.method == 'POST' else None

    # قائمة الفروع المتاحة
    branches = emp_df['الفرع'].dropna().unique() if 'الفرع' in emp_df.columns else []

    # فلترة الموظفين بناءً على الفرع
    employees_filtered = emp_df[emp_df['الفرع'] == selected_branch] if selected_branch else emp_df

    # فلترة بيانات الموظف
    filtered_data = {}
    if selected_id:
        filtered_data = {
            'employee': emp_df[emp_df['رقم الهوية'] == selected_id],
            'requests': req_df[req_df['رقم الهوية'] == selected_id],
            'evaluations': eval_df[eval_df['رقم الهوية'] == selected_id],
            'attendance': att_df[att_df['رقم الهوية'] == selected_id],
            'status': status_df[status_df['رقم الهوية'] == selected_id]
        }

    return render_template('full_employee_info.html',
                           employees=employees_filtered,
                           branches=branches,
                           selected_branch=selected_branch,
                           selected_id=selected_id,
                           data=filtered_data)

from werkzeug.utils import secure_filename

EXCEL_FOLDER = os.path.dirname(os.path.abspath(__file__))

@app.route('/manage_excels', methods=['GET', 'POST'])
@log_event(event_name="إدارة ملفات Excel", request_type="إدارة")
def manage_excels():
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')

    # نستخدم المجلد الحالي الذي فيه app.py وملفات Excel/CSV
    EXCEL_FOLDER = os.path.dirname(os.path.abspath(__file__))

    # جلب كل الملفات .xlsx و .csv
    all_files = [f for f in os.listdir(EXCEL_FOLDER) if f.endswith(('.xlsx', '.csv'))]

    # فصل bulk في قائمة مستقلة
    bulk_files = [f for f in all_files if 'bulk' in f.lower()]
    normal_files = [f for f in all_files if 'bulk' not in f.lower()]

    # ترتيب كل جزء على حدة
    files = sorted(normal_files) + sorted(bulk_files)

    # التعامل مع رفع ملف
    if request.method == 'POST':
        filename = request.form['filename']
        file = request.files['new_file']
        if file and filename in files:
            path = os.path.join(EXCEL_FOLDER, filename)
            file.save(path)
            flash(f'✅ تم استبدال الملف {filename} بنجاح')
        return redirect('/manage_excels')

    return render_template('manage_excels.html', files=files)

@app.route('/download_excel/<filename>')
def download_excel(filename):
    if 'id' not in session or session['role'] not in ['موارد بشرية', 'مشرف عام']:
        return redirect('/login')
    return send_from_directory(EXCEL_FOLDER, filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True, port=5000)

# --- إحصائيات المشرف العام ---
