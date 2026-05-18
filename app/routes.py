import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import case, func, or_

from . import db
from .email_utils import send_email
from .models import (
    RESERVATION_DURATION_LABELS,
    DiningTable,
    Notification,
    Reservation,
    Restaurant,
    User,
)


main_bp = Blueprint("main", __name__)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ACTIVE_RESERVATION_STATUSES = ("pending", "confirmed")
STATUS_LABELS = {
    "pending": "Очікує",
    "confirmed": "Підтверджено",
    "rejected": "Відхилено",
    "cancelled_by_user": "Скасовано користувачем",
}
RESTAURANT_STATUS_LABELS = {
    "not_sent": "Очікує надсилання в ресторан",
    "sent": "Запит надіслано ресторану",
    "approved": "Ресторан погодив заявку",
    "rejected": "Ресторан відхилив заявку",
}
ACTIVITY_STATUS_LABELS = {
    "active": "Активне",
    "completed": "Завершене",
    "inactive": "Неактивне",
}
RESERVATION_DURATION_OPTIONS = tuple(RESERVATION_DURATION_LABELS.items())
SLOT_STEP_MINUTES = 15
INVALID_BOOKING_TIME_MESSAGE = "Неможливо створити бронювання на обраний час"

LOGIN_MAX_ATTEMPTS = 3
LOGIN_LOCK_SECONDS = 60

try:
    APP_TIMEZONE = ZoneInfo("Europe/Kyiv")
except Exception:
    APP_TIMEZONE = timezone(timedelta(hours=3))


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Увійдіть як адміністратор, щоб продовжити.", "warning")
            return redirect(url_for("admin.admin_login"))
        if not current_user.is_admin:
            flash("У вас немає доступу до адмін-панелі.", "danger")
            return redirect(url_for("main.home"))
        return view(*args, **kwargs)

    return wrapped_view


def parse_reservation_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def parse_reservation_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def parse_duration_minutes(value):
    if not value:
        return None
    try:
        duration_minutes = int(value)
    except (TypeError, ValueError):
        return None
    return duration_minutes if duration_minutes in RESERVATION_DURATION_LABELS else None


def parse_clock_input(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def normalize_categories(value):
    categories = []
    seen = set()

    for item in (value or "").split(","):
        cleaned = item.strip()
        normalized = cleaned.lower()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            categories.append(cleaned)

    return categories


def build_reservation_window(date_value, time_value, duration_value):
    reservation_date = parse_reservation_date(date_value)
    reservation_clock = parse_reservation_time(time_value)
    duration_minutes = parse_duration_minutes(duration_value)

    if not reservation_date or not reservation_clock:
        return None, None, duration_minutes

    start_datetime = datetime.combine(reservation_date, reservation_clock).replace(second=0, microsecond=0)
    if not duration_minutes:
        return start_datetime, None, duration_minutes

    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    return start_datetime, end_datetime, duration_minutes


def local_now():
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None, second=0, microsecond=0)


def reservation_uses_valid_slot_step(start_datetime):
    if not start_datetime:
        return False
    return (
        start_datetime.second == 0
        and start_datetime.microsecond == 0
        and start_datetime.minute % SLOT_STEP_MINUTES == 0
    )


def get_restaurant_bounds(restaurant, reservation_date, duration_minutes):
    opening_datetime = datetime.combine(reservation_date, restaurant.opening_time)
    closing_datetime = datetime.combine(reservation_date, restaurant.closing_time)
    latest_start = closing_datetime - timedelta(minutes=duration_minutes)
    return opening_datetime, closing_datetime, latest_start


