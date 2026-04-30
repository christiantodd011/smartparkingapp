from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import random
import os

app = Flask(__name__)
app.secret_key = "smart_parking_secret_key"

ADMIN_PASSWORD = "admin123"
USER_PASSWORD = "user123"
DECAL_PRICE = 75.00

parking_data = [
    {"lot": "Lot A", "open": 12, "total": 50},
    {"lot": "Lot B", "open": 5, "total": 40},
    {"lot": "Lot C", "open": 20, "total": 60}
]

def connect_db():
    return sqlite3.connect("database.db")

def add_column_if_missing(cursor, table, column, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [col[1] for col in cursor.fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

def generate_decal_number(user_id):
    return "NSU-" + user_id[-4:] + "-" + str(random.randint(1000, 9999))

def init_db():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            user_id TEXT PRIMARY KEY,
            user_type TEXT,
            full_name TEXT,
            phone TEXT,
            email TEXT,
            residence TEXT,
            decal_status TEXT DEFAULT 'No Decal',
            decal_number TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            plate TEXT,
            make TEXT,
            model TEXT,
            color TEXT,
            decal_number TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            reason TEXT,
            amount REAL,
            status TEXT DEFAULT 'Unpaid'
        )
    """)

    add_column_if_missing(cursor, "user_info", "user_type", "TEXT")
    add_column_if_missing(cursor, "user_info", "decal_status", "TEXT DEFAULT 'No Decal'")
    add_column_if_missing(cursor, "user_info", "decal_number", "TEXT")
    add_column_if_missing(cursor, "vehicles", "user_id", "TEXT")
    add_column_if_missing(cursor, "vehicles", "decal_number", "TEXT")
    add_column_if_missing(cursor, "tickets", "user_id", "TEXT")

    conn.commit()
    conn.close()

init_db()

def require_login():
    return "role" in session and "user" in session

@app.route("/")
def dashboard():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("dashboard.html", role=session["role"], user=session["user"])

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        role = request.form["role"].lower()
        password = request.form["password"]

        if role == "admin":
            if password != ADMIN_PASSWORD:
                error = "Invalid admin password."
                return render_template("login.html", error=error)

            session["user"] = "Admin Verified"
            session["role"] = "admin"
            session["user_id"] = "ADMIN"
            session["user_type"] = "Admin"

        else:
            user_id = request.form["user_id"].strip()

            if password != USER_PASSWORD:
                error = "Invalid user password."
                return render_template("login.html", error=error)

            if user_id == "":
                error = "ID is required."
                return render_template("login.html", error=error)

            session["user"] = f"{role.title()} Verified"
            session["role"] = "user"
            session["user_id"] = user_id
            session["user_type"] = role.title()

            conn = connect_db()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR IGNORE INTO user_info 
                (user_id, user_type, decal_status)
                VALUES (?, ?, 'No Decal')
            """, (user_id, role.title()))

            cursor.execute("""
                UPDATE user_info
                SET user_type=?
                WHERE user_id=?
            """, (role.title(), user_id))

            conn.commit()
            conn.close()

        return redirect(url_for("dashboard"))

    return render_template("login.html", error=error)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] == "admin":
        return redirect(url_for("admin"))

    user_id = session["user_id"]

    conn = connect_db()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE user_info
            SET full_name=?, phone=?, email=?, residence=?
            WHERE user_id=?
        """, (
            request.form["full_name"],
            request.form["phone"],
            request.form["email"],
            request.form["residence"],
            user_id
        ))
        conn.commit()

    cursor.execute("""
        SELECT user_id, user_type, full_name, phone, email, residence, decal_status, decal_number
        FROM user_info
        WHERE user_id=?
    """, (user_id,))
    user_data = cursor.fetchone()

    conn.close()

    return render_template("profile.html", user_data=user_data)

@app.route("/vehicles", methods=["GET", "POST"])
def vehicles():
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] == "admin":
        return redirect(url_for("admin"))

    user_id = session["user_id"]

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT decal_number FROM user_info WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    user_decal_number = result[0] if result and result[0] else ""

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO vehicles (user_id, plate, make, model, color, decal_number)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            request.form["plate"],
            request.form["make"],
            request.form["model"],
            request.form["color"],
            user_decal_number
        ))
        conn.commit()

    cursor.execute("""
        SELECT id, plate, make, model, color, decal_number
        FROM vehicles
        WHERE user_id=?
    """, (user_id,))
    vehicles_list = cursor.fetchall()

    conn.close()

    return render_template("vehicles.html", vehicles=vehicles_list)

@app.route("/delete_vehicle/<int:vehicle_id>")
def delete_vehicle(vehicle_id):
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] == "admin":
        return redirect(url_for("admin"))

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM vehicles WHERE id=? AND user_id=?",
        (vehicle_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("vehicles"))

@app.route("/buy_decal", methods=["GET", "POST"])
def buy_decal():
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] == "admin":
        return redirect(url_for("admin"))

    user_id = session["user_id"]

    if request.method == "GET":
        return render_template("purchase_decal.html")

    decal_number = generate_decal_number(user_id)

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE user_info
        SET decal_status='Purchased', decal_number=?
        WHERE user_id=?
    """, (decal_number, user_id))

    cursor.execute("""
        UPDATE vehicles
        SET decal_number=?
        WHERE user_id=?
    """, (decal_number, user_id))

    cursor.execute("""
        INSERT INTO tickets (user_id, reason, amount, status)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        "Parking Decal Purchase",
        DECAL_PRICE,
        "Paid"
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("tickets"))

@app.route("/pay_ticket/<int:ticket_id>", methods=["GET", "POST"])
def pay_ticket(ticket_id):
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] == "admin":
        return redirect(url_for("admin"))

    user_id = session["user_id"]

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, reason, amount, status
        FROM tickets
        WHERE id=? AND user_id=?
    """, (ticket_id, user_id))

    ticket = cursor.fetchone()

    if ticket is None:
        conn.close()
        return redirect(url_for("tickets"))

    if request.method == "POST":
        cursor.execute("""
            UPDATE tickets
            SET status='Paid'
            WHERE id=? AND user_id=?
        """, (ticket_id, user_id))

        conn.commit()
        conn.close()

        return redirect(url_for("tickets"))

    conn.close()

    return render_template("pay_ticket.html", ticket=ticket)

