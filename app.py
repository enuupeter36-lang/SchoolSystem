import os
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import qrcode
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from flask import Flask, render_template, request, redirect, send_file

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

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
    cur.execute("SELECT * FROM students ORDER BY id DESC")
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

# DELETE
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

    return render_template(
        "dashboard.html",
        total_students=total,
        class_data=class_data,
        gender_data=gender_data
    )

# EXPORT EXCEL
@app.route('/export/excel')
def export_excel():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM students", conn)
    conn.close()

    file_path = "students.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)

# EXPORT PDF
@app.route('/export/pdf')
def export_pdf():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    conn.close()

    doc = SimpleDocTemplate("students.pdf")
    styles = getSampleStyleSheet()

    content = []
    for s in students:
        content.append(Paragraph(f"{s['first_name']} {s['last_name']} - {s['class']}", styles['Normal']))

    doc.build(content)

    return send_file("students.pdf", as_attachment=True)

# QR CODE
@app.route('/qr/<int:id>')
def generate_qr(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cur.fetchone()
    conn.close()

    data = f"{student['first_name']} {student['last_name']} - {student['class']}"

    img = qrcode.make(data)
    path = f"static/qr_{id}.png"
    img.save(path)

    return send_file(path, mimetype='image/png')

# RUN
if __name__ == "__main__":
    app.run(debug=True)