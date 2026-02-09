import os
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tourgen-secret-key'

# ------------------ FILE UPLOAD CONFIG ------------------
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

# ------------------ USER ROUTES ------------------

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

# ------------------ AUTHENTICATION ------------------

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm']

        if password != confirm:
            flash('Passwords do not match')
            return redirect(url_for('signup'))

        hashed = generate_password_hash(password)
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute('INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)', (username, hashed, 0))
            db.commit()
            flash('Account created! Please login.')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Username already exists')
        finally:
            cur.close()
            db.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = query_db('SELECT * FROM users WHERE username=%s', (username,), one=True)

        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            flash('Login successful!')
            return redirect(url_for('admin') if session['is_admin'] else url_for('home'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for('home'))

# ------------------ SIMPLIFIED JOIN SYSTEM ------------------

@app.route('/booking/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def booking(tour_id):
    # Fetch tour details and the day-wise itinerary for the traveler to see
    tour = query_db('SELECT * FROM tours WHERE id=%s', (tour_id,), one=True)
    if not tour:
        abort(404)

    # Fetch detailed itinerary to show traveler what they are joining
    itinerary = query_db("""
        SELECT ti.day_number, ms.spot_name 
        FROM tour_itinerary ti 
        JOIN master_spots ms ON ti.spot_id = ms.id 
        WHERE ti.tour_id = %s 
        ORDER BY ti.day_number ASC, ti.order_sequence ASC
    """, (tour_id,))

    if request.method == 'POST':
        # Travelers just click "Join" - no date entry needed.
        # We automatically use the tour's fixed start date.
        db = get_db()
        cur = db.cursor()
        cur.execute(
            'INSERT INTO bookings (user_id, tour_id, date, status) VALUES (%s,%s,%s,%s)',
            (session['user_id'], tour_id, tour['start_date'], 'pending')
        )
        db.commit()
        booking_id = cur.lastrowid
        cur.close()
        db.close()
        return redirect(url_for('payment', booking_id=booking_id))

    return render_template('booking.html', tour=tour, itinerary=itinerary)

@app.route('/mybookings')
@login_required
def mybookings():
    rows = query_db('''
     SELECT b.*, t.title, t.price FROM bookings b
     JOIN tours t ON b.tour_id = t.id
     WHERE b.user_id = %s ORDER BY b.id DESC
    ''', (session['user_id'],))
    return render_template('mybookings.html', bookings=rows)

@app.route('/payment/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def payment(booking_id):
    booking = query_db("""
        SELECT b.*, t.price, t.title FROM bookings b
        JOIN tours t ON b.tour_id = t.id WHERE b.id=%s
    """, (booking_id,), one=True)
    if not booking: abort(404)

    if request.method == 'POST':
        amount = float(request.form.get('amount') or booking['price'])
        db = get_db()
        cur = db.cursor()
        cur.execute('INSERT INTO payments (booking_id, amount, paid) VALUES (%s,%s,%s)', (booking_id, amount, 1))
        cur.execute('UPDATE bookings SET status="paid" WHERE id=%s', (booking_id,))
        db.commit()
        cur.close()
        db.close()
        flash('Payment successful!')
        return redirect(url_for('mybookings'))
    return render_template('payment.html', booking=booking)

# ------------------ UPDATED ADMIN COMMAND CENTER ------------------

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin():
    db = get_db()
    cur = db.cursor(dictionary=True)

    if request.method == 'POST':
        action = request.form.get('action')

        # Action 1: Add a reusable Spot to the Master Database (Library)
        if action == 'add_spot':
            spot_name = request.form.get('spot_name')
            file = request.files.get('spot_image')
            filename = None
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            cur.execute("INSERT INTO master_spots (spot_name, image_url) VALUES (%s, %s)",
                        (spot_name, filename))
            db.commit()
            flash("Spot saved to library!")

        # Action 2: Create a Detailed Tour with Day-wise Itinerary
        elif action == 'add_tour':
            title = request.form.get('title')
            description = request.form.get('description')
            price = request.form.get('price')
            start_point = request.form.get('start_point')
            end_point = request.form.get('end_point')
            start_date = request.form.get('start_date') or None
            end_date = request.form.get('end_date') or None
            
            file = request.files.get('tour_image')
            filename = None
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            cur.execute("""
                INSERT INTO tours (title, description, price, start_date, end_date, start_point, end_point, image_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (title, description, price, start_date, end_date, start_point, end_point, filename))
            
            tour_id = cur.lastrowid

            # Save the Itinerary with Day Numbers
            selected_spots = request.form.getlist('spots[]')
            day_numbers = request.form.getlist('day_numbers[]')
            
            for idx, spot_id in enumerate(selected_spots):
                day = day_numbers[idx] if idx < len(day_numbers) else 1
                cur.execute("""
                    INSERT INTO tour_itinerary (tour_id, spot_id, order_sequence, day_number) 
                    VALUES (%s, %s, %s, %s)
                """, (tour_id, spot_id, idx, day))
            
            db.commit()
            flash("Detailed tour published successfully!")

    # Fetch data for display
    tours = query_db("SELECT * FROM tours")
    master_spots = query_db("SELECT * FROM master_spots")
    bookings = query_db("""
        SELECT b.id, u.username, t.title, b.date, b.status FROM bookings b
        JOIN users u ON b.user_id=u.id JOIN tours t ON b.tour_id=t.id ORDER BY b.id DESC
    """)
    users = query_db("SELECT id, username, is_admin FROM users")

    cur.close()
    db.close()
    return render_template('admin.html', tours=tours, spots=master_spots, bookings=bookings, users=users)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5001)