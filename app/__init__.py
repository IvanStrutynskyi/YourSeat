import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask import Flask, render_template, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text


db = SQLAlchemy()
login_manager = LoginManager()

DEFAULT_RESTAURANT_NOTIFICATION_EMAIL = "restaurant@example.com"
DEFAULT_ADMIN_EMAIL = "admin@yourseat.local"
DEFAULT_ADMIN_PASSWORD = "admin12345"

RESTAURANT_RATINGS = {
    "Fabbrica": 4.6,
    "Urban Space 100": 4.6,
    "Delikacia": 4.7,
    "Fayno": 4.7,
    "Фамілія": 4.6,
    "Corassini": 4.6,
    "Terrace": 4.3,
    "Ambasada": 4.8,
    "Sapori": 4.8,
    "Десятка": 4.7,
}

IMAGE_OVERRIDES = {
    "Fabbrica": "img/restaurants/fabbrica-new.png",
    "Urban Space 100": "img/restaurants/urban-space-100.png",
    "Delikacia": "img/restaurants/delikacia-new.png",
    "Fayno": "img/restaurants/fauno-logo.png",
    "Фамілія": "img/restaurants/familiia-logo.png",
    "Corassini": "img/restaurants/corassini-logo.png",
    "Terrace": "img/restaurants/terrace-logo.png",
    "Ambasada": "img/restaurants/ambasada-logo.png",
    "Sapori": "img/restaurants/sapori-logo.png",
    "Десятка": "img/restaurants/desiatka-logo.png",
}

TEXT_LOGO_OVERRIDES = {
    "Fabbrica": "img/reservation-logos/fabbrica-text-logo.png",
    "Urban Space 100": "img/reservation-logos/urban-space-100-text-logo.png",
    "Delikacia": "img/reservation-logos/delikacia-text-logo.png",
    "Fayno": "img/reservation-logos/fayno-text-logo.png",
    "Р¤Р°РјС–Р»С–СЏ": "img/reservation-logos/familiia-text-logo.png",
    "Corassini": "img/reservation-logos/corassini-text-logo.png",
    "Terrace": "img/reservation-logos/terrace-text-logo.png",
    "Ambasada": "img/reservation-logos/ambasada-text-logo.png",
    "Sapori": "img/reservation-logos/sapori-text-logo.png",
    "Р”РµСЃСЏС‚РєР°": "img/reservation-logos/desiatka-text-logo.png",
}

RESTAURANT_RATING_SLUGS = {
    "fabbrica": 4.6,
    "urban-space-100": 4.6,
    "delikacia": 4.7,
    "fayno": 4.7,
    "familiia": 4.6,
    "corassini": 4.6,
    "terrace": 4.3,
    "ambasada": 4.8,
    "sapori": 4.8,
    "desiatka": 4.7,
}

IMAGE_OVERRIDE_SLUGS = {
    "fabbrica": "img/restaurants/fabbrica-new.png",
    "urban-space-100": "img/restaurants/urban-space-100.png",
    "delikacia": "img/restaurants/delikacia-new.png",
    "fayno": "img/restaurants/fauno-logo.png",
    "familiia": "img/restaurants/familiia-logo.png",
    "corassini": "img/restaurants/corassini-logo.png",
    "terrace": "img/restaurants/terrace-logo.png",
    "ambasada": "img/restaurants/ambasada-logo.png",
    "sapori": "img/restaurants/sapori-logo.png",
    "desiatka": "img/restaurants/desiatka-logo.png",
}

TEXT_LOGO_OVERRIDE_SLUGS = {
    "fabbrica": "img/reservation-logos/fabbrica-text-logo.png",
    "urban-space-100": "img/reservation-logos/urban-space-100-text-logo.png",
    "delikacia": "img/reservation-logos/delikacia-text-logo.png",
    "fayno": "img/reservation-logos/fayno-text-logo.png",
    "familiia": "img/reservation-logos/familiia-text-logo.png",
    "corassini": "img/reservation-logos/corassini-text-logo.png",
    "terrace": "img/reservation-logos/terrace-text-logo.png",
    "ambasada": "img/reservation-logos/ambasada-text-logo.png",
    "sapori": "img/reservation-logos/sapori-text-logo.png",
    "desiatka": "img/reservation-logos/desiatka-text-logo.png",
}

