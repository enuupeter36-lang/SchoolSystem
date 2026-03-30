import os
import io
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import qrcode
from flask import Flask, render_template, request, redirect, send_file, url_for
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")  # Set your database URL

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# HOME
@app.route('/')
def home():
    return render_template("index.html")

# VIEW STUDENTS
@app.route('/students')
def students():
    conn = get_connection()
    cur = conn.cursor()
    search = request.args.get('search', '')
    class_filter = request.args.get('class', '')
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if search:
        query += " AND (first_name ILIKE %s OR last_name ILIKE %s OR admission ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if class_filter:
        query += " AND class=%s"
        params.append(class_filter)
    query += " ORDER BY id DESC"
    cur.execute(query, params)
    data = cur.fetchall()
    conn.close()
    return render_template("students.html", students=data)

# ADD STUDENT
@app.route('/add', methods=['GET', 'POST'])
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

# EDIT STUDENT
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
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

# DELETE STUDENT
@app.route('/delete/<int:id>')
def delete_student(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect('/students')

# DASHBOARD
@app.route('/dashboard')
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
    return render_template("dashboard.html", total_students=total, class_data=class_data, gender_data=gender_data)

# VIEW SINGLE ID CARD
@app.route('/id_card/<int:id>')
def id_card(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    conn.close()
    return render_template("id_card.html", student=student)

# PRINT ALL / BATCH PRINT
@app.route('/batch-print')
def batch_print():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students ORDER BY class, first_name")
    students = cur.fetchall()
    conn.close()
    return render_template("batch_print.html", students=students)

# EXPORT EXCEL
@app.route('/export/excel')
def export_excel():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM students", conn)
    conn.close()
    file_path = "students.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

# EXPORT PDF (ID Cards layout)
@app.route('/export/pdf')
def export_pdf():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students ORDER BY class, first_name")
    students = cur.fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(100*mm, 150*mm), leftMargin=10, rightMargin=10, topMargin=10, bottomMargin=10)
    styles = getSampleStyleSheet()
    elements = []

    for s in students:
        # School Logo
        try:
            elements.append(Image("static/logo.png", width=40, height=40))
        except:
            pass

        elements.append(Spacer(1, 4))

        # Name
        elements.append(Paragraph(f"<b>{s['first_name']} {s['last_name']}</b>", styles['Title']))
        elements.append(Paragraph(f"Adm: {s['admission']}", styles['Normal']))
        elements.append(Paragraph(f"{s['class']} {s['stream'] or ''}", styles['Normal']))
        elements.append(Spacer(1, 4))

        # Photo
        photo_path = f"static/student_photos/{s['photo'] or 'default.png'}"
        try:
            elements.append(Image(photo_path, width=80, height=100))
        except:
            pass

        # Barcode
        barcode_path = f"static/barcodes/{s['admission']}.png"
        try:
            elements.append(Image(barcode_path, width=80, height=30))
        except:
            pass

        # QR code
        qr_path = f"static/qrcodes/{s['admission']}.png"
        try:
            elements.append(Image(qr_path, width=60, height=60))
        except:
            pass

        elements.append(Spacer(1, 10))

    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="students_id_cards.pdf", mimetype="application/pdf")

# GENERATE QR CODE
@app.route('/qr/<int:id>')
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

# RUN APP
if __name__ == "__main__":
    app.run(debug=True)