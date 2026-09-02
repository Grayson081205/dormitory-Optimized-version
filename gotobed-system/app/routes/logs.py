from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from ..models import db, Log, User

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/logs')
@login_required
def log_list():
    page = request.args.get('page', 1, type=int)
    user_id = request.args.get('user_id', type=int)
    per_page = 20

    query = Log.query.join(User).order_by(Log.executed_at.desc())
    if not current_user.is_admin:
        query = query.filter(User.owner_id == current_user.id)
    if user_id:
        query = query.filter_by(user_id=user_id)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users_query = User.query if current_user.is_admin else User.query.filter_by(owner_id=current_user.id)
    users = users_query.order_by(User.username).all()

    return render_template('logs/list.html',
                           logs=pagination.items,
                           pagination=pagination,
                           users=users,
                           selected_user_id=user_id)
