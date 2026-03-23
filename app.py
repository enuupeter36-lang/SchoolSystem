import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import qrcode
from reportlab.graphics.barcode.code128 import Code128
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")

# PostgreSQL Configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# Config
UPLOAD_FOLDER = "static/student_photos"
QRCODE_FOLDER = "static/qrcodes"
BARCODE_FOLDER = "static/barcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QRCODE_FOLDER, exist_ok=True)
os.makedirs(BARCODE_FOLDER, exist_ok=True)

# ============== DATABASE FUNCTIONS ==============

def get_db():
    """Get database connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    """Initialize database tables"""
    conn = get_db()
    if not conn:
        print("Failed to connect to database")
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            admission TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            gender TEXT,
            dob TEXT,
            class TEXT NOT NULL,
            stream TEXT,
            parent TEXT,
            phone TEXT NOT NULL,
            photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        cursor.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        conn.close()

def execute_query(query, params=None):
    """Execute INSERT, UPDATE, DELETE queries"""
    conn = get_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f"Query error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def fetch_all(query, params=None):
    """Fetch multiple rows"""
    conn = get_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params or ())
        data = cursor.fetchall()
        cursor.close()
        return data
    except Exception as e:
        print(f"Fetch error: {e}")
        return []
    finally:
        conn.close()

def fetch_one(query, params=None):
    """Fetch single row"""
    conn = get_db()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params or ())
        data = cursor.fetchone()
        cursor.close()
        return data
    except Exception as e:
        print(f"Fetch error: {e}")
        return None
    finally:
        conn.close()

def fetch_count(query):
    """Fetch count"""
    conn = get_db()
    if not conn:
        return 0
    
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else 0
    except Exception as e:
        print(f"Count error: {e}")
        return 0
    finally:
        conn.close()

# ============== HELPER FUNCTIONS ==============

def generate_qr(admission):
    """Generate QR code"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(admission)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        filepath = os.path.join(QRCODE_FOLDER, f"{admission}.png")
        img.save(filepath)
        print(f"QR code generated: {admission}")
    except Exception as e:
        print(f"Error generating QR code: {e}")

def generate_barcode(admission):
    """Generate barcode"""
    try:
        barcode_value = Code128(admission, barWidth=1.5, barHeight=25)
        filepath = os.path.join(BARCODE_FOLDER, f"{admission}.png")
        barcode_value.save(filename=filepath, formats=['png'])
        print(f"Barcode generated: {admission}")
    except Exception as e:
        print(f"Error generating barcode: {e}")

# ============== ROUTES ==============

@app.route("/")
def dashboard():
    """Dashboard page"""
    init_db()
    total = fetch_count("SELECT COUNT(*) FROM students")
    classes = fetch_all("SELECT class, COUNT(*) as count FROM students GROUP BY class ORDER BY class")
    
    return render_template("dashboard.html", total=total, classes=classes)