RESTAURANT_NAME_ALIASES = {
    "fauno": "fayno",
    "fayno": "fayno",
    "файно": "fayno",
    "фамілія": "familiia",
    "десятка": "desiatka",
    "urban space 100": "urban-space-100",
}

TABLE_LAYOUT_SPECS = (
    {"seats": 2, "location": "Перший ряд, ліворуч"},
    {"seats": 4, "location": "Перший ряд, центр"},
    {"seats": 6, "location": "Перший ряд, центр"},
    {"seats": 2, "location": "Перший ряд, праворуч"},
    {"seats": 4, "location": "Другий ряд, ліворуч"},
    {"seats": 6, "location": "Другий ряд, центр"},
    {"seats": 2, "location": "Другий ряд, центр"},
    {"seats": 4, "location": "Другий ряд, праворуч"},
    {"seats": 6, "location": "Третій ряд, ліворуч"},
    {"seats": 2, "location": "Третій ряд, центр"},
    {"seats": 4, "location": "Третій ряд, центр"},
    {"seats": 6, "location": "Третій ряд, праворуч"},
)

BREAKFAST_THRESHOLD = "10:00"

RESTAURANT_SEED_DATA = (
    {
        "name": "Fabbrica",
        "address": "вул. Вірменська, 1",
        "cuisine": "Італійська кухня",
        "categories": "Італійська кухня, Авторська кухня, Сніданки",
        "description": "Стильний ресторан з відкритою кухнею, пастою, піцою та затишною атмосферою для вечірніх зустрічей.",
        "image_url": "/static/img/restaurants/fabbrica-new.png",
        "maps_url": "https://www.google.com/maps/search/Fabbrica+Ivano-Frankivsk",
        "opening_time": "09:00",
        "closing_time": "22:30",
        "phone": "+380 50 111 22 33",
    },
    {
        "name": "Urban Space 100",
        "address": "вул. Грушевського, 19",
        "cuisine": "Європейська кухня",
        "categories": "Європейська кухня, Сніданки",
        "description": "Громадський ресторан із сучасним меню, сніданками та комфортним форматом для ділових і дружніх зустрічей.",
        "image_url": "/static/img/restaurants/urban-space-100.png",
        "maps_url": "https://www.google.com/maps/search/Urban+Space+100+Ivano-Frankivsk",
        "opening_time": "07:00",
        "closing_time": "22:00",
        "phone": "+380 50 222 33 44",
    },
    {
        "name": "Delikacia",
        "address": "вулиця Незалежності, 20",
        "cuisine": "Українська кухня",
        "categories": "Українська кухня, Сімейний ресторан, Сніданки",
        "description": "Затишний ресторан української кухні з домашньою подачею, комфортом для сімейних візитів і вечерь у центрі міста.",
        "image_url": "/static/img/restaurants/delikacia-new.png",
        "maps_url": "https://www.google.com/maps/search/Delikacia+Ivano-Frankivsk",
        "opening_time": "07:45",
        "closing_time": "21:00",
        "phone": "+380 50 333 44 55",
    },
    {
        "name": "Fayno",
        "address": "вулиця Сотника Мартинця, 4",
        "cuisine": "Українська кухня",
        "categories": "Українська кухня, Авторська кухня",
        "description": "Ресторан із сучасним поглядом на локальні смаки, якісною подачею та атмосферою для спокійної вечері.",
        "image_url": "/static/img/restaurants/fauno-logo.png",
        "maps_url": "https://www.google.com/maps/search/Fayno+Ivano-Frankivsk",
        "opening_time": "10:30",
        "closing_time": "22:00",
        "phone": "+380 50 444 55 66",
    },
    {
        "name": "Фамілія",
        "address": "вулиця Незалежності, 31",
        "cuisine": "Українська кухня",
        "categories": "Українська кухня, Сімейний ресторан",
        "description": "Просторий ресторан для сімейних обідів і зустрічей з акцентом на знайомі українські смаки та комфортний сервіс.",
        "image_url": "/static/img/restaurants/familiia-logo.png",
        "maps_url": "https://www.google.com/maps/search/Familia+Ivano-Frankivsk",
        "opening_time": "11:00",
        "closing_time": "22:00",
        "phone": "+380 50 555 66 77",
    },
    {
        "name": "Corassini",
        "address": "Бастіон Святого Андрея, Фортечний провулок, 1",
        "cuisine": "Європейська кухня",
        "categories": "Європейська кухня, Авторська кухня",
        "description": "Ресторан з виразним інтер'єром, спокійною атмосферою та меню для вечірніх бронювань і неспішних зустрічей.",
        "image_url": "/static/img/restaurants/corassini-logo.png",
        "maps_url": "https://www.google.com/maps/search/Corassini+Ivano-Frankivsk",
        "opening_time": "12:00",
        "closing_time": "23:00",
        "phone": "+380 50 666 77 88",
    },
    {
        "name": "Terrace",
        "address": "вулиця Михайла Грушевського, 3",
        "cuisine": "Європейська кухня",
        "categories": "Європейська кухня, Авторська кухня, Сніданки",
        "description": "Елегантний ресторан у центрі міста з просторим залом, вечірнім настроєм і зручним форматом для бронювання компанією.",
        "image_url": "/static/img/restaurants/terrace-logo.png",
        "maps_url": "https://www.google.com/maps/search/Terrace+Ivano-Frankivsk",
        "opening_time": "10:00",
        "closing_time": "22:00",
        "phone": "+380 50 777 88 99",
    },
    {
        "name": "Ambasada",
        "address": "площа Міцкевича, 4",
        "cuisine": "Європейська кухня",
        "categories": "Європейська кухня, Авторська кухня",
        "description": "Заклад із преміальною атмосферою, стриманим сервісом і зручним простором для важливих зустрічей і вечерь.",
        "image_url": "/static/img/restaurants/ambasada-logo.png",
        "maps_url": "https://www.google.com/maps/search/Ambasada+Ivano-Frankivsk",
        "opening_time": "11:00",
        "closing_time": "23:00",
        "phone": "+380 50 888 99 11",
    },
    {
        "name": "Sapori",
        "address": "вулиця Гетьмана Мазепи, 23",
        "cuisine": "Італійська кухня",
        "categories": "Італійська кухня, Авторська кухня",
        "description": "Камерний ресторан з теплим інтер'єром, італійськими акцентами та спокійним форматом для бронювань на вечір.",
        "image_url": "/static/img/restaurants/sapori-logo.png",
        "maps_url": "https://www.google.com/maps/search/Sapori+Ivano-Frankivsk",
        "opening_time": "12:00",
        "closing_time": "22:00",
        "phone": "+380 50 999 11 22",
    },
    {
        "name": "Десятка",
        "address": "вулиця Шашкевича, 4",
        "cuisine": "Українська кухня",
        "categories": "Українська кухня, Сімейний ресторан",
        "description": "Популярний ресторан народної кухні з великими порціями, живою атмосферою та зручним форматом для компаній.",
        "image_url": "/static/img/restaurants/desiatka-logo.png",
        "maps_url": "https://www.google.com/maps/search/Desyatka+Ivano-Frankivsk",
        "opening_time": "11:00",
        "closing_time": "22:00",
        "phone": "+380 50 123 45 67",
    },
)


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _default_database_uri(instance_path):
    return f"sqlite:///{Path(instance_path) / 'yourseat.db'}"


