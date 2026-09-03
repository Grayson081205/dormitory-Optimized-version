from datetime import datetime
from zoneinfo import ZoneInfo
import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# 北京时间
BJT = ZoneInfo('Asia/Shanghai')


class Account(UserMixin, db.Model):
    """网站登录账号。网站密码只保存哈希，不能反向解密。"""

    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String(20), nullable=False, default='user')
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(BJT))
    last_login_at = db.Column(db.DateTime, nullable=True)

    managed_users = db.relationship('User', backref='owner', lazy=True)

    @property
    def is_admin(self):
        return self.role == 'admin'


class EmailVerificationCode(db.Model):
    """注册和找回密码使用的一次性邮箱验证码。"""

    __tablename__ = 'email_verification_codes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(BJT))


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 兼容旧数据库，首次升级时该字段允许为空，孤立账号会归到管理员名下。
    owner_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    username = db.Column(db.Text, nullable=False)
    password_encrypted = db.Column(db.Text, nullable=False)
    principal = db.Column(db.Text, nullable=True)
    credential = db.Column(db.Text, nullable=True)
    email = db.Column(db.Text, nullable=True)
    # 查寝校区：baiyun（白云）或 huizhou（惠州）。
    campus = db.Column(db.String(20), nullable=False, default='baiyun')
    cron_times = db.Column(db.Text, nullable=False, default='["10 21 * * *"]')
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(BJT))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(BJT),
                           onupdate=lambda: datetime.now(BJT))

    logs = db.relationship('Log', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def get_cron_times(self) -> list:
        """获取 cron 时间列表"""
        try:
            return json.loads(self.cron_times)
        except (json.JSONDecodeError, TypeError):
            return ['10 21 * * *']

    def set_cron_times(self, times: list):
        """设置 cron 时间列表"""
        self.cron_times = json.dumps(times)

    def last_log(self):
        """获取最近一条执行日志"""
        return self.logs.order_by(Log.executed_at.desc()).first()

    def __repr__(self):
        return f'<User {self.username}>'


class Log(db.Model):
    __tablename__ = 'logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.Text, nullable=False)  # 'success' / 'failure'
    message = db.Column(db.Text, nullable=False)
    executed_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(BJT))

    def __repr__(self):
        return f'<Log {self.id} {self.status}>'
