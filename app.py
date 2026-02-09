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

# ---------------- DATABASE ----------------
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

# ---------------- DECORATORS ----------------
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

# ---------------- HOME ----------------
@app.route('/')
def home():
    tours = query_db("SELECT * FROM tours LIMIT 3")
    return render_template('home.html', tours=tours)

@app.route('/tour')
def tour():
    search = request.args.get('search','')
    if search:
        tours = query_db("SELECT * FROM tours WHERE title LIKE %s",(f"%{search}%",))
    else:
        tours = query_db("SELECT * FROM tours")
    return render_template('tour.html', tours=tours, search=search)

# ---------------- BOOKING ----------------
@app.route('/booking/<int:tour_id>', methods=['GET','POST'])
@login_required
def booking(tour_id):

    tour = query_db("SELECT * FROM tours WHERE id=%s",(tour_id,),one=True)
    if not tour:
        abort(404)

    # already booked?
    existing_booking = query_db("""
        SELECT * FROM bookings
        WHERE user_id=%s AND tour_id=%s
    """,(session['user_id'],tour_id),one=True)

    readonly = False
    if existing_booking and existing_booking['status']=='paid':
        readonly = True

    if request.method=='POST' and not readonly:
        final_amount = request.form.get('final_amount')

        db = mysql.connector.connect(**MYSQL_CONFIG)
        cur = db.cursor()
        cur.execute("""
            INSERT INTO bookings(user_id,tour_id,date,status)
            VALUES(%s,%s,NOW(),'pending')
        """,(session['user_id'],tour_id))
        db.commit()
        booking_id = cur.lastrowid
        cur.close()
        db.close()

        return redirect(url_for('payment',booking_id=booking_id,amount=final_amount))

    itinerary = query_db("""
        SELECT ti.day_number, ms.spot_name, ms.image_url
        FROM tour_itinerary ti
        JOIN master_spots ms ON ti.spot_id = ms.id
        WHERE ti.tour_id=%s ORDER BY ti.day_number
    """,(tour_id,))

    return render_template('booking.html',tour=tour,itinerary=itinerary,readonly=readonly)

# ---------------- PAYMENT ----------------
@app.route('/payment/<int:booking_id>', methods=['GET','POST'])
@login_required
def payment(booking_id):

    booking = query_db("""
        SELECT b.*, t.price, t.title, t.start_date
        FROM bookings b
        JOIN tours t ON b.tour_id=t.id
        WHERE b.id=%s AND b.user_id=%s
    """,(booking_id,session['user_id']),one=True)

    if not booking:
        abort(404)

    custom_amount = request.args.get('amount')
    amount_to_pay = float(custom_amount) if custom_amount else float(booking['price'])

    base_price = float(booking['price'])
    extra_charges = max(0, amount_to_pay - base_price)

    if request.method=='POST':
        db = mysql.connector.connect(**MYSQL_CONFIG)
        cur = db.cursor()

        cur.execute(
            "INSERT INTO payments(booking_id,amount,paid) VALUES(%s,%s,1)",
            (booking_id,amount_to_pay)
        )

        cur.execute("UPDATE bookings SET status='paid' WHERE id=%s",(booking_id,))
        db.commit()
        cur.close()
        db.close()

        flash("Payment Successful! Your trip is confirmed.")
        return redirect(url_for('mybookings'))

    return render_template(
        'payment.html',
        booking=booking,
        amount_to_pay=amount_to_pay,
        base_price=base_price,
        extra_charges=extra_charges
    )

# ---------------- MY BOOKINGS ----------------
@app.route('/mybookings')
@login_required
def mybookings():
    rows = query_db("""
        SELECT b.id,b.date,b.status,b.tour_id,
               t.title,t.price,t.image_path,t.start_date
        FROM bookings b
        JOIN tours t ON b.tour_id=t.id
        WHERE b.user_id=%s
        ORDER BY b.id DESC
    """,(session['user_id'],))
    return render_template('mybookings.html',bookings=rows)