def _parse_clock(value):
    return datetime.strptime(value, "%H:%M").time()


def _format_open_hours(opening_time, closing_time):
    return f"{opening_time.strftime('%H:%M')} - {closing_time.strftime('%H:%M')}"


def _ensure_breakfast_category(categories, opening_time):
    category_list = []
    seen = set()

    for item in (categories or "").split(","):
        cleaned = item.strip()
        normalized = cleaned.lower()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            category_list.append(cleaned)

    if opening_time.strftime("%H:%M") <= BREAKFAST_THRESHOLD and "сніданки" not in seen:
        category_list.append("Сніданки")

    return ", ".join(category_list)


def _restaurant_slug(restaurant_name=None):
    raw_name = (restaurant_name or "").strip().lower()
    if not raw_name:
        return ""

    if raw_name in RESTAURANT_NAME_ALIASES:
        return RESTAURANT_NAME_ALIASES[raw_name]

    normalized = re.sub(r"[^a-z0-9]+", "-", raw_name).strip("-")
    return RESTAURANT_NAME_ALIASES.get(normalized, normalized)


def _resolve_image_url(image_url, restaurant_name=None):
    override = IMAGE_OVERRIDE_SLUGS.get(_restaurant_slug(restaurant_name))
    raw_value = (image_url or "").strip()

    if raw_value.startswith(("http://", "https://", "/static/")):
        return raw_value
    if raw_value.startswith("static/"):
        return url_for("static", filename=raw_value.removeprefix("static/"))
    if override:
        return url_for("static", filename=override)
    if raw_value:
        return raw_value
    return url_for("static", filename="img/restaurants/urban-space-100.png")