@app.route("/add", methods=["GET", "POST"])
def add_student():
    """Add new student"""
    if request.method == "POST":
        try:
            data = request.form
            photo = request.files.get("photo")

            filename = ""
            if photo and photo.filename != "":
                filename = photo.filename
                photo.save(os.path.join(UPLOAD_FOLDER, filename))

            success = execute_query("""
            INSERT INTO students (admission, first_name, last_name, gender, dob, class, stream, parent, phone, photo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data["admission"],
                data["first_name"],
                data["last_name"],
                data.get("gender", ""),
                data.get("dob", ""),
                data["class"],
                data["stream"],
                data.get("parent", ""),
                data["phone"],
                filename
            ))

            if success:
                generate_qr(data["admission"])
                generate_barcode(data["admission"])
                return redirect("/students")
            else:
                return render_template("add_student.html", error="Failed to add student")
        except Exception as e:
            return render_template("add_student.html", error=str(e))

    return render_template("add_student.html")

@app.route("/students")
def students():
    """View all students"""
    search = request.args.get("search", "")
    cls = request.args.get("class", "")

    query = "SELECT * FROM students WHERE 1=1"
    params = []

    if search:
        query += " AND (first_name ILIKE %s OR last_name ILIKE %s OR admission ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if cls:
        query += " AND class=%s"
        params.append(cls)

    query += " ORDER BY admission"
    data = fetch_all(query, params)

    return render_template("students.html", students=data)

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    """Edit student"""
    if request.method == "POST":
        try:
            data = request.form
            photo = request.files.get("photo")

            student = fetch_one("SELECT * FROM students WHERE id=%s", (id,))
            if not student:
                return redirect("/students")

            filename = student['photo']

            if photo and photo.filename != "":
                filename = photo.filename
                photo.save(os.path.join(UPLOAD_FOLDER, filename))

            success = execute_query("""
            UPDATE students SET 
                admission=%s, first_name=%s, last_name=%s, gender=%s, dob=%s, class=%s, stream=%s, parent=%s, phone=%s, photo=%s
            WHERE id=%s
            """, (
                data["admission"],
                data["first_name"],
                data["last_name"],
                data.get("gender", ""),
                data.get("dob", ""),
                data["class"],
                data["stream"],
                data.get("parent", ""),
                data["phone"],
                filename,
                id
            ))

            if success:
                generate_qr(data["admission"])
                generate_barcode(data["admission"])
                return redirect("/students")
            else:
                return render_template("edit_student.html", student=student, error="Failed to update student")
        except Exception as e:
            student = fetch_one("SELECT * FROM students WHERE id=%s", (id,))
            return render_template("edit_student.html", student=student, error=str(e))

    student = fetch_one("SELECT * FROM students WHERE id=%s", (id,))
    if not student:
        return redirect("/students")

    return render_template("edit_student.html", student=student)

@app.route("/delete/<int:id>")
def delete_student(id):
    """Delete student"""
    try:
        student = fetch_one("SELECT photo FROM students WHERE id=%s", (id,))

        if student:
            execute_query("DELETE FROM students WHERE id=%s", (id,))

            if student['photo']:
                photo_path = os.path.join(UPLOAD_FOLDER, student['photo'])
                if os.path.exists(photo_path):
                    os.remove(photo_path)
    except Exception as e:
        print(f"Error deleting student: {e}")

    return redirect("/students")

@app.route("/promote")
def promote_students():
    """Promote all students to next class"""
    try:
        promotion_map = {
            "S1": "S2",
            "S2": "S3",
            "S3": "S4",
            "S4": "S5",
            "S5": "S6"
        }

        for old, new in promotion_map.items():
            execute_query("UPDATE students SET class=%s WHERE class=%s", (new, old))
    except Exception as e:
        print(f"Error promoting students: {e}")

    return redirect("/students")

@app.route("/id/<int:id>")
def id_card(id):
    """View single ID card"""
    student = fetch_one("SELECT * FROM students WHERE id=%s", (id,))
    if not student:
        return redirect("/students")

    return render_template("id_card.html", student=student)

@app.route("/print/<int:id>")
def print_card(id):
    """Print single card"""
    student = fetch_one("SELECT * FROM students WHERE id=%s", (id,))
    if not student:
        return redirect("/students")

    return render_template("print_card.html", student=student)

@app.route("/print-all")
def print_all_cards():
    """Print all cards"""
    cls = request.args.get("class", "")

    if cls:
        students = fetch_all("SELECT * FROM students WHERE class=%s ORDER BY admission", (cls,))
    else:
        students = fetch_all("SELECT * FROM students ORDER BY admission")

    return render_template("print_all.html", students=students, selected_class=cls)

@app.route("/batch-print")
def batch_print():
    """Batch print by class"""
    classes = fetch_all("SELECT DISTINCT class FROM students ORDER BY class")
    return render_template("batch_print.html", classes=classes)

# ============== RUN APP ==============

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)