# @Time : 15/7/2024 下午9:53
import smtplib
import os
from datetime import datetime
from email.mime.text import MIMEText

import pytz


def get_beijing_time():
    utc_time = datetime.now(pytz.utc)
    return utc_time.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %A %H:%M')


def send_QQ_email_plain(content):
    sender = os.getenv('SMTP_USER', '').strip()
    passwd = os.getenv('SMTP_PASS', '').strip()
    recipient = os.getenv('EMAIL_ADDRESS', '').strip()
    smtp_host = os.getenv('SMTP_HOST', 'smtp.qq.com').strip()
    smtp_port = int(os.getenv('SMTP_PORT', '465'))

    if not recipient:
        print('未配置 EMAIL_ADDRESS，跳过邮件发送')
        return False
    if not sender or not passwd:
        print('未配置 SMTP_USER/SMTP_PASS，跳过邮件发送')
        return False

    msg = MIMEText(f'签到结果：{content}', 'plain', 'utf-8')
    result_status = '成功' if '成功' in content else '失败'
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = f'查寝 {result_status} {get_beijing_time()}'

    try:
        if smtp_port == 465:
            smtp = smtplib.SMTP_SSL(smtp_host, 465, timeout=30)
        else:
            smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            smtp.starttls()
        smtp.login(sender, passwd)
        smtp.sendmail(sender, recipient, msg.as_string())
        smtp.quit()
        print('邮件发送成功')
        return True
    except Exception as first_error:
        if smtp_port == 465:
            try:
                smtp = smtplib.SMTP(smtp_host, 587, timeout=30)
                smtp.starttls()
                smtp.login(sender, passwd)
                smtp.sendmail(sender, recipient, msg.as_string())
                smtp.quit()
                print('邮件发送成功（587 STARTTLS）')
                return True
            except Exception as fallback_error:
                print(f'邮件发送失败（465 SSL: {first_error}; 587 STARTTLS: {fallback_error}）')
                return False
        print(f'邮件发送失败（{type(first_error).__name__}: {first_error}）')
        return False
