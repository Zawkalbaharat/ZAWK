# email.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(to_email, subject, body):
    sender_email = "no.reply.zawk@gmail.com"        # ← بريدك الذي أنشأته
    sender_password = "mlnhdmbyfnkalphg"    # ← App Password الصحيح

    auto_notice = "\n\n🔔 هذه رسالة آلية. الرجاء عدم الرد على هذا البريد.\nThis is an automated message. Please do not reply to this email."
    full_body = body + auto_notice

    # إعداد الرسالة
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(full_body, "plain"))

    try:
        print("🔄 بدء الاتصال بـ Gmail...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.set_debuglevel(1)  # ← مهم جدًا لعرض تفاصيل الجلسة
        server.starttls()
        print("🔐 محاولة تسجيل الدخول...")
        server.login(sender_email, sender_password)
        print("✅ تم تسجيل الدخول")
        server.sendmail(sender_email, to_email, msg.as_string())
        print(f"✅ تم إرسال الإيميل إلى: {to_email}")
        server.quit()
    except Exception as e:
        print("❌ فشل إرسال الإيميل:")
        print(str(e))
        print("📢 تمت قراءة ملف notification/email.py")

