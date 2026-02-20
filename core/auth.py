"""Auth and role decorators."""

from functools import wraps
from flask import abort, flash, redirect, session, url_for


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            current_role = session.get("role")
            allowed_roles = set(role) if isinstance(role, (list, tuple, set)) else {role}

            if current_role not in allowed_roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
