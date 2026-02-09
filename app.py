import os
import mysql.connector
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tourgen-secret-key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# --- DATABASE CONFIG (Matches tourgen_db-6.sql) ---
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'tourgen_db',
    'port': 8889
}

def query_db(query, args=(), one=False):
    db = mysql.connector.connect(**MYSQL_CONFIG)
    cur = db.cursor(dictionary=True)
    cur.execute(query, args)
    res = cur.fetchone() if one else cur.fetchall()
    cur.close()
    db.close()
    return res

# --- DECORATORS ---
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        return fn(*a, **kw)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('is_admin'): abort(403)
        return fn(*a, **kw)
    return wrapper

# --- USER ROUTES ---
@app.route('/')
def home():
    tours = query_db('SELECT * FROM tours LIMIT 3') 
    return render_template('home.html', tours=tours)

@app.route('/tour')
def tour():
    search = request.args.get('search', '')
    if search:
        tours = query_db("SELECT * FROM tours WHERE title LIKE %s", (f"%{search}%",))
    else:
        tours = query_db("SELECT * FROM tours")
    return render_template('tour.html', tours=tours, search=search)

@app.route('/booking/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def booking(tour_id):
    tour = query_db('SELECT * FROM tours WHERE id=%s', (tour_id,), one=True)
    if not tour: abort(404)

    if request.method == 'POST':
        final_amount = request.form.get('final_amount') 
        db = mysql.connector.connect(**MYSQL_CONFIG)
        cur = db.cursor()
        cur.execute(
            'INSERT INTO bookings (user_id, tour_id, date, status) VALUES (%s,%s,%s,%s)',
            (session['user_id'], tour_id, tour['start_date'], 'pending')
        )
        db.commit()
        booking_id = cur.lastrowid
        cur.close()
        db.close()
        return redirect(url_for('payment', booking_id=booking_id, amount=final_amount))

    # New query - adds 'ms.image_url' so you can show the photo!
    itinerary = query_db("""
        SELECT ti.day_number, ms.spot_name, ms.image_url 
        FROM tour_itinerary ti 
        JOIN master_spots ms ON ti.spot_id = ms.id 
        WHERE ti.tour_id = %s ORDER BY ti.day_number ASC
    """, (tour_id,))
    return render_template('booking.html', tour=tour, itinerary=itinerary)

@app.route('/payment/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def payment(booking_id):
    booking = query_db("""
        SELECT b.*, t.price, t.title FROM bookings b
        JOIN tours t ON b.tour_id = t.id WHERE b.id=%s
    """, (booking_id,), one=True)
    if not booking: abort(404)
    
    custom_amount = request.args.get('amount')
    amount_to_pay = float(custom_amount) if custom_amount else float(booking['price'])

    if request.method == 'POST':
        db = mysql.connector.connect(**MYSQL_CONFIG)
        cur = db.cursor()
        cur.execute('INSERT INTO payments (booking_id, amount, paid) VALUES (%s,%s,%s)', 
                    (booking_id, amount_to_pay, 1))
        cur.execute('UPDATE bookings SET status="paid" WHERE id=%s', (booking_id,))
        db.commit()
        cur.close(); db.close()
        flash('Payment successful!')
        return redirect(url_for('mybookings'))

    return render_template('payment.html', booking=booking, amount_to_pay=amount_to_pay)

@app.route('/mybookings')
@login_required
def mybookings():
    rows = query_db('''
     SELECT b.*, t.title, t.price FROM bookings b
     JOIN tours t ON b.tour_id = t.id
     WHERE b.user_id = %s ORDER BY b.id DESC
    ''', (session['user_id'],))
    return render_template('mybookings.html', bookings=rows)

# --- ADMIN ROUTE (FIXED) ---
@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        db = mysql.connector.connect(**MYSQL_CONFIG)
        cur = db.cursor()
        
        if action == 'add_state':
            cur.execute("INSERT INTO states (state_name) VALUES (%s)", (request.form.get('state_name'),))
        
        elif action == 'add_city':
            cur.execute("INSERT INTO cities (state_id, city_name) VALUES (%s, %s)", 
                        (request.form.get('state_id'), request.form.get('city_name')))
        
        elif action == 'add_spot':
            try:
                # 1. Handle File Upload
                file = request.files.get('spot_image')
                fname = None
                
                if file and file.filename != '':
                    fname = secure_filename(file.filename)
                    # Ensure folder exists before saving
                    if not os.path.exists(app.config['UPLOAD_FOLDER']):
                        os.makedirs(app.config['UPLOAD_FOLDER'])
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                
                # 2. Insert into Database
                cur.execute("INSERT INTO master_spots (spot_name, city_id, image_url) VALUES (%s, %s, %s)",
                            (request.form.get('spot_name'), request.form.get('city_id'), fname))
                print("SUCCESS: Spot added to database!") # Check your terminal for this
                
            except Exception as e:
                print(f"ERROR ADDING SPOT: {e}") # This will tell you why it failed!
                flash(f"Error adding spot: {e}")
        
        elif action == 'add_tour':
            s_date, e_date = request.form.get('start_date'), request.form.get('end_date')
            if datetime.strptime(e_date, '%Y-%m-%d') <= datetime.strptime(s_date, '%Y-%m-%d'):
                flash("Error: End date must be after start date.")
            else:
                file = request.files.get('tour_image')
                t_fname = secure_filename(file.filename) if file else None
                if t_fname: file.save(os.path.join(app.config['UPLOAD_FOLDER'], t_fname))
                cur.execute("""INSERT INTO tours (title, description, price, start_date, end_date, start_point, end_point, image_path) 
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (request.form.get('title'), request.form.get('description'), request.form.get('price'), 
                             s_date, e_date, request.form.get('start_point'), request.form.get('end_point'), t_fname))
                t_id = cur.lastrowid
                spots, days = request.form.getlist('spots[]'), request.form.getlist('day_numbers[]')
                for idx, sid in enumerate(spots):
                    cur.execute("INSERT INTO tour_itinerary (tour_id, spot_id, order_sequence, day_number) VALUES (%s,%s,%s,%s)",
                                (t_id, sid, idx, days[idx]))
        db.commit(); cur.close(); db.close()

    # Consolidated GET data fetching
    data = {
        'states': query_db("SELECT * FROM states ORDER BY state_name ASC"),
        'cities': query_db("SELECT c.*, s.state_name FROM cities c JOIN states s ON c.state_id = s.id ORDER BY s.state_name, c.city_name"),
        'spots': query_db("SELECT ms.*, c.city_name FROM master_spots ms JOIN cities c ON ms.city_id = c.id ORDER BY c.city_name, ms.spot_name"),
        'tours': query_db("SELECT * FROM tours"),
        'bookings': query_db("""
            SELECT b.id, u.username, t.title as tour_title, b.date, b.status 
            FROM bookings b JOIN users u ON b.user_id=u.id JOIN tours t ON b.tour_id=t.id ORDER BY t.title ASC
        """)
    }
    return render_template('admin.html', **data)

# --- AUTH ROUTES ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        if request.form['confirm'] != password: flash('Passwords do not match'); return redirect(url_for('signup'))
        hashed = generate_password_hash(password)
        db = mysql.connector.connect(**MYSQL_CONFIG); cur = db.cursor()
        try:
            cur.execute('INSERT INTO users (username, password, is_admin) VALUES (%s, %s, 0)', (username, hashed))
            db.commit(); flash('Account created! Login now.'); return redirect(url_for('login'))
        except: flash('Username taken')
        finally: cur.close(); db.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = query_db('SELECT * FROM users WHERE username=%s', (request.form['username'],), one=True)
        if user and check_password_hash(user['password'], request.form['password']):
            session['user_id'], session['username'], session['is_admin'] = user['id'], user['username'], bool(user['is_admin'])
            return redirect(url_for('admin') if user['is_admin'] else url_for('home'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('home'))

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5001)