import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


RESERVATION_DURATION_LABELS = {
    90: "1.5 години",
    120: "2 години",
    150: "2.5 години",
    180: "3 години",
}

try:
    DISPLAY_TIMEZONE = ZoneInfo("Europe/Kyiv")
except Exception:
    DISPLAY_TIMEZONE = timezone(timedelta(hours=3))


def utc_now():
    return datetime.utcnow()


def format_system_datetime(value):
    if not value:
        return None

    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    localized_value = utc_value.astimezone(DISPLAY_TIMEZONE)
    return localized_value.strftime("%d.%m.%Y %H:%M")


def local_booking_now():
    return datetime.now(DISPLAY_TIMEZONE).replace(tzinfo=None, second=0, microsecond=0)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    last_failed_attempt = db.Column(db.DateTime)
    lock_until = db.Column(db.DateTime)

    reservations = db.relationship("Reservation", back_populates="user")
    notifications = db.relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_login_locked(self):
        return bool(self.lock_until and self.lock_until > utc_now())

    @property
    def login_lock_remaining_seconds(self):
        if not self.is_login_locked:
            return 0
        return max(0, math.ceil((self.lock_until - utc_now()).total_seconds()))

    def reset_login_attempts(self):
        self.failed_attempts = 0
        self.last_failed_attempt = None
        self.lock_until = None

    def register_failed_login_attempt(self, max_attempts=3, lock_seconds=60):
        self.failed_attempts = int(self.failed_attempts or 0) + 1
        self.last_failed_attempt = utc_now()
        if self.failed_attempts >= max_attempts:
            self.lock_until = utc_now() + timedelta(seconds=lock_seconds)

    def ensure_login_lock_freshness(self):
        if self.lock_until and self.lock_until <= utc_now():
            self.reset_login_attempts()
            return True
        return False

    @property
    def role_label(self):
        return "Адміністратор" if self.is_admin else "Користувач"

    @property
    def created_at_display(self):
        return format_system_datetime(self.created_at)