def _resolve_restaurant_text_logo(restaurant_name=None):
    logo_path = TEXT_LOGO_OVERRIDE_SLUGS.get(_restaurant_slug(restaurant_name))
    if logo_path:
        return url_for("static", filename=logo_path)
    return None


def _resolve_restaurant_rating(restaurant_name=None):
    return RESTAURANT_RATING_SLUGS.get(_restaurant_slug(restaurant_name), 4.6)


def _resolve_maps_embed_url(restaurant_name=None, address=None):
    query_parts = [part.strip() for part in [restaurant_name, address, "Ivano-Frankivsk"] if part and part.strip()]
    query = " ".join(query_parts)
    return f"https://www.google.com/maps?q={quote_plus(query)}&output=embed"


def _next_table_number(existing_numbers, start_index):
    candidate_index = start_index
    while True:
        candidate = f"T{candidate_index}"
        if candidate not in existing_numbers:
            return candidate
        candidate_index += 1


def ensure_database_schema():
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    with db.engine.begin() as connection:
        if "users" in tables:
            user_columns = {
                column["name"] for column in inspector.get_columns("users")
            }

            if "failed_attempts" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0")
                )
            if "last_failed_attempt" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN last_failed_attempt DATETIME")
                )
            if "lock_until" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN lock_until DATETIME")
                )

            connection.execute(
                text("UPDATE users SET failed_attempts = 0 WHERE failed_attempts IS NULL")
            )

        if "reservations" in tables:
            reservation_columns = {
                column["name"] for column in inspector.get_columns("reservations")
            }

            if "duration_minutes" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 120")
                )
            if "end_datetime" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN end_datetime DATETIME")
                )
            if "restaurant_status" not in reservation_columns:
                connection.execute(
                    text(
                        "ALTER TABLE reservations ADD COLUMN restaurant_status VARCHAR(20) "
                        "NOT NULL DEFAULT 'not_sent'"
                    )
                )
            if "restaurant_token" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN restaurant_token VARCHAR(120)")
                )
            if "restaurant_email_sent_at" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN restaurant_email_sent_at DATETIME")
                )
            if "restaurant_responded_at" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN restaurant_responded_at DATETIME")
                )
            if "cancelled_at" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN cancelled_at DATETIME")
                )
            if "cancellation_email_sent_at" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN cancellation_email_sent_at DATETIME")
                )
            if "updated_at" not in reservation_columns:
                connection.execute(
                    text("ALTER TABLE reservations ADD COLUMN updated_at DATETIME")
                )

            connection.execute(
                text("UPDATE reservations SET duration_minutes = 120 WHERE duration_minutes IS NULL")
            )
            connection.execute(
                text(
                    "UPDATE reservations "
                    "SET end_datetime = datetime(reservation_time, '+120 minutes') "
                    "WHERE end_datetime IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE reservations "
                    "SET restaurant_status = 'not_sent' "
                    "WHERE restaurant_status IS NULL OR trim(restaurant_status) = ''"
                )
            )
            connection.execute(
                text(
                    "UPDATE reservations "
                    "SET updated_at = COALESCE(updated_at, cancelled_at, restaurant_responded_at, restaurant_email_sent_at, created_at) "
                    "WHERE updated_at IS NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_reservations_end_datetime "
                    "ON reservations (end_datetime)"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_restaurant_token "
                    "ON reservations (restaurant_token)"
                )
            )

            reservation_create_sql = (
                connection.execute(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'table' AND name = 'reservations'"
                    )
                ).scalar()
                or ""
            )
            needs_reservations_rebuild = (
                db.engine.dialect.name == "sqlite"
                and (
                    "cancelled_by_user" not in reservation_create_sql
                    or "ck_restaurant_status" not in reservation_create_sql
                    or "cancelled_at" not in reservation_create_sql
                    or "cancellation_email_sent_at" not in reservation_create_sql
                )
            )

            if needs_reservations_rebuild:
                connection.execute(text("DROP TABLE IF EXISTS reservations__new"))
                connection.execute(
                    text(
                        """
                        CREATE TABLE reservations__new (
                            id INTEGER NOT NULL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            restaurant_id INTEGER NOT NULL,
                            table_id INTEGER NOT NULL,
                            reservation_time DATETIME NOT NULL,
                            duration_minutes INTEGER NOT NULL DEFAULT 120,
                            end_datetime DATETIME NOT NULL,
                            guests_count INTEGER NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            restaurant_status VARCHAR(20) NOT NULL DEFAULT 'not_sent',
                            restaurant_token VARCHAR(120),
                            restaurant_email_sent_at DATETIME,
                            restaurant_responded_at DATETIME,
                            cancelled_at DATETIME,
                            cancellation_email_sent_at DATETIME,
                            special_request VARCHAR(255),
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            CONSTRAINT ck_reservation_status CHECK (
                                status IN ('pending', 'confirmed', 'rejected', 'cancelled_by_user')
                            ),
                            CONSTRAINT ck_restaurant_status CHECK (
                                restaurant_status IN ('not_sent', 'sent', 'approved', 'rejected')
                            ),
                            FOREIGN KEY(user_id) REFERENCES users (id),
                            FOREIGN KEY(restaurant_id) REFERENCES restaurants (id),
                            FOREIGN KEY(table_id) REFERENCES tables (id)
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO reservations__new (
                            id, user_id, restaurant_id, table_id, reservation_time,
                            duration_minutes, end_datetime, guests_count, status,
                            restaurant_status, restaurant_token, restaurant_email_sent_at,
                            restaurant_responded_at, cancelled_at, cancellation_email_sent_at,
                            special_request, created_at, updated_at
                        )
                        SELECT
                            id,
                            user_id,
                            restaurant_id,
                            table_id,
                            reservation_time,
                            COALESCE(duration_minutes, 120),
                            COALESCE(end_datetime, datetime(reservation_time, '+120 minutes')),
                            guests_count,
                            CASE
                                WHEN status IN ('pending', 'confirmed', 'rejected', 'cancelled_by_user') THEN status
                                ELSE 'pending'
                            END,
                            CASE
                                WHEN restaurant_status IN ('not_sent', 'sent', 'approved', 'rejected') THEN restaurant_status
                                ELSE 'not_sent'
                            END,
                            restaurant_token,
                            restaurant_email_sent_at,
                            restaurant_responded_at,
                            cancelled_at,
                            cancellation_email_sent_at,
                            special_request,
                            created_at,
                            COALESCE(updated_at, cancelled_at, restaurant_responded_at, restaurant_email_sent_at, created_at)
                        FROM reservations
                        """
                    )
                )
                connection.execute(text("DROP TABLE reservations"))
                connection.execute(text("ALTER TABLE reservations__new RENAME TO reservations"))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_reservations_status ON reservations (status)")
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_reservations_restaurant_status "
                        "ON reservations (restaurant_status)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_reservations_reservation_time "
                        "ON reservations (reservation_time)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_reservations_end_datetime "
                        "ON reservations (end_datetime)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_restaurant_token "
                        "ON reservations (restaurant_token)"
                    )
                )

        if "restaurants" in tables:
            restaurant_columns = {
                column["name"] for column in inspector.get_columns("restaurants")
            }
            if "categories" not in restaurant_columns:
                connection.execute(
                    text("ALTER TABLE restaurants ADD COLUMN categories VARCHAR(255) NOT NULL DEFAULT ''")
                )
            connection.execute(
                text(
                    "UPDATE restaurants SET categories = cuisine "
                    "WHERE (categories IS NULL OR trim(categories) = '') "
                    "AND cuisine IS NOT NULL"
                )
            )
            if "opening_time" not in restaurant_columns:
                connection.execute(
                    text("ALTER TABLE restaurants ADD COLUMN opening_time TIME")
                )
            if "closing_time" not in restaurant_columns:
                connection.execute(
                    text("ALTER TABLE restaurants ADD COLUMN closing_time TIME")
                )
            if "maps_url" not in restaurant_columns:
                connection.execute(
                    text("ALTER TABLE restaurants ADD COLUMN maps_url VARCHAR(500) NOT NULL DEFAULT ''")
                )

        if "notifications" in tables:
            notification_columns = {
                column["name"] for column in inspector.get_columns("notifications")
            }
            if "is_read" not in notification_columns:
                connection.execute(
                    text("ALTER TABLE notifications ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0")
                )
            if "read_at" not in notification_columns:
                connection.execute(
                    text("ALTER TABLE notifications ADD COLUMN read_at DATETIME")
                )


