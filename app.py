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
        old_password = request.form['old_password']
        new_password = request.form['new_password']

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
        user = cur.fetchone()

        if not check_password_hash(user['password_hash'], old_password):
            flash("Old password is incorrect!", "danger")
            conn.close()
            return redirect(url_for('change_password'))

        new_hash = generate_password_hash(new_password)
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, session['user_id']))
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
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
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
# STUDENT MANAGEMENT
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

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    conn = get_connection()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute("""
            UPDATE students SET
            admission=%s, first_name=%s, last_name=%s, gender=%s, dob=%s,
            class=%s, stream=%s, parent=%s, phone=%s, photo=%s
            WHERE id=%s
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
            request.form['photo'],
            id
        ))
        conn.commit()
        conn.close()
        return redirect('/students')

    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    conn.close()
    return render_template("edit_student.html", student=student)

@app.route('/delete/<int:id>')
@login_required
def delete_student(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect('/students')

# -------------------------
# ID CARD VIEW & PRINT
# -------------------------
@app.route('/id_card/<int:id>')
@login_required
def id_card(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    conn.close()
    return render_template("id_card.html", student=student)

@app.route('/print_all')
@login_required
def print_all():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    conn.close()
    return render_template("print_all.html", students=students)

# -------------------------
# EXPORT EXCEL
# -------------------------
@app.route('/export/excel')
@login_required
def export_excel():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM students", conn)
    conn.close()
    file_path = "students.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

# -------------------------
# EXPORT PDF (ID Cards Layout)
# -------------------------
@app.route('/export/pdf')
@login_required
def export_pdf():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    conn.close()

    doc = SimpleDocTemplate("students.pdf", pagesize=A6)
    styles = getSampleStyleSheet()
    elements = []

    for s in students:
        # STUDENT INFO
        elements.append(Paragraph(f"<b>{s['first_name']} {s['last_name']}</b>", styles['Title']))
        elements.append(Paragraph(f"Adm: {s['admission']}", styles['Normal']))
        elements.append(Paragraph(f"Class: {s['class']} {s['stream'] or ''}", styles['Normal']))

        # PHOTO
        photo_path = s['photo'] or "static/default.png"
        try:
            elements.append(Image(photo_path, width=80, height=100))
        except:
            pass

        # BARCODE
        barcode_path = f"static/barcodes/{s['admission']}.png"
        try:
            elements.append(Image(barcode_path, width=130, height=40))
        except:
            pass

        elements.append(Spacer(1, 20))

    doc.build(elements)
    return send_file("students.pdf", as_attachment=True)

# -------------------------
# QR CODE
# -------------------------
@app.route('/qr/<int:id>')
@login_required
def generate_qr(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    conn.close()

    data = f"{student['first_name']} {student['last_name']} - {student['class']}"
    img = qrcode.make(data)
    path = f"static/qrcodes/{student['admission']}.png"
    img.save(path)
    return send_file(path, mimetype='image/png')

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)