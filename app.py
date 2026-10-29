from flask import Flask, render_template, request, redirect, url_for
import uuid
from db import get_connection

app = Flask(__name__)

@app.route("/")
def home():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT concert_id, title, artist, venue, city, concert_date
        FROM concerts
        WHERE is_active = TRUE
        ORDER BY concert_date
    """)

    concerts = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("index.html", concerts=concerts)


@app.route("/concert/<int:concert_id>")
def concert_details(concert_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM concerts WHERE concert_id = %s AND is_active = TRUE",
        (concert_id,)
    )
    concert = cursor.fetchone()

    if concert is None:
        cursor.close()
        connection.close()
        return "Concert not found", 404

    cursor.execute("""
        SELECT category_id, category_name, price, available_quantity
        FROM ticket_categories
        WHERE concert_id = %s AND available_quantity > 0
        ORDER BY price
    """, (concert_id,))

    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "concert_details.html",
        concert=concert,
        categories=categories
    )


@app.route("/book/<int:concert_id>", methods=["GET", "POST"])
def book_ticket(concert_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM concerts WHERE concert_id = %s AND is_active = TRUE",
            (concert_id,)
        )
        concert = cursor.fetchone()

        if concert is None:
            return "Concert not found", 404

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            category_id = request.form.get("category_id", type=int)
            quantity = request.form.get("quantity", type=int)

            if not full_name or not email or not category_id or not quantity:
                return "Please fill in all required fields.", 400

            if quantity < 1 or quantity > 10:
                return "You can book between 1 and 10 tickets.", 400

            cursor.execute("""
                SELECT category_id, category_name, price, available_quantity
                FROM ticket_categories
                WHERE category_id = %s AND concert_id = %s
                FOR UPDATE
            """, (category_id, concert_id))

            category = cursor.fetchone()

            if category is None:
                connection.rollback()
                return "Invalid ticket category.", 400

            if category["available_quantity"] < quantity:
                connection.rollback()
                return "Not enough tickets available.", 400

            cursor.execute(
                "SELECT user_id FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()

            if user:
                user_id = user["user_id"]
                cursor.execute("""
                    UPDATE users
                    SET full_name = %s, phone = %s
                    WHERE user_id = %s
                """, (full_name, phone or None, user_id))
            else:
                cursor.execute("""
                    INSERT INTO users (full_name, email, phone)
                    VALUES (%s, %s, %s)
                """, (full_name, email, phone or None))
                user_id = cursor.lastrowid

            total_amount = category["price"] * quantity
            booking_code = "CT-" + uuid.uuid4().hex[:10].upper()

            cursor.execute("""
                INSERT INTO bookings
                (booking_code, user_id, concert_id, category_id,
                 quantity, total_amount, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'CONFIRMED')
            """, (
                booking_code, user_id, concert_id, category_id,
                quantity, total_amount
            ))

            booking_id = cursor.lastrowid

            cursor.execute("""
                UPDATE ticket_categories
                SET available_quantity = available_quantity - %s
                WHERE category_id = %s
                  AND available_quantity >= %s
            """, (quantity, category_id, quantity))

            if cursor.rowcount != 1:
                connection.rollback()
                return "Tickets are no longer available. Please try again.", 409

            cursor.execute("""
                INSERT INTO payments
                (booking_id, amount, payment_method, payment_status)
                VALUES (%s, %s, 'DEMO', 'PENDING')
            """, (booking_id, total_amount))

            connection.commit()

            return render_template(
                "booking_success.html",
                booking_code=booking_code,
                concert=concert,
                category_name=category["category_name"],
                quantity=quantity,
                total_amount=total_amount
            )

        cursor.execute("""
            SELECT category_id, category_name, price, available_quantity
            FROM ticket_categories
            WHERE concert_id = %s AND available_quantity > 0
            ORDER BY price
        """, (concert_id,))

        categories = cursor.fetchall()

        return render_template(
            "booking.html",
            concert=concert,
            categories=categories
        )

    except Exception:
        connection.rollback()
        app.logger.exception("Ticket booking failed")
        return "Booking failed due to a server error. Please try again.", 500

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    app.run(debug=True)