def sync_notifications():
    from .models import Notification, Reservation

    confirmed_reservations = (
        Reservation.query.filter_by(status="confirmed")
        .order_by(Reservation.created_at.desc())
        .all()
    )

    for reservation in confirmed_reservations:
        if reservation.notification is not None:
            continue

        created_at = reservation.restaurant_responded_at or reservation.created_at
        notification = Notification(
            user_id=reservation.user_id,
            reservation_id=reservation.id,
            title="Бронювання підтверджено",
            message=(
                f"Ваше бронювання в ресторані {reservation.restaurant.name}, "
                f"столик {reservation.table.table_number}, "
                f"з {reservation.reservation_time.strftime('%H:%M')} до {reservation.resolved_end_datetime.strftime('%H:%M')} "
                f"{reservation.reservation_time.strftime('%d.%m.%Y')} підтверджено."
            ),
            is_read=False,
            created_at=created_at,
        )
        db.session.add(notification)

    db.session.commit()


def seed_data():
    from .models import DiningTable, Restaurant, User

    admin = User.query.filter_by(email=DEFAULT_ADMIN_EMAIL).first()
    if admin is None:
        admin = User(
            full_name="Адміністратор YourSeat",
            email=DEFAULT_ADMIN_EMAIL,
            is_admin=True,
        )
        admin.set_password(DEFAULT_ADMIN_PASSWORD)
        db.session.add(admin)

    restaurants_by_name = {
        restaurant.name: restaurant
        for restaurant in Restaurant.query.all()
    }

    legacy_restaurant = restaurants_by_name.get("PromBar")
    if legacy_restaurant is not None and not legacy_restaurant.reservations:
        db.session.delete(legacy_restaurant)
        restaurants_by_name.pop("PromBar", None)

    legacy_fauno = restaurants_by_name.get("Fauno")
    current_fayno = restaurants_by_name.get("Fayno")
    if legacy_fauno is not None and current_fayno is None:
        legacy_fauno.name = "Fayno"
        restaurants_by_name["Fayno"] = legacy_fauno
        restaurants_by_name.pop("Fauno", None)
    elif legacy_fauno is not None and current_fayno is not None and not legacy_fauno.reservations:
        db.session.delete(legacy_fauno)
        restaurants_by_name.pop("Fauno", None)

    for item in RESTAURANT_SEED_DATA:
        restaurant = restaurants_by_name.get(item["name"])
        is_new_restaurant = restaurant is None

        if restaurant is None:
            restaurant = Restaurant(name=item["name"])
            db.session.add(restaurant)
            restaurants_by_name[item["name"]] = restaurant

        restaurant.address = item["address"]
        restaurant.cuisine = item["cuisine"]
        opening_time = _parse_clock(item["opening_time"])
        closing_time = _parse_clock(item["closing_time"])
        restaurant.categories = _ensure_breakfast_category(item["categories"], opening_time)
        restaurant.description = item["description"]
        restaurant.image_url = item["image_url"]
        restaurant.maps_url = item["maps_url"]
        restaurant.opening_time = opening_time
        restaurant.closing_time = closing_time
        restaurant.open_hours = _format_open_hours(opening_time, closing_time)
        restaurant.phone = item["phone"]

        if is_new_restaurant:
            db.session.flush()

        existing_tables = sorted(
            restaurant.tables,
            key=lambda table: (table.id or 0, table.table_number),
        )
        existing_numbers = {table.table_number for table in existing_tables}

        for index, layout in enumerate(TABLE_LAYOUT_SPECS, start=1):
            if index <= len(existing_tables):
                table = existing_tables[index - 1]
            else:
                table = DiningTable(
                    restaurant=restaurant,
                    table_number=_next_table_number(existing_numbers, index),
                )
                existing_numbers.add(table.table_number)
                db.session.add(table)
                existing_tables.append(table)

            table.seats = layout["seats"]
            table.location = layout["location"]
            table.is_active = True

    db.session.commit()


