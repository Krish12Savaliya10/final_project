import os
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# ------------------ MYSQL CONFIG ------------------
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'tourgen_db',
    'port': 8889
}

# ------------------ DATABASE CONNECTION ------------------
def get_db():
    return mysql.connector.connect(**MYSQL_CONFIG)

def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(query, args)
    result = cur.fetchone() if one else cur.fetchall()
    cur.close()
    db.close()
    return result

# ------------------ INITIALIZE DATABASE ------------------
def init_db():
    db = get_db()
    cur = db.cursor()

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(255) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        is_admin INT DEFAULT 0
    ) ENGINE=InnoDB;
    """)

    # TOURS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tours (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        price DECIMAL(10,2)
    ) ENGINE=InnoDB;
    """)

    # BOOKINGS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        tour_id INT NOT NULL,
        date VARCHAR(255),
        status VARCHAR(50) DEFAULT 'pending',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (tour_id) REFERENCES tours(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)

    # PAYMENTS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        booking_id INT NOT NULL,
        amount DECIMAL(10,2),
        paid INT,
        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)

    db.commit()
    cur.close()
    db.close()

# ------------------ ROUTE TO CREATE TABLES ------------------
@app.route('/initdb')
def route_initdb():
    key = request.args.get('key')
    if key != app.config['SECRET_KEY']:
        abort(403)
    init_db()
    return "Database initialized successfully!"

# ------------------ HOME ------------------
@app.route('/')
def home():
    tours = query_db('SELECT * FROM tours')
    return render_template('home.html', tours=tours)

@app.route('/tourlist')
def tourlist():
    search = request.args.get('search', '')
    if search:
        tours = query_db("SELECT * FROM tours WHERE title LIKE %s", (f"%{search}%",))
    else:
        tours = query_db("SELECT * FROM tours")
    return render_template('tourlist.html', tours=tours, search=search)


# ------------------ SIGNUP ------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm']

        if password != confirm:
            flash('Passwords do not match')
            return redirect(url_for('signup'))

        db = get_db()
        cur = db.cursor()

        try:
            cur.execute(
                'INSERT INTO users (username, password) VALUES (%s, %s)',
                (username, generate_password_hash(password))
            )
            db.commit()
            flash('Account created! Please login.')
            return redirect(url_for('login'))

        except mysql.connector.IntegrityError:
            flash('Username already exists')

        finally:
            cur.close()

    return render_template('signup.html')


# ------------------ LOGIN ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = query_db(
            'SELECT * FROM users WHERE username = %s',
            (username,), one=True
        )

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            flash('Login successful!')
            return redirect(url_for('home'))

        flash('Invalid username or password')

    return render_template('login.html')

# ------------------ LOGOUT ------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ------------------ LOGIN REQUIRED DECORATOR ------------------
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return fn(*a, **kw)
    return wrapper

# ------------------ BOOK TOUR ------------------
@app.route('/booking/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def booking(tour_id):
    tour = query_db('SELECT * FROM tours WHERE id=%s', (tour_id,), one=True)
    if not tour:
        abort(404)

    if request.method == 'POST':
        date = request.form.get('date', '')

        db = get_db()
        cur = db.cursor()

        cur.execute(
            'INSERT INTO bookings (user_id, tour_id, date) VALUES (%s, %s, %s)',
            (session['user_id'], tour_id, date)
        )
        db.commit()
        booking_id = cur.lastrowid

        cur.close()
        db.close()

        return redirect(url_for('payment', booking_id=booking_id))

    return render_template('booking.html', tour=tour)

# ------------------ PAYMENT ------------------
@app.route('/payment/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def payment(booking_id):
    booking = query_db("""
        SELECT b.*, t.price, t.title
        FROM bookings b
        JOIN tours t ON b.tour_id=t.id
        WHERE b.id=%s
    """, (booking_id,), one=True)

    if not booking:
        abort(404)

    if request.method == 'POST':
        amount = float(request.form.get('amount') or booking['price'])

        db = get_db()
        cur = db.cursor()

        cur.execute(
            'INSERT INTO payments (booking_id, amount, paid) VALUES (%s, %s, %s)',
            (booking_id, amount, 1)
        )

        cur.execute(
            'UPDATE bookings SET status="paid" WHERE id=%s',
            (booking_id,)
        )

        db.commit()
        cur.close()
        db.close()

        flash('Payment successful!')
        return redirect(url_for('home'))

    return render_template('payment.html', booking=booking)

# ------------------ RUN SERVER ------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