@app.route("/parking")
def parking():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("parking.html", lots=parking_data)

@app.route("/live_parking")
def live_parking():
    if not require_login():
        return redirect(url_for("login"))

    for lot in parking_data:
        lot["open"] = random.randint(0, lot["total"])

    return render_template("parking.html", lots=parking_data)

@app.route("/tickets")
def tickets():
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] == "admin":
        return redirect(url_for("admin"))

    user_id = session["user_id"]

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, reason, amount, status
        FROM tickets
        WHERE user_id=?
    """, (user_id,))
    ticket_list = cursor.fetchall()

    cursor.execute("""
        SELECT SUM(amount)
        FROM tickets
        WHERE user_id=? AND status='Unpaid'
    """, (user_id,))
    balance = cursor.fetchone()[0] or 0

    cursor.execute("""
        SELECT decal_status, decal_number
        FROM user_info
        WHERE user_id=?
    """, (user_id,))
    decal_result = cursor.fetchone()

    decal_status = decal_result[0] if decal_result else "No Decal"
    decal_number = decal_result[1] if decal_result else ""

    conn.close()

    return render_template(
        "tickets.html",
        tickets=ticket_list,
        balance=balance,
        decal_status=decal_status,
        decal_number=decal_number
    )

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not require_login():
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return "Access Denied: Admins only."

    search = request.args.get("search", "")

    conn = connect_db()
    cursor = conn.cursor()

    if request.method == "POST":
        action = request.form["action"]

        if action == "ticket":
            cursor.execute("""
                INSERT INTO tickets (user_id, reason, amount, status)
                VALUES (?, ?, ?, 'Unpaid')
            """, (
                request.form["user_id"],
                request.form["reason"],
                float(request.form["amount"])
            ))

        elif action == "decal":
            user_id = request.form["user_id"]
            decal_status = request.form["decal_status"]

            if decal_status == "Purchased":
                decal_number = generate_decal_number(user_id)

                cursor.execute("""
                    UPDATE user_info
                    SET decal_status='Purchased', decal_number=?
                    WHERE user_id=?
                """, (decal_number, user_id))

                cursor.execute("""
                    UPDATE vehicles
                    SET decal_number=?
                    WHERE user_id=?
                """, (decal_number, user_id))

            else:
                cursor.execute("""
                    UPDATE user_info
                    SET decal_status='No Decal', decal_number=NULL
                    WHERE user_id=?
                """, (user_id,))

                cursor.execute("""
                    UPDATE vehicles
                    SET decal_number=NULL
                    WHERE user_id=?
                """, (user_id,))

        elif action == "paid":
            cursor.execute("""
                UPDATE tickets
                SET status='Paid'
                WHERE id=?
            """, (request.form["ticket_id"],))

        conn.commit()

    cursor.execute("""
        SELECT 
            u.user_id,
            u.user_type,
            u.full_name,
            u.phone,
            u.email,
            u.residence,
            u.decal_status,
            u.decal_number,
            COUNT(DISTINCT v.id),
            COUNT(DISTINCT t.id),
            COALESCE(SUM(CASE WHEN t.status='Unpaid' THEN t.amount ELSE 0 END), 0)
        FROM user_info u
        LEFT JOIN vehicles v ON u.user_id = v.user_id
        LEFT JOIN tickets t ON u.user_id = t.user_id
        WHERE u.user_id LIKE ? OR u.full_name LIKE ? OR u.user_type LIKE ?
        GROUP BY u.user_id
    """, (f"%{search}%", f"%{search}%", f"%{search}%"))
    users = cursor.fetchall()

    cursor.execute("""
        SELECT id, user_id, reason, amount, status
        FROM tickets
        ORDER BY id DESC
    """)
    all_tickets = cursor.fetchall()

    cursor.execute("""
        SELECT user_id, plate, make, model, color, decal_number
        FROM vehicles
    """)
    all_vehicles = cursor.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        tickets=all_tickets,
        vehicles=all_vehicles,
        lots=parking_data,
        search=search
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)