def create_app():
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env")

    app = Flask(
        __name__,
        instance_path=str(base_dir / "instance"),
        instance_relative_config=False,
    )

    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "yourseat-secret-key"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", _default_database_uri(app.instance_path)),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PROJECT_NAME="YourSeat",
        SMTP_HOST=os.getenv("SMTP_HOST", "").strip(),
        SMTP_PORT=int(os.getenv("SMTP_PORT", "587")),
        SMTP_USERNAME=os.getenv("MAIL_USERNAME", os.getenv("SMTP_USERNAME", "")).strip(),
        SMTP_PASSWORD=os.getenv("MAIL_PASSWORD", os.getenv("SMTP_PASSWORD", "")),
        SMTP_USE_TLS=_as_bool(os.getenv("SMTP_USE_TLS", "1"), default=True),
        SMTP_USE_SSL=_as_bool(os.getenv("SMTP_USE_SSL", "0")),
        MAIL_FROM=os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_FROM", "noreply@yourseat.local")).strip(),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/"),
        RESTAURANT_NOTIFICATION_EMAIL=os.getenv(
            "RESTAURANT_NOTIFICATION_EMAIL",
            DEFAULT_RESTAURANT_NOTIFICATION_EMAIL,
        ).strip(),
    )

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"
    login_manager.login_message = "Увійдіть, щоб продовжити."
    login_manager.login_message_category = "warning"

    from .models import Notification, User
    from .routes import admin_bp, main_bp

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_global_context():
        user_notifications = []
        unread_notification_count = 0

        if current_user.is_authenticated and not getattr(current_user, "is_admin", False):
            user_notifications = (
                Notification.query.filter_by(user_id=current_user.id)
                .order_by(Notification.created_at.desc())
                .all()
            )
            unread_notification_count = sum(0 if notification.is_read else 1 for notification in user_notifications)

        return {
            "project_name": app.config["PROJECT_NAME"],
            "restaurant_image_url": lambda restaurant: _resolve_image_url(
                getattr(restaurant, "image_url", ""),
                getattr(restaurant, "name", ""),
            ),
            "restaurant_rating": lambda restaurant: _resolve_restaurant_rating(
                getattr(restaurant, "name", ""),
            ),
            "restaurant_text_logo_url": lambda restaurant: _resolve_restaurant_text_logo(
                getattr(restaurant, "name", ""),
            ),
            "restaurant_maps_embed_url": lambda restaurant: _resolve_maps_embed_url(
                getattr(restaurant, "name", ""),
                getattr(restaurant, "address", ""),
            ),
            "restaurant_address": lambda restaurant: getattr(restaurant, "address", ""),
            "user_notifications": user_notifications,
            "notification_unread_count": unread_notification_count,
        }

    @app.errorhandler(404)
    def not_found(_error):
        return (
            render_template(
                "error.html",
                error_code=404,
                error_message="Сторінку не знайдено.",
            ),
            404,
        )

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return (
            render_template(
                "error.html",
                error_code=500,
                error_message="Сталася внутрішня помилка сервера.",
            ),
            500,
        )

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        ensure_database_schema()
        seed_data()
        sync_notifications()

    return app
