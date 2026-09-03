import smtplib
from datetime import datetime
from zoneinfo import ZoneInfo
from email.mime.text import MIMEText

from flask import current_app

# 北京时间
BJT = ZoneInfo('Asia/Shanghai')

# 中文星期映射
_WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def get_beijing_time():
    now = datetime.now(BJT)
    weekday = _WEEKDAYS[now.weekday()]
    return now.strftime(f'%Y-%m-%d {weekday} %H:%M')


def send_email(subject: str, content: str, to_address: str):
    """发送邮件，返回是否发送成功。"""
    if not to_address:
        print(f'未配置邮箱，跳过邮件发送。结果：{content}')
        return False

    smtp_host = current_app.config.get('SMTP_HOST', '')
    smtp_port = current_app.config.get('SMTP_PORT', 465)
    smtp_user = current_app.config.get('SMTP_USER', '')
    smtp_pass = current_app.config.get('SMTP_PASS', '')

    if not smtp_user or not smtp_pass:
        print(f'SMTP 未配置，跳过邮件发送。结果：{content}')
        return False

    msg = MIMEText(content, 'plain', 'utf-8')
    msg['From'] = smtp_user
    msg['To'] = to_address
    msg['Subject'] = subject

    try:
        if int(smtp_port) == 465:
            # 465 端口使用连接即加密的 SSL；部分网络会拦截该端口。
            smtp = smtplib.SMTP_SSL(smtp_host, 465, timeout=15)
        else:
            # QQ 邮箱推荐使用 587 端口，通过 STARTTLS 升级为加密连接。
            smtp = smtplib.SMTP(smtp_host, int(smtp_port), timeout=15)
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
        smtp.login(smtp_user, smtp_pass)
        smtp.sendmail(smtp_user, to_address, msg.as_string())
        smtp.quit()
        print(f'邮件发送成功 -> {to_address}')
        return True
    except Exception as e:
        print(f'邮件发送失败: {e}')
        return False


def send_verification_code(to_address: str, code: str, purpose: str):
    """发送注册或找回密码验证码。"""
    action = '注册账号' if purpose == 'register' else '重置密码'
    subject = f'查寝管理系统 - {action}验证码'
    content = (
        f'您好，您正在进行{action}。\n\n'
        f'验证码：{code}\n'
        '验证码 10 分钟内有效，请勿将验证码告知他人。\n\n'
        '如非本人操作，请忽略此邮件。'
    )
    return send_email(subject, content, to_address)


def send_gotobed_result(content: str, to_address: str):
    """发送查寝结果通知"""
    formatted_date = get_beijing_time()
    result_status = '✅成功' if '成功' in content else '❌失败'
    subject = f'查寝 {result_status} {formatted_date}'
    body = f'签到结果：{content}'
    send_email(subject, body, to_address)
