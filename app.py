import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pandas as pd
from io import BytesIO

from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import A6
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or "secret"

DATABASE_URL = os.getenv("DATABASE_URL")

# -------------------------
# DB CONNECTION
# -------------------------
def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# -------------------------
# INIT DB
# -------------------------
def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'admin',
        must_change_password BOOLEAN DEFAULT FALSE
    )
    """)
    # Students table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        admission TEXT UNIQUE,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        dob DATE,
        class TEXT,
        stream TEXT,
        parent TEXT,
        phone TEXT,
        photo TEXT
    )
    """)
    conn.commit()
    conn.close()

# -------------------------
# DEFAULT ADMIN
# -------------------------
def create_default_admin():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE role='super'")
    if not cur.fetchone():
        cur.execute("""
        INSERT INTO users (username, password_hash, role, must_change_password)
        VALUES (%s, %s, 'super', TRUE)
        """, ("Lolachatsss@gmail.com", generate_password_hash("Temp@1234")))
    conn.commit()
    conn.close()

# -------------------------
# AUTH DECORATOR
# -------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

def must_change():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT must_change_password FROM users WHERE id=%s", (session['user_id'],))
    result = cur.fetchone()
    conn.close()
    return result['must_change_password']

# -------------------------
# LOGIN
# -------------------------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (request.form['username'],))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], request.form['password']):
            session['user_id'] = user['id']
            if user['must_change_password']:
                return redirect('/change-password')
            return redirect('/dashboard')
        flash("Invalid login")
    return render_template("login.html")

@app.route('/change-password', methods=['GET','POST'])
@login_required
def change_password():
    if request.method == 'POST':
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE users SET password_hash=%s, must_change_password=FALSE WHERE id=%s
        """, (generate_password_hash(request.form['new_password']), session['user_id']))
        conn.commit()
        conn.close()
        return redirect('/dashboard')
    return render_template("change_password.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# -------------------------
# idex
# -------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -------------------------
# DASHBOARD
# -------------------------
@app.route('/')
@login_required
def home():
    return redirect('/dashboard')

@app.route('/dashboard')
@login_required
def dashboard():
    if must_change():
        return redirect('/change-password')
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
# STUDENTS + SEARCH
# -------------------------
@app.route('/students')
@login_required
def students():
    conn = get_connection()
    cur = conn.cursor()
    search = request.args.get('search')
    class_filter = request.args.get('class')
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if search:
        query += " AND (first_name ILIKE %s OR last_name ILIKE %s OR admission ILIKE %s)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if class_filter:
        query += " AND class=%s"
        params.append(class_filter)
    query += " ORDER BY id DESC"
    cur.execute(query, params)
    students = cur.fetchall()
    conn.close()
    return render_template("students.html", students=students)

# -------------------------
# ADD STUDENT
# -------------------------
@app.route('/add', methods=['GET','POST'])
@login_required
def add_student():
    if request.method == 'POST':
        admission = request.form['admission']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        gender = request.form.get('gender')
        dob = request.form.get('dob')
        student_class = request.form['class']
        stream = request.form.get('stream')
        parent = request.form.get('parent')
        phone = request.form['phone']
        photo_file = request.files.get('photo')
        photo_filename = None
        if photo_file and photo_file.filename:
            photo_filename = f"{admission}.png"
            photo_file.save(os.path.join("static/student_photos", photo_filename))
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO students (admission, first_name, last_name, gender, dob, class, stream, parent, phone, photo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (admission, first_name, last_name, gender, dob, student_class, stream, parent, phone, photo_filename))
        conn.commit()
        conn.close()
        return redirect('/students')
    return render_template("add_student.html")

# -------------------------
# EDIT STUDENT
# -------------------------
@app.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit_student(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    if request.method == 'POST':
        admission = request.form['admission']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        gender = request.form.get('gender')
        dob = request.form.get('dob')
        student_class = request.form['class']
        stream = request.form.get('stream')
        parent = request.form.get('parent')
        phone = request.form['phone']
        photo_file = request.files.get('photo')
        photo_filename = student['photo']
        if photo_file and photo_file.filename:
            photo_filename = f"{admission}.png"
            photo_file.save(os.path.join("static/student_photos", photo_filename))
        cur.execute("""
            UPDATE students SET admission=%s, first_name=%s, last_name=%s, gender=%s, dob=%s,
            class=%s, stream=%s, parent=%s, phone=%s, photo=%s WHERE id=%s
        """, (admission, first_name, last_name, gender, dob, student_class, stream, parent, phone, photo_filename, id))
        conn.commit()
        conn.close()
        return redirect('/students')
    conn.close()
    return render_template("edit_student.html", student=student)

# -------------------------
# DELETE STUDENT
# -------------------------
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
# PROMOTE
# -------------------------
def next_class(c):
    classes = ["S1","S2","S3","S4","S5","S6"]
    if c in classes:
        idx = classes.index(c)
        return classes[min(idx+1, len(classes)-1)]
    return c

@app.route('/promote/<int:id>')
@login_required
def promote(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT class FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    new_class = next_class(student['class'])
    cur.execute("UPDATE students SET class=%s WHERE id=%s", (new_class, id))
    conn.commit()
    conn.close()
    return redirect('/students')

@app.route('/promote')
@login_required
def promote_all():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, class FROM students")
    students = cur.fetchall()
    for s in students:
        new_class = next_class(s['class'])
        cur.execute("UPDATE students SET class=%s WHERE id=%s", (new_class, s['id']))
    conn.commit()
    conn.close()
    return redirect('/students')

# -------------------------
# ID CARDS
# -------------------------
@app.route('/id_card/<int:id>')
@login_required
def id_card(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    conn.close()
    # Ensure default images if none exist
    if not student['photo']:
        student['photo'] = "default.png"
    return render_template("id_card.html", student=student)

@app.route('/batch-print')
@login_required
def batch_print():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    conn.close()
    for s in students:
        if not s['photo']:
            s['photo'] = "default.png"
    return render_template("batch_print.html", students=students)

@app.route('/print_all')
@login_required
def print_all():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    conn.close()
    for s in students:
        if not s['photo']:
            s['photo'] = "default.png"
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
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output,
                     download_name="students.xlsx",
                     as_attachment=True)

# -------------------------
# EXPORT PDF
# -------------------------
@app.route('/export/pdf')
@login_required
def export_pdf():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    conn.close()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A6)
    styles = getSampleStyleSheet()
    elements = []
    for s in students:
        elements.append(Paragraph(f"<b>{s['first_name']} {s['last_name']}</b>", styles['Title']))
        elements.append(Paragraph(f"Class: {s['class']}", styles['Normal']))
        elements.append(Spacer(1, 10))
        photo_path = f"static/student_photos/{s['photo']}" if s['photo'] else "static/student_photos/default.png"
        if not os.path.exists(photo_path):
            photo_path = "static/student_photos/default.png"
        elements.append(Image(photo_path, width=80, height=100))
        elements.append(Spacer(1, 10))
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer,
                     download_name="students.pdf",
                     as_attachment=True)

# -------------------------
# STARTUP
# -------------------------
init_db()
create_default_admin()

if __name__ == "__main__":
    app.run(debug=True)