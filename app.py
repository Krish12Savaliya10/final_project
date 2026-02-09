import os
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tourgen-secret-key'

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

# ------------------ DECORATORS ------------------
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return fn(*a, **kw)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('is_admin'):
            abort(403)
        return fn(*a, **kw)
    return wrapper

# ------------------ HOME ------------------
@app.route('/')
def home():
    tours = query_db('SELECT * FROM tours')
    return render_template('home.html', tours=tours)

# ------------------ TOUR LIST ------------------
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

        hashed = generate_password_hash(password)  # PASSWORD HASHED HERE

        db = get_db()
        cur = db.cursor()

        try:
            cur.execute(
                'INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)',
                (username, hashed, 0)
            )
            db.commit()
            flash('Account created! Please login.')
            return redirect(url_for('login'))

        except mysql.connector.IntegrityError:
            flash('Username already exists')

        finally:
            cur.close()
            db.close()

    return render_template('signup.html')

# ------------------ LOGIN ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        user = query_db(
            'SELECT * FROM users WHERE username=%s',
            (username,), one=True
        )

        # PASSWORD CHECK
        if user and check_password_hash(user['password'], password):

            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])

            flash('Login successful!')

            # ADMIN REDIRECT
            if session['is_admin']:
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('home'))

        flash('Invalid username or password')

    return render_template('login.html')

# ------------------ LOGOUT ------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for('home'))

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
            'INSERT INTO bookings (user_id, tour_id, date, status) VALUES (%s,%s,%s,%s)',
            (session['user_id'], tour_id, date, 'pending')
        )
        db.commit()

        booking_id = cur.lastrowid

        cur.close()
        db.close()

        return redirect(url_for('payment', booking_id=booking_id))

    return render_template('booking.html', tour=tour)

# ------------------ MY BOOKINGS ------------------
@app.route('/mybookings')
@login_required
def mybookings():
    rows = query_db('''
     SELECT b.*, t.title, t.price
     FROM bookings b
     JOIN tours t ON b.tour_id = t.id
     WHERE b.user_id = %s
     ORDER BY b.id DESC
    ''', (session['user_id'],))
    return render_template('mybookings.html', bookings=rows)


# ------------------ PAYMENT ------------------
@app.route('/payment/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def payment(booking_id):

    booking = query_db("""
        SELECT b.*, t.price, t.title
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        WHERE b.id=%s
    """, (booking_id,), one=True)

    if not booking:
        abort(404)

    if request.method == 'POST':

        amount = float(request.form.get('amount') or booking['price'])

        db = get_db()
        cur = db.cursor()

        cur.execute(
            'INSERT INTO payments (booking_id, amount, paid) VALUES (%s,%s,%s)',
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
        return redirect(url_for('mybookings'))

    return render_template('payment.html', booking=booking)

# ------------------ ADMIN DASHBOARD ------------------
@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin():

    db = get_db()
    cur = db.cursor()

    # ADD TOUR
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        price = request.form.get('price')

        cur.execute(
            "INSERT INTO tours (title, description, price) VALUES (%s,%s,%s)",
            (title, description, price)
        )
        db.commit()

    cur.close()
    db.close()

    tours = query_db("SELECT * FROM tours")
    bookings = query_db("""
        SELECT b.id, u.username, t.title, b.date, b.status
        FROM bookings b
        JOIN users u ON b.user_id=u.id
        JOIN tours t ON b.tour_id=t.id
        ORDER BY b.id DESC
    """)
    users = query_db("SELECT id, username, is_admin FROM users")

    return render_template('admin.html', tours=tours, bookings=bookings, users=users)

# ------------------ RUN SERVER ------------------
if __name__ == '__main__':
    app.run(debug=True, port=5001)
