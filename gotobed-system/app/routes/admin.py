from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps

from ..models import db, Account, User, Log


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """装饰器：要求管理员权限"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('需要管理员权限才能访问此页面', 'danger')
            return redirect(url_for('users.user_list'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/accounts')
@admin_required
def account_management():
    """账号管理页面 - 显示所有管理员和普通用户"""
    # 获取所有账号
    accounts = Account.query.order_by(Account.created_at.desc()).all()

    # 为每个账号统计其拥有的查寝账号数量和最近状态
    account_stats = []
    for account in accounts:
        user_count = User.query.filter_by(owner_id=account.id).count()
        enabled_user_count = User.query.filter_by(owner_id=account.id, enabled=True).count()

        # 获取该账号下最近的查寝记录
        recent_logs = Log.query.join(User).filter(
            User.owner_id == account.id
        ).order_by(Log.executed_at.desc()).limit(10).all()

        success_count = sum(1 for log in recent_logs if log.status == 'success')
        success_rate = round(success_count / len(recent_logs) * 100) if recent_logs else 0

        account_stats.append({
            'account': account,
            'user_count': user_count,
            'enabled_user_count': enabled_user_count,
            'success_rate': success_rate,
            'last_activity': recent_logs[0].executed_at if recent_logs else None,
        })

    # 统计总览
    total_accounts = len(accounts)
    admin_accounts = sum(1 for acc in accounts if acc.role == 'admin')
    user_accounts = total_accounts - admin_accounts
    enabled_accounts = sum(1 for acc in accounts if acc.enabled)

    stats = {
        'total_accounts': total_accounts,
        'admin_accounts': admin_accounts,
        'user_accounts': user_accounts,
        'enabled_accounts': enabled_accounts,
        'disabled_accounts': total_accounts - enabled_accounts,
    }

    return render_template('admin/accounts.html', account_stats=account_stats, stats=stats)


@admin_bp.route('/accounts/<int:account_id>/toggle', methods=['POST'])
@admin_required
def account_toggle(account_id):
    """启用/禁用账号"""
    account = Account.query.get_or_404(account_id)

    # 不允许禁用自己
    if account.id == current_user.id:
        flash('不能禁用自己的账号', 'danger')
        return redirect(url_for('admin.account_management'))

    account.enabled = not account.enabled
    db.session.commit()

    status = '启用' if account.enabled else '禁用'
    flash(f'账号 {account.email} 已{status}', 'success')
    return redirect(url_for('admin.account_management'))


@admin_bp.route('/accounts/<int:account_id>/users')
@admin_required
def account_users(account_id):
    """查看某个账号下的所有查寝用户"""
    account = Account.query.get_or_404(account_id)
    users = User.query.filter_by(owner_id=account.id).order_by(User.created_at.desc()).all()

    # 为每个用户获取最近的日志
    user_details = []
    for user in users:
        last_log = user.last_log()
        user_details.append({
            'user': user,
            'last_log': last_log,
        })

    return render_template('admin/account_users.html', account=account, user_details=user_details)


@admin_bp.route('/accounts/<int:account_id>/delete', methods=['POST'])
@admin_required
def account_delete(account_id):
    """删除账号（包括其下所有查寝用户）"""
    account = Account.query.get_or_404(account_id)

    # 不允许删除自己
    if account.id == current_user.id:
        flash('不能删除自己的账号', 'danger')
        return redirect(url_for('admin.account_management'))

    # 如果要删除的是管理员，检查是否是最后一个管理员
    if account.role == 'admin':
        admin_count = Account.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash('不能删除最后一个管理员账号，系统至少需要保留一个管理员', 'danger')
            return redirect(url_for('admin.account_management'))

    # 删除该账号下的所有查寝用户（级联删除会自动处理日志）
    User.query.filter_by(owner_id=account.id).delete()

    email = account.email
    db.session.delete(account)
    db.session.commit()

    flash(f'账号 {email} 及其所有查寝用户已删除', 'success')
    return redirect(url_for('admin.account_management'))
