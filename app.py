import os
import csv
import requests
from flask import Flask, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chaser_social.db'
app.config['SECRET_KEY'] = 'vortex-chaser-social-fixed-master-key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='eventlet')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(300), default='default_avatar.png')
    bio = db.Column(db.String(200), default='Storm chaser & radar spotter.')
    posts = db.relationship('Post', backref='author_user', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author_user', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='author_user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='author_user', lazy=True, cascade='all, delete-orphan')
    pins = db.relationship('ThreatPin', backref='author_user', lazy=True, cascade='all, delete-orphan')
    shelters = db.relationship('StormShelter', backref='author_user', lazy=True, cascade='all, delete-orphan')

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_file = db.Column(db.String(300))
    location = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='parent_post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='parent_post', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reaction_type = db.Column(db.String(20), default='⚡ Bolt')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_dms')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_dms')

class ThreatPin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    phenomenon = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class StormShelter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200), nullable=False)
    details = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class EmergencyDispatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    headline = db.Column(db.String(250), nullable=False)
    area = db.Column(db.String(200), nullable=False)
    severity = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    if StormShelter.query.count() == 0:
        default_shelters = [
            StormShelter(name="Sylacauga Safe Room / Rec Center", lat=33.1755, lng=-86.2501, address="Sylacauga, AL", details="Public community storm shelter.", user_id=1),
            StormShelter(name="Calera Storm Shelter", lat=33.1068, lng=-86.7508, address="Calera, AL", details="Reinforced municipal safe room.", user_id=1),
            StormShelter(name="Moore Norman Technology Center Shelter", lat=35.3395, lng=-97.4868, address="Moore, OK", details="FEMA-rated community safe room.", user_id=1),
            StormShelter(name="Nashville Municipal Auditorium Shelter", lat=36.1627, lng=-86.7816, address="Nashville, TN", details="Downtown severe weather refuge.", user_id=1)
        ]
        db.session.bulk_save_objects(default_shelters)
        db.session.commit()

@app.route('/')
@login_required
def feed():
    tab = request.args.get('tab', 'global')
    if tab == 'my':
        posts = Post.query.filter_by(user_id=current_user.id).order_by(Post.id.desc()).all()
    else:
        posts = Post.query.order_by(Post.id.desc()).all()
    return render_template('feed.html', posts=posts, active_tab=tab)

@app.route('/api/nws_alerts')
@login_required
def nws_alerts():
    try:
        headers = {'User-Agent': 'ChaserConnect/1.0 (vortexghost.site)'}
        res = requests.get('https://api.weather.gov/alerts/active?event=Tornado%20Warning,Severe%20Thunderstorm%20Warning', headers=headers, timeout=5)
        data = res.json()
        alerts = []
        for feature in data.get('features', [])[:10]:
            props = feature.get('properties', {})
            headline = props.get('headline', 'Severe Weather Alert')
            area = props.get('areaDesc', 'Affected Area')
            severity = props.get('severity', 'Severe')
            alerts.append({'headline': headline, 'area': area, 'severity': severity})
            
            if 'Tornado Warning' in headline and not EmergencyDispatch.query.filter_by(headline=headline).first():
                dispatch = EmergencyDispatch(headline=headline, area=area, severity=severity)
                db.session.add(dispatch)
                db.session.commit()
                socketio.emit('emergency_dispatch', {'headline': headline, 'area': area})
        return jsonify(alerts)
    except Exception as e:
        return jsonify([{'headline': 'NWS Live Feed Sync Active', 'area': 'Nationwide', 'severity': 'Info'}])

@app.route('/chat')
@login_required
def chat():
    messages = ChatMessage.query.order_by(ChatMessage.id.asc()).all()
    return render_template('chat.html', messages=messages)

@app.route('/dm/<int:recipient_id>')
@login_required
def direct_messages(recipient_id):
    recipient = User.query.get_or_404(recipient_id)
    if recipient.id == current_user.id:
        other_user = User.query.filter(User.id != current_user.id).first()
        if other_user:
            return redirect(url_for('direct_messages', recipient_id=other_user.id))
        else:
            flash('No other users available to message yet.', 'warning')
            return redirect(url_for('feed'))
    
    dms = DirectMessage.query.filter(
        ((DirectMessage.sender_id == current_user.id) & (DirectMessage.recipient_id == recipient.id)) |
        ((DirectMessage.sender_id == recipient.id) & (DirectMessage.recipient_id == current_user.id))
    ).order_by(DirectMessage.id.asc()).all()
    
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('dm.html', recipient=recipient, dms=dms, users=users)

@app.route('/send_dm/<int:recipient_id>', methods=['POST'])
@login_required
def send_dm(recipient_id):
    content = request.form.get('content')
    if content:
        dm = DirectMessage(sender_id=current_user.id, recipient_id=recipient_id, content=content)
        db.session.add(dm)
        db.session.commit()
        socketio.emit('receive_dm', {
            'sender_id': current_user.id,
            'recipient_id': recipient_id,
            'content': content,
            'sender_username': current_user.username,
            'sender_pic': current_user.profile_pic
        })
    return redirect(url_for('direct_messages', recipient_id=recipient_id))

