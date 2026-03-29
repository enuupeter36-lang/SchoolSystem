import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for
import qrcode
from reportlab.graphics.barcode.code128 import Code128

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")

# ================= DATABASE =================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL is not set. Check Render environment variables.")

# ✅ Fix postgres:// issue on Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

UPLOAD_FOLDER = "static/student_photos"
QRCODE_FOLDER = "static/qrcodes"
BARCODE_FOLDER = "static/barcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QRCODE_FOLDER, exist_ok=True)
os.makedirs(BARCODE_FOLDER, exist_ok=True)

# ================= DB FUNCTIONS =================

def get_db():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print("❌ DB CONNECTION ERROR:", e)
        return None

def init_db():
    conn = get_db()
    if not conn:
        return

    try:
        cur = conn.cursor()
        cur.execute("""
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
        cur.close()
        print("✅ Database initialized")
    except Exception as e:
        print("❌ INIT DB ERROR:", e)
    finally:
        conn.close()

# ✅ RUN DB INIT ON START (IMPORTANT FIX)
init_db()

def execute_query(query, params=None):
    conn = get_db()
    if not conn:
        raise Exception("Database connection failed")

    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print("🔥 QUERY ERROR:", e)
        raise e
    finally:
        conn.close()

def fetch_all(query, params=None):
    conn = get_db()
    if not conn:
        return []

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params or ())
        data = cur.fetchall()
        cur.close()
        return data
    except Exception as e:
        print("❌ FETCH ERROR:", e)
        return []
    finally:
        conn.close()

def fetch_count(query):
    conn = get_db()
    if not conn:
        return 0

    try:
        cur = conn.cursor()
        cur.execute(query)
        count = cur.fetchone()[0]
        cur.close()
        return count
    except Exception as e:
        print("❌ COUNT ERROR:", e)
        return 0
    finally:
        conn.close()

def fetch_one(query, params=None):
    conn = get_db()
    if not conn:
        return None

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params or ())
        data = cur.fetchone()
        cur.close()
        return data
    except Exception as e:
        print("❌ FETCH ONE ERROR:", e)
        return None
    finally:
        conn.close()

# ================= HELPERS =================

def generate_qr(admission):
    try:
        qr = qrcode.make(admission)
        qr.save(f"{QRCODE_FOLDER}/{admission}.png")
    except Exception as e:
        print("❌ QR ERROR:", e)

def generate_barcode(admission):
    try:
        barcode = Code128(admission)
        barcode.save(f"{BARCODE_FOLDER}/{admission}.png")
    except Exception as e:
        print("❌ BARCODE ERROR:", e)

# ================= ROUTES =================

@app.route("/")
def dashboard():
    try:
        total = fetch_count("SELECT COUNT(*) FROM students")

        classes = fetch_all("""
            SELECT class, COUNT(*) as count 
            FROM students 
            GROUP BY class 
            ORDER BY class
        """)

        gender = fetch_all("""
            SELECT gender, COUNT(*) as count 
            FROM students 
            GROUP BY gender
        """)

        return render_template(
            "dashboard.html",
            total=total,
            classes=classes,
            gender=gender
        )

    except Exception as e:
        return f"Dashboard Error: {e}"
@app.route("/add", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        try:
            data = request.form
            photo = request.files.get("photo")

            filename = ""
            if photo and photo.filename != "":
                filename = photo.filename
                photo.save(os.path.join(UPLOAD_FOLDER, filename))

            execute_query("""
                INSERT INTO students 
                (admission, first_name, last_name, gender, dob, class, stream, parent, phone, photo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get("admission"),
                data.get("first_name"),
                data.get("last_name"),
                data.get("gender", ""),
                data.get("dob", ""),
                data.get("class"),
                data.get("stream", ""),
                data.get("parent", ""),
                data.get("phone"),
                filename
            ))

            generate_qr(data.get("admission"))
            generate_barcode(data.get("admission"))

            return redirect("/students")

        except Exception as e:
            print("🔥 ADD ERROR:", e)

            if "duplicate key" in str(e):
                return render_template("add_student.html", error="Admission number already exists")

            return render_template("add_student.html", error=str(e))

    return render_template("add_student.html")

@app.route("/students")
def students():
    try:
        search = request.args.get("search", "")
        class_filter = request.args.get("class", "")

        query = "SELECT * FROM students WHERE 1=1"
        params = []

        if search:
            query += " AND (LOWER(first_name) LIKE %s OR LOWER(last_name) LIKE %s OR LOWER(admission) LIKE %s)"
            search_term = f"%{search.lower()}%"
            params.extend([search_term, search_term, search_term])

        if class_filter:
            query += " AND class=%s"
            params.append(class_filter)

        query += " ORDER BY admission"

        data = fetch_all(query, params)

        return render_template("students.html", students=data)

    except Exception as e:
        return f"Students Error: {e}"

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    if request.method == "POST":
        try:
            data = request.form

            execute_query("""
                UPDATE students SET
                first_name=%s,
                last_name=%s,
                gender=%s,
                dob=%s,
                class=%s,
                stream=%s,
                parent=%s,
                phone=%s
                WHERE id=%s
            """, (
                data.get("first_name"),
                data.get("last_name"),
                data.get("gender"),
                data.get("dob"),
                data.get("class"),
                data.get("stream"),
                data.get("parent"),
                data.get("phone"),
                id
            ))

            return redirect("/students")

        except Exception as e:
            return f"Edit Error: {e}"

    student = fetch_one("SELECT * FROM students WHERE id=%s", (id,))
    return render_template("edit_student.html", student=student)

@app.route("/id/<admission>")
def generate_id(admission):
    student = fetch_one("SELECT * FROM students WHERE admission=%s", (admission,))

    if not student:
        return "Student not found"

    return render_template("id_card.html", s=student)

# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)