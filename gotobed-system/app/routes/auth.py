import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify, get_flashed_messages
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from .. import login_manager
from ..email_sender import send_verification_code
from ..models import db, Account, EmailVerificationCode, BJT

auth_bp = Blueprint('auth', __name__)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
CODE_TTL_MINUTES = 10
CODE_RESEND_SECONDS = 60
MAX_CODE_ATTEMPTS = 5


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Account, int(user_id)) if str(user_id).isdigit() else None


def _normal_email(value):
    return (value or '').strip().lower()


def _issue_code(email, purpose):
    """生成验证码并发送邮件；返回错误提示或 None。"""
    now = datetime.now(BJT).replace(tzinfo=None)
    recent = EmailVerificationCode.query.filter_by(email=email, purpose=purpose).order_by(
        EmailVerificationCode.created_at.desc()).first()
    if recent and (now - recent.created_at).total_seconds() < CODE_RESEND_SECONDS:
        return '验证码发送过于频繁，请稍后再试'
    code = f'{secrets.randbelow(1000000):06d}'
    record = EmailVerificationCode(email=email, purpose=purpose,
        code_hash=generate_password_hash(code), expires_at=now + timedelta(minutes=CODE_TTL_MINUTES))
    db.session.add(record)
    db.session.commit()
    if not send_verification_code(email, code, purpose):
        db.session.delete(record)
        db.session.commit()
        return '验证码邮件发送失败，请检查 SMTP 配置'
    return None


def _verify_code(email, purpose, code):
    """校验最近一条验证码，并在成功后标记为已使用。"""
    now = datetime.now(BJT).replace(tzinfo=None)
    record = EmailVerificationCode.query.filter_by(email=email, purpose=purpose).order_by(
        EmailVerificationCode.created_at.desc()).first()
    if not record or record.consumed_at or record.expires_at < now:
        return False, '验证码不存在或已过期'
    if record.attempts >= MAX_CODE_ATTEMPTS:
        return False, '验证码错误次数过多，请重新发送'
    record.attempts += 1
    if not check_password_hash(record.code_hash, (code or '').strip()):
        db.session.commit()
        return False, '验证码错误'
    record.consumed_at = now
    db.session.commit()
    return True, None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('users.user_list'))
    email = _normal_email(request.args.get('email'))
    if request.method == 'POST':
        email = _normal_email(request.form.get('email'))
        account = Account.query.filter_by(email=email).first()
        if account and account.enabled and account.email_verified_at and check_password_hash(account.password_hash, request.form.get('password', '')):
            account.last_login_at = datetime.now(BJT).replace(tzinfo=None)
            db.session.commit()
            login_user(account)
            return redirect(request.args.get('next') or url_for('users.user_list'))
        flash('邮箱或密码错误，或邮箱尚未验证', 'danger')
    # 登录失败时回显邮箱，方便用户只重新输入密码；密码字段保持为空。
    return render_template('login.html', email=email)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = _normal_email(request.form.get('email'))
        if not EMAIL_RE.match(email):
            flash('请输入有效的邮箱地址', 'danger')
        elif Account.query.filter_by(email=email).first():
            flash('该邮箱已注册，请直接登录或找回密码', 'danger')
        elif len(request.form.get('password', '')) < 8 or request.form.get('password') != request.form.get('confirm_password'):
            flash('密码至少 8 位，且两次输入必须一致', 'danger')
        else:
            ok, error = _verify_code(email, 'register', request.form.get('code'))
            if ok:
                account = Account(email=email, password_hash=generate_password_hash(request.form['password']),
                                  email_verified_at=datetime.now(BJT).replace(tzinfo=None))
                db.session.add(account)
                db.session.commit()
                flash('注册成功，请登录', 'success')
                return redirect(url_for('auth.login'))
            flash(error, 'danger')
    return render_template('register.html')


@auth_bp.route('/register/send-code', methods=['POST'])
def register_send_code():
    email = _normal_email(request.form.get('email'))
    if not EMAIL_RE.match(email):
        flash('请输入有效的邮箱地址', 'danger')
    elif Account.query.filter_by(email=email).first():
        flash('该邮箱已注册，请直接登录或找回密码', 'danger')
    else:
        error = _issue_code(email, 'register')
        flash(error or '验证码已发送，请查收邮件', 'danger' if error else 'success')
    # 注册页通过 fetch 请求验证码时返回 JSON，避免整页刷新导致表单内容丢失。
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
        messages = get_flashed_messages(with_categories=True)
        category, message = messages[-1] if messages else ('success', '验证码已发送，请查收邮件')
        return jsonify({'ok': category == 'success', 'message': message})
    return redirect(url_for('auth.register'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = _normal_email(request.form.get('email'))
        if not EMAIL_RE.match(email):
            flash('请输入有效的邮箱地址', 'danger')
        else:
            if Account.query.filter_by(email=email).first():
                error = _issue_code(email, 'reset_password')
                if error:
                    flash(error, 'danger')
                    return render_template('forgot_password.html')
            flash('如果该邮箱已注册，验证码将发送到邮箱', 'success')
            return redirect(url_for('auth.reset_password', email=email))
    return render_template('forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = _normal_email(request.values.get('email'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 8 or password != request.form.get('confirm_password'):
            flash('密码至少 8 位，且两次输入必须一致', 'danger')
        else:
            ok, error = _verify_code(email, 'reset_password', request.form.get('code'))
            account = Account.query.filter_by(email=email).first()
            if ok and account:
                account.password_hash = generate_password_hash(password)
                db.session.commit()
                flash('密码已重置，请使用新密码登录', 'success')
                return redirect(url_for('auth.login'))
            flash(error or '重置失败，请重试', 'danger')
    return render_template('reset_password.html', email=email)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