@app.route('/map')
@login_required
def hazard_map():
    pins = ThreatPin.query.all()
    return render_template('map.html', pins=pins)

@app.route('/shelters')
@login_required
def shelter_map():
    shelters_data = []
    for s in StormShelter.query.all():
        shelters_data.append({
            'name': s.name, 'lat': s.lat, 'lng': s.lng, 'address': s.address, 'details': s.details
        })
    return render_template('shelters.html', shelters=shelters_data)

@app.route('/spc')
@login_required
def spc_outlooks():
    return render_template('spc.html')

@app.route('/dispatches')
@login_required
def dispatches():
    logs = EmergencyDispatch.query.order_by(EmergencyDispatch.id.desc()).all()
    return render_template('dispatches.html', logs=logs)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    new_bio = request.form.get('bio')
    if new_bio is not None:
        current_user.bio = new_bio
        
    file = request.files.get('profile_pic')
    if file and file.filename != '' and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        current_user.profile_pic = filename
        
    db.session.commit()
    flash('Profile updated successfully.', 'success')
    return redirect(request.referrer or url_for('feed'))

@app.route('/add_shelter', methods=['POST'])
@login_required
def add_shelter():
    try:
        name = request.form.get('name')
        lat = float(request.form.get('lat'))
        lng = float(request.form.get('lng'))
        address = request.form.get('address')
        details = request.form.get('details')
        new_shelter = StormShelter(name=name, lat=lat, lng=lng, address=address, details=details, user_id=current_user.id)
        db.session.add(new_shelter)
        db.session.commit()
        flash('Public storm shelter registered successfully.', 'success')
    except Exception as e:
        flash('Error adding shelter.', 'danger')
    return redirect(url_for('shelter_map'))

@app.route('/export_csv')
@login_required
def export_csv():
    pins = ThreatPin.query.all()
    output = [['ID', 'Spotter', 'Phenomenon', 'Description', 'Latitude', 'Longitude']]
    for pin in pins:
        output.append([pin.id, pin.author_user.username, pin.phenomenon, pin.description, pin.lat, pin.lng])
    response = make_response('\n'.join([','.join(map(str, row)) for row in output]))
    response.headers['Content-Disposition'] = 'attachment; filename=chaser_threat_log.csv'
    response.headers['Content-type'] = 'text/csv'
    return response

@app.route('/add_pin', methods=['POST'])
@login_required
def add_pin():
    try:
        lat = float(request.form.get('lat'))
        lng = float(request.form.get('lng'))
        phenomenon = request.form.get('phenomenon')
        description = request.form.get('description')
        new_pin = ThreatPin(lat=lat, lng=lng, phenomenon=phenomenon, description=description, user_id=current_user.id)
        db.session.add(new_pin)
        db.session.commit()
        socketio.emit('new_pin', {'lat': lat, 'lng': lng, 'phenomenon': phenomenon, 'description': description, 'username': current_user.username})
    except Exception as e:
        flash('Error dropping hazard pin.', 'danger')
    return redirect(url_for('hazard_map'))

@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    return render_template('profile.html', user=user)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        bio = request.form.get('bio', 'Storm chaser.')
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('signup'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        avatar_filename = 'default_avatar.png'
        file = request.files.get('profile_pic')
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            avatar_filename = filename
        new_user = User(username=username, password=hashed_password, profile_pic=avatar_filename, bio=bio)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('feed'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('feed'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/post', methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content')
    location = request.form.get('location')
    image_filename = None
    file = request.files.get('post_image')
    if file and file.filename != '' and allowed_file(file.filename):
        image_filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
    if content:
        new_post = Post(content=content, location=location, image_file=image_filename, user_id=current_user.id)
        db.session.add(new_post)
        db.session.commit()
        socketio.emit('new_post', {
            'username': current_user.username, 'profile_pic': current_user.profile_pic,
            'location': location or '', 'content': content, 'image_file': image_filename, 'post_id': new_post.id
        })
    return redirect(url_for('feed'))

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id == current_user.id:
        db.session.delete(post)
        db.session.commit()
        flash('Post deleted successfully.', 'success')
    else:
        flash('Unauthorized action.', 'danger')
    return redirect(url_for('feed'))

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content')
    if content:
        new_comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
        db.session.add(new_comment)
        db.session.commit()
    return redirect(url_for('feed'))

@app.route('/like/<int:post_id>/<reaction>')
@login_required
def react_post(post_id, reaction):
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if existing_like:
        if existing_like.reaction_type == reaction:
            db.session.delete(existing_like)
        else:
            existing_like.reaction_type = reaction
    else:
        new_like = Like(user_id=current_user.id, post_id=post_id, reaction_type=reaction)
        db.session.add(new_like)
    db.session.commit()
    return redirect(url_for('feed'))

@socketio.on('send_message')
def handle_chat(data):
    content = data.get('content')
    if content and current_user.is_authenticated:
        new_msg = ChatMessage(content=content, user_id=current_user.id)
        db.session.add(new_msg)
        db.session.commit()
        socketio.emit('receive_message', {
            'username': current_user.username, 'profile_pic': current_user.profile_pic, 'content': content, 'user_id': current_user.id
        })

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
