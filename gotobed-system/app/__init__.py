import os
from datetime import datetime
from flask import Flask
from flask_login import LoginManager
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
except ImportError:  # 未安装可选依赖时仍允许通过系统环境变量启动
    def load_dotenv(*args, **kwargs):
        return False

from .models import db, Account, User, BJT

login_manager = LoginManager()


def create_app():
    # 支持本地直接运行时自动读取 gotobed-system/.env，Docker 仍可通过 env_file 注入。
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
    app = Flask(__name__)

    # 数据目录（使用项目根目录，确保 Docker volume 挂载生效）
    data_dir = os.path.join(os.path.dirname(app.root_path), 'data')
    os.makedirs(data_dir, exist_ok=True)

    # 加载配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'sqlite:///' + os.path.join(data_dir, 'gotobed.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'admin123')
    app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL', os.environ.get('SMTP_USER', ''))
    app.config['FERNET_KEY'] = os.environ.get('FERNET_KEY', '')
    app.config['SMTP_HOST'] = os.environ.get('SMTP_HOST', 'smtp.qq.com')
    app.config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', '465'))
    app.config['SMTP_USER'] = os.environ.get('SMTP_USER', '')
    app.config['SMTP_PASS'] = os.environ.get('SMTP_PASS', '')

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # 注册蓝图
    from .routes import register_blueprints
    register_blueprints(app)

    # 创建数据库表
    with app.app_context():
        db.create_all()
        _upgrade_legacy_schema()
        _ensure_admin_account(app)

    # 初始化调度器（需在建表之后）
    from .scheduler import init_scheduler
    init_scheduler(app)

    return app


def _upgrade_legacy_schema():
    """为已有 SQLite 数据库补充新字段，避免升级后旧数据无法启动。"""
    inspector = inspect(db.engine)
    if 'users' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('users')}
    if 'owner_id' not in columns:
        db.session.execute(text('ALTER TABLE users ADD COLUMN owner_id INTEGER'))
        db.session.commit()
    if 'campus' not in columns:
        # 旧版本没有校区字段，这里按旧版账号规则迁移一次，之后由用户手动维护。
        db.session.execute(text("ALTER TABLE users ADD COLUMN campus VARCHAR(20) NOT NULL DEFAULT 'baiyun'"))
        current_year = datetime.now(BJT).year
        legacy_users = db.session.execute(text('SELECT id, username FROM users')).fetchall()
        for user_id, username in legacy_users:
            campus = 'baiyun'
            try:
                campus = 'huizhou' if int(str(username)[:4]) >= current_year else 'baiyun'
            except (TypeError, ValueError):
                pass
            db.session.execute(text('UPDATE users SET campus = :campus WHERE id = :user_id'),
                                {'campus': campus, 'user_id': user_id})
        db.session.commit()


def _ensure_admin_account(app):
    """首次启动时创建管理员，并接管旧版本中没有 owner_id 的查寝账号。"""
    admin_email = (app.config.get('ADMIN_EMAIL') or '').strip().lower()
    if not admin_email:
        return

    admin = Account.query.filter_by(email=admin_email).first()
    if not admin:
        admin = Account(
            email=admin_email,
            password_hash=generate_password_hash(app.config['ADMIN_PASSWORD']),
            email_verified_at=datetime.now(BJT),
            role='admin',
            enabled=True,
        )
        db.session.add(admin)
        db.session.flush()
    else:
        # 当前项目暂无独立的修改管理员密码页面，配置文件中的密码作为管理员密码来源。
        # 这样用户修改 .env 后重启服务即可生效，不会继续使用旧的密码哈希。
        if not admin.password_hash or not check_password_hash(admin.password_hash, app.config['ADMIN_PASSWORD']):
            admin.password_hash = generate_password_hash(app.config['ADMIN_PASSWORD'])

    # 迁移旧版创建的查寝账号，避免管理员升级后看不到原数据。
    User.query.filter(User.owner_id.is_(None)).update({'owner_id': admin.id}, synchronize_session=False)
    db.session.commit()