class Restaurant(db.Model):
    __tablename__ = "restaurants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    cuisine = db.Column(db.String(120), nullable=False)
    categories = db.Column(db.String(255), nullable=False, default="")
    description = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    maps_url = db.Column(db.String(500), nullable=False, default="")
    open_hours = db.Column(db.String(80), nullable=False)
    opening_time = db.Column(db.Time, nullable=False)
    closing_time = db.Column(db.Time, nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    tables = db.relationship(
        "DiningTable",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        order_by="DiningTable.table_number",
    )
    reservations = db.relationship("Reservation", back_populates="restaurant")

    @property
    def category_list(self):
        source = self.categories or self.cuisine or ""
        categories = []
        seen = set()

        for item in source.split(","):
            cleaned = item.strip()
            normalized = cleaned.lower()
            if cleaned and normalized not in seen:
                seen.add(normalized)
                categories.append(cleaned)

        if not categories and self.cuisine:
            return [self.cuisine]

        return categories


class DiningTable(db.Model):
    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    table_number = db.Column(db.String(20), nullable=False)
    seats = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="tables")
    reservations = db.relationship("Reservation", back_populates="table")

    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "table_number", name="uq_table_number_per_restaurant"),
    )


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey("tables.id"), nullable=False)
    reservation_time = db.Column(db.DateTime, nullable=False, index=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=120)
    end_datetime = db.Column(db.DateTime, nullable=False, index=True)
    guests_count = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    restaurant_status = db.Column(db.String(20), default="not_sent", nullable=False, index=True)
    restaurant_token = db.Column(db.String(120), unique=True, index=True)
    restaurant_email_sent_at = db.Column(db.DateTime)
    restaurant_responded_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancellation_email_sent_at = db.Column(db.DateTime)
    special_request = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = db.relationship("User", back_populates="reservations")
    restaurant = db.relationship("Restaurant", back_populates="reservations")
    table = db.relationship("DiningTable", back_populates="reservations")
    notification = db.relationship(
        "Notification",
        back_populates="reservation",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected', 'cancelled_by_user')",
            name="ck_reservation_status",
        ),
        db.CheckConstraint(
            "restaurant_status IN ('not_sent', 'sent', 'approved', 'rejected')",
            name="ck_restaurant_status",
        ),
    )

    @property
    def resolved_end_datetime(self):
        if self.end_datetime is not None:
            return self.end_datetime
        return self.reservation_time + timedelta(minutes=self.duration_minutes or 120)

    @property
    def duration_label(self):
        if self.duration_minutes in RESERVATION_DURATION_LABELS:
            return RESERVATION_DURATION_LABELS[self.duration_minutes]

        duration_hours = (self.duration_minutes or 0) / 60
        return f"{duration_hours:g} години"

    @property
    def interval_label(self):
        return f"{self.reservation_time.strftime('%H:%M')} - {self.resolved_end_datetime.strftime('%H:%M')}"

    @property
    def activity_status(self):
        if self.status in {"rejected", "cancelled_by_user"}:
            return "inactive"
        return "completed" if local_booking_now() > self.resolved_end_datetime else "active"

    @property
    def activity_status_label(self):
        if self.activity_status == "completed":
            return "Завершене"
        if self.activity_status == "inactive":
            return "Неактивне"
        return "Активне"

    @property
    def is_completed(self):
        return self.activity_status == "completed"

    @property
    def is_inactive(self):
        return self.activity_status != "active"

    @property
    def restaurant_decision_ready(self):
        return self.restaurant_status in {"approved", "rejected"}

    @property
    def is_cancelled_by_user(self):
        return self.status == "cancelled_by_user"

    @property
    def can_send_to_restaurant(self):
        return self.status == "pending" and self.restaurant_status == "not_sent"

    @property
    def can_finalize_confirmation(self):
        return self.status == "pending" and self.restaurant_status == "approved"

    @property
    def can_finalize_rejection(self):
        return self.status == "pending" and self.restaurant_status in {"approved", "rejected"}

    @property
    def cancellation_deadline(self):
        return self.reservation_time - timedelta(minutes=5)

    @property
    def can_cancel_by_user(self):
        if self.status not in {"pending", "confirmed"}:
            return False
        return local_booking_now() < self.cancellation_deadline

    @property
    def can_notify_restaurant_about_cancellation(self):
        return (
            self.status == "cancelled_by_user"
            and self.restaurant_status == "approved"
            and self.cancellation_email_sent_at is None
        )

    @property
    def restaurant_email_sent_at_display(self):
        return format_system_datetime(self.restaurant_email_sent_at)

    @property
    def restaurant_responded_at_display(self):
        return format_system_datetime(self.restaurant_responded_at)

    @property
    def cancelled_at_display(self):
        return format_system_datetime(self.cancelled_at)

    @property
    def cancellation_email_sent_at_display(self):
        return format_system_datetime(self.cancellation_email_sent_at)

    @property
    def user_progress_tone(self):
        if self.status == "cancelled_by_user":
            return "warning-soft"
        if self.status == "confirmed":
            return "success"
        if self.status == "rejected":
            return "danger"
        if self.restaurant_status == "approved":
            return "success-soft"
        if self.restaurant_status == "rejected":
            return "danger-soft"
        return "info"

    @property
    def user_progress_title(self):
        if self.status == "cancelled_by_user":
            return "Бронювання скасовано користувачем"
        if self.status == "confirmed":
            return "Бронювання підтверджено"
        if self.status == "rejected":
            return "Заявку відхилено"
        if self.restaurant_status == "approved":
            return "Ресторан уже погодив заявку"
        if self.restaurant_status == "rejected":
            return "Ресторан відхилив заявку"
        if self.restaurant_status == "sent":
            return "Запит уже надіслано ресторану"
        return "Заявку створено"

    @property
    def user_progress_message(self):
        if self.status == "cancelled_by_user":
            if self.restaurant_status == "approved":
                return (
                    "Ви скасували цю заявку після погодження рестораном. "
                    "Адміністратор побачить скасування і за потреби повідомить заклад окремим листом."
                )
            return (
                "Ви скасували це бронювання самостійно. "
                "Заявка лишається в історії, але більше не блокує столик у вибраному інтервалі."
            )
        if self.status == "confirmed":
            return (
                "Адміністратор фінально підтвердив бронювання. "
                "Можна орієнтуватися на обраний час і планувати візит."
            )
        if self.status == "rejected":
            if self.restaurant_status == "rejected":
                return (
                    "Ресторан не погодив це бронювання, тому заявка була фінально відхилена. "
                    "Спробуйте інший час або інший столик."
                )
            if self.restaurant_status == "approved":
                return (
                    "Ресторан погодив заявку, але адміністратор не зміг її фінально підтвердити. "
                    "Таке може статися, якщо інтервал уже став недоступним."
                )
            return (
                "Адміністратор фінально відхилив заявку. "
                "Можна спробувати повторити бронювання на інший час."
            )
        if self.restaurant_status == "approved":
            return (
                "Ресторан погодив заявку, тепер очікується фінальне підтвердження адміністратора."
            )
        if self.restaurant_status == "rejected":
            return (
                "Ресторан відхилив заявку. Адміністратор ще має зафіксувати фінальне рішення в системі."
            )
        if self.restaurant_status == "sent":
            return (
                "Заявку вже надіслано ресторану на погодження. "
                "Щойно відповідь надійде, статус оновиться тут."
            )
        return (
            "Заявку збережено в системі. Адміністратор ще не надіслав її ресторану для погодження."
        )


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey("reservations.id"), nullable=False, unique=True, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    user = db.relationship("User", back_populates="notifications")
    reservation = db.relationship("Reservation", back_populates="notification")

    @property
    def created_at_display(self):
        return format_system_datetime(self.created_at)

    @property
    def read_at_display(self):
        return format_system_datetime(self.read_at)
