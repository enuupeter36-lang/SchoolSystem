import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pandas as pd
import qrcode
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import A6
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or "supersecretkey"

DATABASE_URL = os.getenv("DATABASE_URL")

# -------------------------
# DATABASE CONNECTION
# -------------------------
def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ✅ CREATE USERS TABLE (if not exists)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            must_change_password BOOLEAN DEFAULT FALSE
        )
    """)

    # ✅ ENSURE COLUMN EXISTS (for old databases)
    cur.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE
    """)

    conn.commit()
    conn.close()

# -------------------------
# AUTO CREATE ONE-TIME ADMIN
# -------------------------
def create_default_admin():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE role='super'")
    existing = cur.fetchone()

    if existing:
        conn.close()
        return

    username = "Lolachatsss@gmail.com"
    temp_password = os.getenv("ADMIN_TEMP_PASSWORD", "Temp@1234")

    password_hash = generate_password_hash(temp_password)

    cur.execute("""
        INSERT INTO users (username, password_hash, role, must_change_password)
        VALUES (%s, %s, 'super', TRUE)
    """, (username, password_hash))

    conn.commit()
    conn.close()

    print("✅ One-time admin created")
    print(f"Username: {username}")
    print(f"Temp Password: {temp_password}")

# Run on startup
init_db()
create_default_admin()

# -------------------------
# LOGIN DECORATORS
# -------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'super':
            flash("Only main admin can access this page.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------
# AUTH ROUTES
# -------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            # 🚨 FORCE PASSWORD CHANGE
            if user.get('must_change_password'):
                flash("Please change your password first.", "warning")
                return redirect(url_for('change_password'))

            flash("Logged in successfully!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "danger")
            return redirect(url_for('login'))

    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        new_password = request.form['new_password']

        conn = get_connection()
        cur = conn.cursor()

        new_hash = generate_password_hash(new_password)

        cur.execute("""
            UPDATE users 
            SET password_hash=%s, must_change_password=FALSE
            WHERE id=%s
        """, (new_hash, session['user_id']))

        conn.commit()
        conn.close()

        flash("Password changed successfully!", "success")
        return redirect(url_for('dashboard'))

    return render_template("change_password.html")

@app.route('/add-coadmin', methods=['GET', 'POST'])
@login_required
@super_admin_required
def add_coadmin():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS count FROM users WHERE role='admin'")
    count = cur.fetchone()['count']
    conn.close()

    if count >= 1:
        flash("Co-admin already exists. Only one allowed.", "warning")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = generate_password_hash(password)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password) VALUES (%s, %s, 'admin', FALSE)",
            (username, password_hash)
        )
        conn.commit()
        conn.close()

        flash("Co-admin added successfully!", "success")
        return redirect(url_for('dashboard'))

    return render_template("add_coadmin.html")

# -------------------------
# DASHBOARD
# -------------------------
@app.route('/')
@login_required
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_connection()
    cur = conn.cursor()

    # 🚨 BLOCK ACCESS IF PASSWORD NOT CHANGED
    cur.execute("SELECT must_change_password FROM users WHERE id=%s", (session['user_id'],))
    user = cur.fetchone()
    if user['must_change_password']:
        conn.close()
        return redirect(url_for('change_password'))

    cur.execute("SELECT COUNT(*) AS total FROM students")
    total = cur.fetchone()['total']

    cur.execute("SELECT class, COUNT(*) AS count FROM students GROUP BY class")
    class_data = cur.fetchall()

    cur.execute("SELECT gender, COUNT(*) AS count FROM students GROUP BY gender")
    gender_data = cur.fetchall()

    conn.close()

    return render_template("dashboard.html",
                           total_students=total,
                           class_data=class_data,
                           gender_data=gender_data)

# -------------------------
# STUDENT MANAGEMENT (UNCHANGED)
# -------------------------
@app.route('/students')
@login_required
def students():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template("students.html", students=data)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO students (admission, first_name, last_name, gender, dob, class, stream, parent, phone, photo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            request.form['admission'],
            request.form['first_name'],
            request.form['last_name'],
            request.form['gender'],
            request.form['dob'],
            request.form['class'],
            request.form['stream'],
            request.form['parent'],
            request.form['phone'],
            request.form['photo']
        ))
        conn.commit()
        conn.close()
        return redirect('/students')
    return render_template("add_student.html")

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)