def reservation_window_is_allowed(restaurant, start_datetime, end_datetime):
    if not restaurant or not start_datetime or not end_datetime:
        return False
    if not reservation_uses_valid_slot_step(start_datetime):
        return False

    opening_datetime, closing_datetime, _latest_start = get_restaurant_bounds(
        restaurant,
        start_datetime.date(),
        int((end_datetime - start_datetime).total_seconds() // 60),
    )
    now_value = local_now()

    if start_datetime < now_value:
        return False
    if start_datetime < opening_datetime:
        return False
    if end_datetime > closing_datetime:
        return False
    return True


def get_dynamic_booking_bounds(restaurant, reservation_date, duration_minutes):
    opening_datetime, closing_datetime, latest_start = get_restaurant_bounds(
        restaurant,
        reservation_date,
        duration_minutes,
    )
    min_start = opening_datetime
    today_local = local_now()
    if reservation_date == today_local.date():
        min_start = max(min_start, today_local)

    if min_start > latest_start:
        return None, None
    return min_start, latest_start


def build_public_url(endpoint, **values):
    public_base_url = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    relative_url = url_for(endpoint, _external=False, **values)
    if public_base_url:
        return f"{public_base_url}{relative_url}"
    return url_for(endpoint, _external=True, **values)


def format_event_datetime(value):
    if not value:
        return ""
    return value.strftime("%d.%m.%Y %H:%M")


def format_countdown_label(seconds):
    total_seconds = max(0, int(seconds or 0))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{remaining_seconds:02d}"


def get_login_lock_state(email, session_key):
    if not email:
        return None, 0

    user = User.query.filter_by(email=email).first()
    if not user:
        session.pop(session_key, None)
        return None, 0

    if user.ensure_login_lock_freshness():
        db.session.commit()
        session.pop(session_key, None)
        return user, 0

    if user.is_login_locked:
        session[session_key] = user.email
        return user, user.login_lock_remaining_seconds

    session.pop(session_key, None)
    return user, 0


def build_login_page_context(session_key, form_email=""):
    lock_email = form_email or session.get(session_key, "")
    _locked_user, lock_seconds = get_login_lock_state(lock_email, session_key)
    return {
        "form_email": lock_email,
        "login_locked": lock_seconds > 0,
        "login_lock_seconds": lock_seconds,
        "login_lock_timer_label": format_countdown_label(lock_seconds),
    }


def build_restaurant_request_text(reservation, approve_url, reject_url):
    return "\n".join(
        [
            "Нове погодження бронювання YourSeat",
            "",
            f"Ресторан: {reservation.restaurant.name}",
            f"Ім'я користувача: {reservation.user.full_name}",
            f"Email користувача: {reservation.user.email}",
            f"Дата бронювання: {reservation.reservation_time.strftime('%d.%m.%Y')}",
            f"Час початку: {reservation.reservation_time.strftime('%H:%M')}",
            f"Час завершення: {reservation.resolved_end_datetime.strftime('%H:%M')}",
            f"Тривалість: {reservation.duration_label}",
            f"Столик: {reservation.table.table_number}",
            f"Кількість гостей: {reservation.guests_count}",
            "",
            f"Підтвердити: {approve_url}",
            f"Відхилити: {reject_url}",
        ]
    )


def build_restaurant_cancellation_text(reservation):
    lines = [
        "Бронювання скасовано користувачем",
        "",
        "Користувач скасував заявку на бронювання.",
        "",
        f"Ресторан: {reservation.restaurant.name}",
        f"Ім'я користувача: {reservation.user.full_name}",
        f"Email користувача: {reservation.user.email}",
        f"Дата: {reservation.reservation_time.strftime('%d.%m.%Y')}",
        f"Час: {reservation.interval_label}",
        f"Тривалість: {reservation.duration_label}",
        f"Столик: {reservation.table.table_number}",
        f"Кількість гостей: {reservation.guests_count}",
    ]
    if reservation.special_request:
        lines.append(f"Додаткові побажання: {reservation.special_request}")
    return "\n".join(lines)


def build_user_notification_payload(reservation):
    return {
        "title": "Бронювання підтверджено",
        "message": (
            f"Ваше бронювання в ресторані {reservation.restaurant.name}, "
            f"столик {reservation.table.table_number}, "
            f"з {reservation.reservation_time.strftime('%H:%M')} до {reservation.resolved_end_datetime.strftime('%H:%M')} "
            f"{reservation.reservation_time.strftime('%d.%m.%Y')} підтверджено."
        ),
    }


def ensure_confirmation_notification(reservation):
    if reservation.notification is not None:
        return reservation.notification

    payload = build_user_notification_payload(reservation)
    notification = Notification(
        user_id=reservation.user_id,
        reservation_id=reservation.id,
        title=payload["title"],
        message=payload["message"],
        is_read=False,
    )
    db.session.add(notification)
    reservation.notification = notification
    return notification


def send_restaurant_approval_request(reservation):
    recipient = current_app.config.get("RESTAURANT_NOTIFICATION_EMAIL")
    approve_url = build_public_url(
        "main.restaurant_response",
        token=reservation.restaurant_token,
        decision="approve",
    )
    reject_url = build_public_url(
        "main.restaurant_response",
        token=reservation.restaurant_token,
        decision="reject",
    )
    logo_cid = "yourseat-logo-header"
    logo_path = Path(current_app.root_path) / "static" / "img" / "yourseat-logo-header.png"

    html_body = render_template(
        "emails/restaurant_request.html",
        reservation=reservation,
        approve_url=approve_url,
        reject_url=reject_url,
        logo_cid=logo_cid,
    )
    text_body = build_restaurant_request_text(reservation, approve_url, reject_url)
    subject = f"YourSeat: погодження бронювання для {reservation.restaurant.name}"

    return send_email(
        recipient=recipient,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        inline_images=[{"cid": logo_cid, "path": str(logo_path)}],
    )


def send_restaurant_cancellation_notice(reservation):
    recipient = current_app.config.get("RESTAURANT_NOTIFICATION_EMAIL")
    logo_cid = "yourseat-logo-header"
    logo_path = Path(current_app.root_path) / "static" / "img" / "yourseat-logo-header.png"

    html_body = render_template(
        "emails/restaurant_cancellation_notice.html",
        reservation=reservation,
        logo_cid=logo_cid,
    )
    text_body = build_restaurant_cancellation_text(reservation)
    subject = f"YourSeat: бронювання скасовано користувачем для {reservation.restaurant.name}"

    return send_email(
        recipient=recipient,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        inline_images=[{"cid": logo_cid, "path": str(logo_path)}],
    )


def get_conflicted_table_ids(restaurant_id, start_datetime, end_datetime, exclude_reservation_id=None):
    if not start_datetime or not end_datetime:
        return set()

    query = Reservation.query.filter(
        Reservation.restaurant_id == restaurant_id,
        Reservation.reservation_time < end_datetime,
        Reservation.end_datetime > start_datetime,
        Reservation.end_datetime > local_now(),
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
    )

    if exclude_reservation_id is not None:
        query = query.filter(Reservation.id != exclude_reservation_id)

    return {table_id for (table_id,) in query.with_entities(Reservation.table_id).all()}


def render_restaurant_detail(restaurant, selected_start=None, selected_end=None, selected_duration=None, form_data=None):
    window_valid = True
    if selected_start and selected_end:
        window_valid = reservation_window_is_allowed(restaurant, selected_start, selected_end)

    booked_table_ids = (
        get_conflicted_table_ids(restaurant.id, selected_start, selected_end)
        if selected_start and selected_end and window_valid
        else set()
    )
    available_tables = [
        table
        for table in restaurant.tables
        if table.is_active
        and (
            not selected_start
            or not selected_end
            or (window_valid and table.id not in booked_table_ids)
        )
    ]
    if selected_start and selected_end and not window_valid:
        available_tables = []

    return render_template(
        "restaurants/detail.html",
        restaurant=restaurant,
        selected_start=selected_start,
        selected_end=selected_end,
        selected_duration=selected_duration,
        booked_table_ids=booked_table_ids,
        available_tables=available_tables,
        form_data=form_data or {},
        status_labels=STATUS_LABELS,
        duration_options=RESERVATION_DURATION_OPTIONS,
        duration_labels=RESERVATION_DURATION_LABELS,
        current_local_iso=local_now().strftime("%Y-%m-%dT%H:%M"),
    )


@main_bp.route("/")
def home():
    featured_restaurants = Restaurant.query.order_by(Restaurant.name.asc()).limit(3).all()
    return render_template("home.html", featured_restaurants=featured_restaurants)


@main_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "main.home"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if len(full_name) < 3:
            flash("Вкажіть ім'я довжиною щонайменше 3 символи.", "danger")
        elif "@" not in email or "." not in email:
            flash("Вкажіть коректну електронну адресу.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Користувач із такою поштою вже існує.", "danger")
        elif len(password) < 6:
            flash("Пароль повинен містити щонайменше 6 символів.", "danger")
        elif password != password_confirm:
            flash("Підтвердження пароля не збігається.", "danger")
        else:
            user = User(full_name=full_name, email=email, is_admin=False)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Реєстрація успішна. Ласкаво просимо до YourSeat.", "success")
            return redirect(url_for("main.home"))

    return render_template("auth/register.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "main.home"))

    session_key = "user_login_lock_email"
    page_context = build_login_page_context(session_key)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        page_context = build_login_page_context(session_key, email)

        user, lock_seconds = get_login_lock_state(email, session_key)
        if lock_seconds > 0:
            flash("Забагато невдалих спроб. Спробуйте через 1 хвилину", "danger")
        elif not user or not user.check_password(password):
            if user:
                user.register_failed_login_attempt(
                    max_attempts=LOGIN_MAX_ATTEMPTS,
                    lock_seconds=LOGIN_LOCK_SECONDS,
                )
                db.session.commit()
                page_context = build_login_page_context(session_key, email)
                if user.is_login_locked:
                    flash("Забагато невдалих спроб. Спробуйте через 1 хвилину", "danger")
                else:
                    flash("Невірна електронна адреса або пароль.", "danger")
            else:
                flash("Невірна електронна адреса або пароль.", "danger")
        elif user.is_admin:
            user.reset_login_attempts()
            db.session.commit()
            session.pop(session_key, None)
            flash("Для адміністратора використайте окремий вхід.", "warning")
            return redirect(url_for("admin.admin_login"))
        else:
            user.reset_login_attempts()
            db.session.commit()
            session.pop(session_key, None)
            login_user(user)
            flash("Вхід виконано успішно.", "success")
            return redirect(url_for("main.home"))

    return render_template("auth/login.html", **page_context)


@main_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Сесію завершено.", "info")
    return redirect(url_for("main.home"))


@main_bp.route("/restaurants")
def restaurants():
    query = request.args.get("q", "").strip()
    restaurants_query = Restaurant.query.order_by(Restaurant.name.asc())
    if query:
        search = f"%{query}%"
        restaurants_query = restaurants_query.filter(
            or_(
                Restaurant.name.ilike(search),
                Restaurant.cuisine.ilike(search),
                Restaurant.categories.ilike(search),
                Restaurant.address.ilike(search),
            )
        )
    restaurants_list = restaurants_query.all()
    return render_template("restaurants/list.html", restaurants=restaurants_list, query=query)


@main_bp.route("/restaurants/<int:restaurant_id>", methods=["GET", "POST"])
def restaurant_detail(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    selected_start, selected_end, selected_duration = build_reservation_window(
        request.values.get("reservation_date", ""),
        request.values.get("reservation_time", ""),
        request.values.get("duration_minutes", "120"),
    )
    form_data = {
        "table_id": request.form.get("table_id", ""),
        "reservation_date": request.form.get("reservation_date", request.args.get("reservation_date", "")),
        "reservation_time": request.form.get("reservation_time", request.args.get("reservation_time", "")),
        "duration_minutes": request.form.get("duration_minutes", request.args.get("duration_minutes", "120")),
        "guests_count": request.form.get("guests_count", ""),
        "special_request": request.form.get("special_request", ""),
    }

    if request.method == "POST":
        if not current_user.is_authenticated:
            flash("Для бронювання потрібно увійти в систему.", "warning")
            return redirect(url_for("main.login"))
        if current_user.is_admin:
            flash("Адміністратор не створює бронювання як користувач.", "warning")
            return redirect(url_for("admin.dashboard"))

        table_id = request.form.get("table_id", "").strip()
        guests_value = request.form.get("guests_count", "").strip()
        special_request = request.form.get("special_request", "").strip()

        table = DiningTable.query.filter_by(id=table_id, restaurant_id=restaurant.id).first()

        if not selected_start:
            flash("Оберіть коректну дату та час бронювання.", "danger")
        elif not selected_duration or not selected_end:
            flash("Оберіть тривалість бронювання: 1.5, 2, 2.5 або 3 години.", "danger")
        elif not reservation_window_is_allowed(restaurant, selected_start, selected_end):
            flash(INVALID_BOOKING_TIME_MESSAGE, "danger")
        elif not table or not table.is_active:
            flash("Оберіть доступний столик.", "danger")
        elif not guests_value.isdigit() or int(guests_value) < 1:
            flash("Вкажіть коректну кількість гостей.", "danger")
        else:
            guests_count = int(guests_value)
            if guests_count > table.seats:
                flash(
                    f"Обраний столик розрахований максимум на {table.seats} гостей.",
                    "danger",
                )
            elif table.id in get_conflicted_table_ids(restaurant.id, selected_start, selected_end):
                flash("Цей столик уже заброньований на обраний час.", "danger")
            else:
                reservation = Reservation(
                    user_id=current_user.id,
                    restaurant_id=restaurant.id,
                    table_id=table.id,
                    reservation_time=selected_start,
                    duration_minutes=selected_duration,
                    end_datetime=selected_end,
                    guests_count=guests_count,
                    status="pending",
                    restaurant_status="not_sent",
                    restaurant_token=secrets.token_urlsafe(32),
                    special_request=special_request[:255] or None,
                )
                db.session.add(reservation)
                db.session.commit()
                flash(
                    "Заявку на бронювання створено. Вона очікує надсилання в ресторан і фінальне рішення адміністратора.",
                    "success",
                )
                return redirect(url_for("main.my_reservations"))

    return render_restaurant_detail(
        restaurant,
        selected_start=selected_start,
        selected_end=selected_end,
        selected_duration=selected_duration,
        form_data=form_data,
    )


@main_bp.route("/my-reservations")
@login_required
def my_reservations():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    now_value = local_now()
    reservations = (
        Reservation.query.filter_by(user_id=current_user.id)
        .order_by(Reservation.reservation_time.desc())
        .all()
    )
    active_reservations = sorted(
        [
            reservation
            for reservation in reservations
            if reservation.status in ACTIVE_RESERVATION_STATUSES
            and reservation.resolved_end_datetime >= now_value
        ],
        key=lambda reservation: reservation.reservation_time,
    )
    inactive_reservations = [
        reservation
        for reservation in reservations
        if reservation not in active_reservations
    ]
    return render_template(
        "my_reservations.html",
        reservations=reservations,
        active_reservations=active_reservations,
        inactive_reservations=inactive_reservations,
        status_labels=STATUS_LABELS,
        restaurant_status_labels=RESTAURANT_STATUS_LABELS,
        activity_status_labels=ACTIVITY_STATUS_LABELS,
    )


@main_bp.route("/my-reservations/<int:reservation_id>/cancel", methods=["POST"])
@login_required
def cancel_reservation(reservation_id):
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    reservation = Reservation.query.filter_by(id=reservation_id, user_id=current_user.id).first_or_404()

    if reservation.status == "cancelled_by_user":
        flash("Це бронювання вже було скасоване.", "warning")
        return redirect(url_for("main.my_reservations"))

    if reservation.status == "rejected" or reservation.activity_status == "completed":
        flash("Скасувати це бронювання вже неможливо.", "danger")
        return redirect(url_for("main.my_reservations"))

    if not reservation.can_cancel_by_user:
        flash("Скасувати бронювання можна лише не пізніше ніж за 5 хвилин до початку.", "danger")
        return redirect(url_for("main.my_reservations"))

    reservation.status = "cancelled_by_user"
    reservation.cancelled_at = datetime.utcnow()
    db.session.commit()

    flash("Бронювання скасовано користувачем.", "success")
    return redirect(url_for("main.my_reservations"))


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()

        if len(full_name) < 3:
            flash("Вкажіть ім'я довжиною щонайменше 3 символи.", "danger")
        else:
            current_user.full_name = full_name
            db.session.commit()
            flash("Ім'я в профілі оновлено.", "success")
            return redirect(url_for("main.profile"))

    latest_notification = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .first()
    )
    upcoming_reservation = (
        Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            Reservation.end_datetime >= local_now(),
        )
        .order_by(Reservation.reservation_time.asc())
        .first()
    )

    return render_template(
        "profile.html",
        latest_notification=latest_notification,
        upcoming_reservation=upcoming_reservation,
        status_labels=STATUS_LABELS,
        restaurant_status_labels=RESTAURANT_STATUS_LABELS,
        activity_status_labels=ACTIVITY_STATUS_LABELS,
    )


@main_bp.route("/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    if current_user.is_admin:
        return jsonify({"ok": False, "message": "Недоступно для адміністратора."}), 403

    unread_notifications = (
        Notification.query.filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .all()
    )

    marked_ids = []
    if unread_notifications:
        read_timestamp = datetime.utcnow()
        for notification in unread_notifications:
            notification.is_read = True
            notification.read_at = read_timestamp
            marked_ids.append(notification.id)
        db.session.commit()

    return jsonify({"ok": True, "marked_ids": marked_ids, "unread_count": 0})


@main_bp.route("/restaurant-response/<string:token>/<string:decision>")
def restaurant_response(token, decision):
    if decision not in {"approve", "reject"}:
        abort(404)

    reservation = Reservation.query.filter_by(restaurant_token=token).first_or_404()
    target_status = "approved" if decision == "approve" else "rejected"
    page_state = "success" if target_status == "approved" else "danger"

    if reservation.status == "cancelled_by_user":
        return render_template(
            "restaurant_response.html",
            reservation=reservation,
            title="Заявку вже скасовано користувачем",
            message="Користувач уже скасував це бронювання, тому відповідь ресторану більше не потрібна.",
            page_state="warning",
            action_label=STATUS_LABELS["cancelled_by_user"],
        )

    if reservation.status != "pending":
        return render_template(
            "restaurant_response.html",
            reservation=reservation,
            title="Заявка вже фінально опрацьована",
            message="Фінальний статус для цього бронювання вже визначено адміністратором, тому змінити рішення більше не можна.",
            page_state="info",
            action_label=RESTAURANT_STATUS_LABELS.get(reservation.restaurant_status, "Відповідь зафіксовано"),
        )

    if reservation.restaurant_status in {"approved", "rejected"}:
        return render_template(
            "restaurant_response.html",
            reservation=reservation,
            title="Відповідь ресторану вже зафіксовано",
            message="Для цієї заявки відповідь від ресторану вже збережена. Адміністратор бачить актуальний статус у панелі керування.",
            page_state="info",
            action_label=RESTAURANT_STATUS_LABELS[reservation.restaurant_status],
        )

    if reservation.restaurant_status != "sent":
        return render_template(
            "restaurant_response.html",
            reservation=reservation,
            title="Посилання ще не активоване",
            message="Для цієї заявки запит ресторану ще не був надісланий або посилання стало неактуальним.",
            page_state="warning",
            action_label=RESTAURANT_STATUS_LABELS.get(reservation.restaurant_status, "Недоступно"),
        )

    reservation.restaurant_status = target_status
    reservation.restaurant_responded_at = datetime.utcnow()
    db.session.commit()

    return render_template(
        "restaurant_response.html",
        reservation=reservation,
        title="Дякуємо, відповідь збережено",
        message=(
            "Ресторан погодив заявку. Тепер адміністратор може фінально підтвердити бронювання для користувача."
            if target_status == "approved"
            else "Ресторан відхилив заявку. Адміністратор побачить це рішення і зможе фінально відхилити бронювання."
        ),
        page_state=page_state,
        action_label=RESTAURANT_STATUS_LABELS[target_status],
    )


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    session_key = "admin_login_lock_email"
    page_context = build_login_page_context(session_key)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        page_context = build_login_page_context(session_key, email)

        user, lock_seconds = get_login_lock_state(email, session_key)
        if lock_seconds > 0:
            flash("Забагато невдалих спроб. Спробуйте через 1 хвилину", "danger")
        elif user and user.check_password(password) and not user.is_admin:
            user.reset_login_attempts()
            db.session.commit()
            session.pop(session_key, None)
            flash("Для звичайного користувача використайте стандартну форму входу.", "warning")
        elif not user or not user.check_password(password):
            if user:
                user.register_failed_login_attempt(
                    max_attempts=LOGIN_MAX_ATTEMPTS,
                    lock_seconds=LOGIN_LOCK_SECONDS,
                )
                db.session.commit()
                page_context = build_login_page_context(session_key, email)
                if user.is_login_locked:
                    flash("Забагато невдалих спроб. Спробуйте через 1 хвилину", "danger")
                else:
                    flash("Адміністративний вхід не виконано. Перевірте дані.", "danger")
            else:
                flash("Адміністративний вхід не виконано. Перевірте дані.", "danger")
        else:
            user.reset_login_attempts()
            db.session.commit()
            session.pop(session_key, None)
            login_user(user)
            flash("Вхід адміністратора виконано успішно.", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template("auth/admin_login.html", **page_context)


@admin_bp.route("/")
@admin_required
def dashboard():
    restaurants = Restaurant.query.order_by(Restaurant.name.asc()).all()
    tables = (
        DiningTable.query.join(Restaurant)
        .order_by(Restaurant.name.asc(), DiningTable.table_number.asc())
        .all()
    )
    users = User.query.order_by(User.created_at.desc()).all()
    reservation_last_event_at = func.coalesce(
        Reservation.updated_at,
        Reservation.cancelled_at,
        Reservation.restaurant_responded_at,
        Reservation.restaurant_email_sent_at,
        Reservation.created_at,
    )
    reservations = (
        Reservation.query.join(Restaurant)
        .order_by(
            case(
                (Reservation.status == "pending", 0),
                else_=1,
            ),
            case(
                (
                    (Reservation.status == "pending") & (Reservation.restaurant_status == "not_sent"),
                    0,
                ),
                (
                    (Reservation.status == "pending") & (Reservation.restaurant_status == "sent"),
                    1,
                ),
                (
                    (Reservation.status == "pending") & (Reservation.restaurant_status == "approved"),
                    2,
                ),
                (
                    (Reservation.status == "pending") & (Reservation.restaurant_status == "rejected"),
                    3,
                ),
                else_=4,
            ),
            case(
                (Reservation.status == "pending", Reservation.reservation_time),
                else_=None,
            ).asc(),
            reservation_last_event_at.desc(),
        )
        .all()
    )

    stats = {
        "users": User.query.filter_by(is_admin=False).count(),
        "restaurants": Restaurant.query.count(),
        "tables": DiningTable.query.count(),
        "pending_reservations": Reservation.query.filter_by(status="pending").count(),
    }

    return render_template(
        "admin/dashboard.html",
        restaurants=restaurants,
        tables=tables,
        users=users,
        reservations=reservations,
        stats=stats,
        status_labels=STATUS_LABELS,
        restaurant_status_labels=RESTAURANT_STATUS_LABELS,
    )


@admin_bp.route("/reservations/<int:reservation_id>/send-request", methods=["POST"])
@admin_required
def send_request_to_restaurant(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)

    if not reservation.can_send_to_restaurant:
        flash("Для цієї заявки запит у ресторан уже надсилали або вона вже опрацьована.", "warning")
        return redirect(url_for("admin.dashboard", _anchor="reservations"))

    if not reservation.restaurant_token:
        reservation.restaurant_token = secrets.token_urlsafe(32)

    delivery_result = send_restaurant_approval_request(reservation)
    reservation.restaurant_status = "sent"
    reservation.restaurant_email_sent_at = datetime.utcnow()
    db.session.commit()

    flash(delivery_result.message, "success" if delivery_result.sent else "warning")
    return redirect(url_for("admin.dashboard", _anchor="reservations"))


@admin_bp.route("/reservations/<int:reservation_id>/notify-cancellation", methods=["POST"])
@admin_required
def notify_restaurant_about_cancellation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)

    if not reservation.can_notify_restaurant_about_cancellation:
        flash("Для цієї заявки повідомлення про скасування вже надіслано або воно не потрібне.", "warning")
        return redirect(url_for("admin.dashboard", _anchor="reservations"))

    delivery_result = send_restaurant_cancellation_notice(reservation)
    if delivery_result.sent:
        reservation.cancellation_email_sent_at = datetime.utcnow()
        db.session.commit()

    flash(delivery_result.message, "success" if delivery_result.sent else "warning")
    return redirect(url_for("admin.dashboard", _anchor="reservations"))


@admin_bp.route("/reservations/<int:reservation_id>/status", methods=["POST"])
@admin_required
def update_reservation_status(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    new_status = request.form.get("status", "").strip()

    if new_status not in {"confirmed", "rejected"}:
        abort(400)

    if reservation.status != "pending":
        flash("Фінальне рішення для цієї заявки вже прийнято.", "warning")
        return redirect(url_for("admin.dashboard", _anchor="reservations"))

    if new_status == "confirmed":
        if reservation.restaurant_status != "approved":
            flash("Неможливо фінально підтвердити заявку, поки ресторан її не погодив.", "danger")
            return redirect(url_for("admin.dashboard", _anchor="reservations"))

        conflict_ids = get_conflicted_table_ids(
            reservation.restaurant_id,
            reservation.reservation_time,
            reservation.resolved_end_datetime,
            exclude_reservation_id=reservation.id,
        )
        if reservation.table_id in conflict_ids:
            flash("Не вдалося підтвердити бронювання: цей часовий інтервал уже зайнятий.", "danger")
            return redirect(url_for("admin.dashboard", _anchor="reservations"))
        if not reservation_window_is_allowed(
            reservation.restaurant,
            reservation.reservation_time,
            reservation.resolved_end_datetime,
        ):
            flash(INVALID_BOOKING_TIME_MESSAGE, "danger")
            return redirect(url_for("admin.dashboard", _anchor="reservations"))
    else:
        if not reservation.restaurant_decision_ready:
            flash("Фінально відхилити можна лише після відповіді ресторану.", "danger")
            return redirect(url_for("admin.dashboard", _anchor="reservations"))

    reservation.status = new_status
    if new_status == "confirmed":
        ensure_confirmation_notification(reservation)
    db.session.commit()
    flash("Фінальний статус заявки оновлено.", "success")
    return redirect(url_for("admin.dashboard", _anchor="reservations"))


@admin_bp.route("/restaurants/create", methods=["POST"])
@admin_required
def create_restaurant():
    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    cuisine = request.form.get("cuisine", "").strip()
    categories = normalize_categories(request.form.get("categories", ""))
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    maps_url = request.form.get("maps_url", "").strip()
    opening_time_value = request.form.get("opening_time", "").strip()
    closing_time_value = request.form.get("closing_time", "").strip()
    phone = request.form.get("phone", "").strip()
    opening_time = parse_clock_input(opening_time_value)
    closing_time = parse_clock_input(closing_time_value)

    if not all([name, address, cuisine, description, image_url, maps_url, phone]) or not categories:
        flash("Заповніть усі поля для створення ресторану.", "danger")
    elif not opening_time or not closing_time or opening_time >= closing_time:
        flash("Вкажіть коректний графік роботи ресторану.", "danger")
    else:
        if opening_time.strftime("%H:%M") <= "10:00" and "сніданки" not in {item.lower() for item in categories}:
            categories.append("Сніданки")
        restaurant = Restaurant(
            name=name,
            address=address,
            cuisine=cuisine,
            categories=", ".join(categories),
            description=description,
            image_url=image_url,
            maps_url=maps_url,
            open_hours=f"{opening_time.strftime('%H:%M')} - {closing_time.strftime('%H:%M')}",
            opening_time=opening_time,
            closing_time=closing_time,
            phone=phone,
        )
        db.session.add(restaurant)
        db.session.commit()
        flash("Ресторан додано.", "success")

    return redirect(url_for("admin.dashboard", _anchor="restaurants"))


@admin_bp.route("/restaurants/<int:restaurant_id>/update", methods=["POST"])
@admin_required
def update_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)

    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    cuisine = request.form.get("cuisine", "").strip()
    categories = normalize_categories(request.form.get("categories", ""))
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    maps_url = request.form.get("maps_url", "").strip()
    opening_time_value = request.form.get("opening_time", "").strip()
    closing_time_value = request.form.get("closing_time", "").strip()
    phone = request.form.get("phone", "").strip()
    opening_time = parse_clock_input(opening_time_value)
    closing_time = parse_clock_input(closing_time_value)

    if not all([name, address, cuisine, description, image_url, maps_url, phone]) or not categories:
        flash("Усі поля ресторану мають бути заповнені.", "danger")
    elif not opening_time or not closing_time or opening_time >= closing_time:
        flash("Вкажіть коректний графік роботи ресторану.", "danger")
    else:
        if opening_time.strftime("%H:%M") <= "10:00" and "сніданки" not in {item.lower() for item in categories}:
            categories.append("Сніданки")
        restaurant.name = name
        restaurant.address = address
        restaurant.cuisine = cuisine
        restaurant.categories = ", ".join(categories)
        restaurant.description = description
        restaurant.image_url = image_url
        restaurant.maps_url = maps_url
        restaurant.open_hours = f"{opening_time.strftime('%H:%M')} - {closing_time.strftime('%H:%M')}"
        restaurant.opening_time = opening_time
        restaurant.closing_time = closing_time
        restaurant.phone = phone
        db.session.commit()
        flash("Інформацію про ресторан оновлено.", "success")

    return redirect(url_for("admin.dashboard", _anchor="restaurants"))


@admin_bp.route("/restaurants/<int:restaurant_id>/delete", methods=["POST"])
@admin_required
def delete_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    if restaurant.reservations:
        flash("Ресторан не можна видалити, поки в нього є заявки на бронювання.", "danger")
    elif restaurant.tables:
        flash("Спочатку видаліть або деактивуйте столики цього ресторану.", "danger")
    else:
        db.session.delete(restaurant)
        db.session.commit()
        flash("Ресторан видалено.", "info")
    return redirect(url_for("admin.dashboard", _anchor="restaurants"))


@admin_bp.route("/tables/create", methods=["POST"])
@admin_required
def create_table():
    restaurant_id = request.form.get("restaurant_id", "").strip()
    table_number = request.form.get("table_number", "").strip()
    seats = request.form.get("seats", "").strip()
    location = request.form.get("location", "").strip()
    is_active = request.form.get("is_active") == "on"

    restaurant = Restaurant.query.filter_by(id=restaurant_id).first()
    existing = None
    if restaurant and table_number:
        existing = DiningTable.query.filter_by(
            restaurant_id=restaurant.id,
            table_number=table_number,
        ).first()

    if not restaurant:
        flash("Оберіть ресторан для столика.", "danger")
    elif not table_number:
        flash("Вкажіть номер столика.", "danger")
    elif not seats.isdigit() or int(seats) < 1:
        flash("Кількість місць повинна бути більшою за 0.", "danger")
    elif not location:
        flash("Вкажіть розташування столика.", "danger")
    elif existing:
        flash("Столик із таким номером уже існує в цьому ресторані.", "danger")
    else:
        db.session.add(
            DiningTable(
                restaurant_id=restaurant.id,
                table_number=table_number,
                seats=int(seats),
                location=location,
                is_active=is_active,
            )
        )
        db.session.commit()
        flash("Столик додано.", "success")

    return redirect(url_for("admin.dashboard", _anchor="tables"))


@admin_bp.route("/tables/<int:table_id>/update", methods=["POST"])
@admin_required
def update_table(table_id):
    table = DiningTable.query.get_or_404(table_id)

    table_number = request.form.get("table_number", "").strip()
    seats = request.form.get("seats", "").strip()
    location = request.form.get("location", "").strip()
    is_active = request.form.get("is_active") == "on"

    existing = DiningTable.query.filter(
        DiningTable.restaurant_id == table.restaurant_id,
        DiningTable.table_number == table_number,
        DiningTable.id != table.id,
    ).first()

    if not table_number:
        flash("Вкажіть номер столика.", "danger")
    elif not seats.isdigit() or int(seats) < 1:
        flash("Кількість місць повинна бути більшою за 0.", "danger")
    elif not location:
        flash("Вкажіть розташування столика.", "danger")
    elif existing:
        flash("Столик із таким номером уже існує в цьому ресторані.", "danger")
    else:
        table.table_number = table_number
        table.seats = int(seats)
        table.location = location
        table.is_active = is_active
        db.session.commit()
        flash("Столик оновлено.", "success")

    return redirect(url_for("admin.dashboard", _anchor="tables"))


@admin_bp.route("/tables/<int:table_id>/delete", methods=["POST"])
@admin_required
def delete_table(table_id):
    table = DiningTable.query.get_or_404(table_id)
    if table.reservations:
        flash("Столик не можна видалити, поки він має історію бронювань.", "danger")
    else:
        db.session.delete(table)
        db.session.commit()
        flash("Столик видалено.", "info")
    return redirect(url_for("admin.dashboard", _anchor="tables"))
