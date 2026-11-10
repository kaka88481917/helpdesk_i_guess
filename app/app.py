from flask import Flask, render_template_string, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from prometheus_flask_exporter import PrometheusMetrics
import psycopg2
import os

app = Flask(__name__)
app.secret_key = 'super_secret_key'
metrics = PrometheusMetrics(app)

DB_HOST = os.environ.get('DB_HOST', 'db')
DB_NAME = os.environ.get('DB_NAME', 'helpdesk')
DB_USER = os.environ.get('DB_USER', 'user')
DB_PASS = os.environ.get('DB_PASS', 'password')

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. สร้างตารางผู้ใช้งาน (Users)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'user'
        );
    ''')
    
    # 2. สร้างตารางแจ้งปัญหา (Reports) และเชื่อมกับ Users
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            title VARCHAR(255) NOT NULL,
            category VARCHAR(100),
            status VARCHAR(50) DEFAULT 'Pending'
        );
    ''')
    
    # 3. สร้าง User Admin อัตโนมัติ (ถ้ายังไม่มี)
    cur.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        hashed_pw = generate_password_hash('admin')
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'admin')", ('admin', hashed_pw))
        
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ================= HTML TEMPLATES (Bootstrap 5) =================

BASE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Campus Helpdesk</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4 shadow-sm">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/">🛠️ Campus Helpdesk</a>
            <div class="d-flex text-white align-items-center">
                {% if session.get('username') %}
                    <span class="me-3">Welcome, <strong>{{ session['username'] }}</strong> <span class="badge bg-light text-dark">{{ session['role'] }}</span></span>
                    <a href="/logout" class="btn btn-sm btn-outline-light">Logout</a>
                {% else %}
                    <a href="/" class="btn btn-sm btn-outline-light me-2">Login</a>
                    <a href="/register" class="btn btn-sm btn-light text-primary">Register</a>
                {% endif %}
            </div>
        </div>
    </nav>
    <div class="container">
        {% if error %}<div class="alert alert-danger shadow-sm">{{ error }}</div>{% endif %}
        {% if msg %}<div class="alert alert-success shadow-sm">{{ msg }}</div>{% endif %}
        {{ content | safe }}
    </div>
</body>
</html>
'''

AUTH_HTML = '''
<div class="row justify-content-center">
    <div class="col-md-5">
        <div class="card shadow-sm border-0 mt-5">
            <div class="card-body p-4">
                <h3 class="text-center mb-4">{{ title }}</h3>
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Username</label>
                        <input type="text" name="username" class="form-control" required autofocus>
                    </div>
                    <div class="mb-4">
                        <label class="form-label">Password</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 fw-bold">{{ title }}</button>
                </form>
                {% if title == 'Login' %}
                    <div class="text-center mt-3"><a href="/register" class="text-decoration-none">Create an account</a></div>
                {% else %}
                    <div class="text-center mt-3"><a href="/" class="text-decoration-none">Already have an account? Login</a></div>
                {% endif %}
            </div>
        </div>
    </div>
</div>
'''

DASHBOARD_HTML = '''
<div class="row">
    <!-- Form Section -->
    <div class="col-md-4 mb-4">
        <div class="card shadow-sm border-0">
            <div class="card-header bg-white fw-bold">📝 Submit New Report</div>
            <div class="card-body">
                <form method="POST" action="/report">
                    <div class="mb-3">
                        <label class="form-label">Issue Title</label>
                        <input type="text" name="title" class="form-control" placeholder="e.g. Wi-Fi is down" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Category</label>
                        <select name="category" class="form-select">
                            <option value="IT Support">IT Support</option>
                            <option value="Facility">Facility & Maintenance</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-success w-100">Submit Report</button>
                </form>
            </div>
        </div>
    </div>

    <!-- Table Section -->
    <div class="col-md-8">
        <div class="card shadow-sm border-0">
            <div class="card-header bg-white fw-bold">
                {% if session['role'] == 'admin' %} All Reports (Admin View) {% else %} My Reports {% endif %}
            </div>
            <div class="card-body p-0">
                <table class="table table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>ID</th>
                            {% if session['role'] == 'admin' %}<th>Requester</th>{% endif %}
                            <th>Title</th>
                            <th>Category</th>
                            <th>Status</th>
                            {% if session['role'] == 'admin' %}<th>Action</th>{% endif %}
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in reports %}
                        <tr>
                            <td>#{{ row[0] }}</td>
                            {% if session['role'] == 'admin' %}<td><span class="badge bg-secondary">{{ row[4] }}</span></td>{% endif %}
                            <td>{{ row[1] }}</td>
                            <td>{{ row[2] }}</td>
                            <td>
                                {% if row[3] == 'Pending' %} <span class="badge bg-warning text-dark">Pending</span>
                                {% else %} <span class="badge bg-success">Closed</span> {% endif %}
                            </td>
                            {% if session['role'] == 'admin' %}
                            <td>
                                {% if row[3] == 'Pending' %}
                                <form action="/close/{{ row[0] }}" method="POST" class="d-inline">
                                    <button type="submit" class="btn btn-sm btn-primary">Close Case</button>
                                </form>
                                {% endif %}
                            </td>
                            {% endif %}
                        </tr>
                        {% else %}
                        <tr><td colspan="6" class="text-center text-muted py-4">No reports found.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
'''
    
# ================= ROUTES =================

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'username' in session: return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        # ตรวจสอบรหัสผ่านที่เข้ารหัสไว้
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid username or password'
            
    content = render_template_string(AUTH_HTML, title='Login')
    return render_template_string(BASE_HTML, content=content, error=error, msg=request.args.get('msg'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session: return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            error = 'Username already taken!'
        else:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_pw))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('login', msg='Registration successful! Please login.'))
        cur.close()
        conn.close()
        
    content = render_template_string(AUTH_HTML, title='Register')
    return render_template_string(BASE_HTML, content=content, error=error)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # เงื่อนไขแบ่ง Role (Admin เห็นทั้งหมดพร้อมชื่อคนแจ้ง, User เห็นแค่ของตัวเอง)
    if session['role'] == 'admin':
        cur.execute('''
            SELECT r.id, r.title, r.category, r.status, u.username 
            FROM reports r JOIN users u ON r.user_id = u.id ORDER BY r.id DESC
        ''')
    else:
        cur.execute('''
            SELECT id, title, category, status 
            FROM reports WHERE user_id = %s ORDER BY id DESC
        ''', (session['user_id'],))
        
    reports = cur.fetchall()
    cur.close()
    conn.close()
    
    content = render_template_string(DASHBOARD_HTML, reports=reports)
    return render_template_string(BASE_HTML, content=content)

@app.route('/report', methods=['POST'])
def report():
    if 'username' not in session: return redirect(url_for('login'))
    
    title = request.form['title']
    category = request.form['category']
    user_id = session['user_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO reports (user_id, title, category) VALUES (%s, %s, %s)', (user_id, title, category))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/close/<int:report_id>', methods=['POST'])
def close_report(report_id):
    if session.get('role') != 'admin': return "Unauthorized", 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE reports SET status = 'Closed' WHERE id = %s", (report_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)