# ---------------- INVOICE ----------------
@app.route('/invoice/<int:booking_id>')
@login_required
def invoice(booking_id):
    booking = query_db("""
        SELECT b.*,t.title,t.price,t.start_date
        FROM bookings b
        JOIN tours t ON b.tour_id=t.id
        WHERE b.id=%s AND b.user_id=%s
    """,(booking_id,session['user_id']),one=True)

    if not booking:
        abort(404)

    return render_template('invoice.html',booking=booking)

# ---------------- ABOUT & CONTACT ----------------
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# ---------------- AUTH ----------------
@app.route('/signup',methods=['GET','POST'])
def signup():

    errors={}
    if request.method=='POST':

        full_name=request.form.get('full_name','').strip()
        email=request.form.get('email','').strip()
        phone=request.form.get('phone','').strip()
        password=request.form.get('password','')
        confirm=request.form.get('confirm','')

        if len(full_name)<3:
            errors['full_name']="Enter valid full name"

        if '@' not in email or '.' not in email:
            errors['email']="Enter valid email"

        if not phone.isdigit() or len(phone)!=10:
            errors['phone']="Enter valid 10 digit mobile"

        if password!=confirm:
            errors['confirm']="Passwords do not match"

        if len(password)<6:
            errors['password']="Password too weak"

        if errors:
            return render_template('signup.html',errors=errors)

        hashed=generate_password_hash(password)

        db=mysql.connector.connect(**MYSQL_CONFIG)
        cur=db.cursor()
        cur.execute("""
            INSERT INTO users(full_name,email,phone,password,is_admin)
            VALUES(%s,%s,%s,%s,0)
        """,(full_name,email,phone,hashed))
        db.commit()
        cur.close()
        db.close()

        return redirect(url_for('login'))

    return render_template('signup.html',errors={})

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        login_input=request.form['login']
        password=request.form['password']

        user=query_db(
            "SELECT * FROM users WHERE email=%s OR phone=%s",
            (login_input,login_input),one=True
        )

        if user and check_password_hash(user['password'],password):
            session['user_id']=user['id']
            session['username']=user['full_name']
            session['is_admin']=bool(user['is_admin'])
            return redirect(url_for('admin') if user['is_admin'] else url_for('home'))

        flash("Invalid email/phone or password")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ---------------- ADMIN ----------------
@app.route('/admin',methods=['GET','POST'])
@login_required
@admin_required
def admin():

    if request.method=='POST':
        action=request.form.get('action')
        db=mysql.connector.connect(**MYSQL_CONFIG)
        cur=db.cursor()

        if action=='add_state':
            cur.execute("INSERT INTO states(state_name) VALUES(%s)",(request.form.get('state_name'),))

        elif action=='add_city':
            cur.execute("INSERT INTO cities(state_id,city_name) VALUES(%s,%s)",
                        (request.form.get('state_id'),request.form.get('city_name')))

        elif action=='add_spot':
            file=request.files.get('spot_image')
            fname=None
            if file and file.filename!='':
                fname=secure_filename(file.filename)
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                file.save(os.path.join(app.config['UPLOAD_FOLDER'],fname))

            cur.execute("INSERT INTO master_spots(spot_name,city_id,image_url) VALUES(%s,%s,%s)",
                        (request.form.get('spot_name'),request.form.get('city_id'),fname))

        db.commit()
        cur.close()
        db.close()

    data={
        'states':query_db("SELECT * FROM states"),
        'cities':query_db("SELECT * FROM cities"),
        'spots':query_db("SELECT * FROM master_spots"),
        'tours':query_db("SELECT * FROM tours")
    }

    return render_template('admin.html',**data)

# ---------------- START SERVER ----------------
if __name__=='__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(host="0.0.0.0",port=5001,debug=True)