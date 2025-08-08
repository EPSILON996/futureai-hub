import os
import requests
from datetime import datetime
from flask import (
    Flask, render_template, redirect, url_for, flash,
    request, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, SubmitField
from wtforms.validators import (
    InputRequired, Length, URL, Optional,
    Email, EqualTo, ValidationError
)
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
import logging

# -----------------------------------------------------------
# Logging setup
logging.basicConfig(level=logging.INFO)

# Flask app setup
app = Flask(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "blog.db")

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', f'sqlite:///{DB_PATH}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secure-key-here')

db = SQLAlchemy(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_now():
    return {'datetime': datetime}

# -----------------------------------------------------------
# Models

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    name = db.Column(db.String(100))
    password = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(300))
    body = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(300))
    source_url = db.Column(db.String(350))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_imported = db.Column(db.Boolean, default=False)
    source_name = db.Column(db.String(80))

class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(256), unique=True, nullable=False)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)

# -----------------------------------------------------------
# Forms

class PostForm(FlaskForm):
    title = StringField('Title', validators=[InputRequired(), Length(max=200)])
    summary = TextAreaField('Summary', validators=[Length(max=300)])
    image_url = StringField('Image URL (optional)', validators=[Optional(), Length(max=300), URL(require_tld=False, message="Invalid URL")])
    body = TextAreaField('Content', validators=[InputRequired()])
    source_url = StringField('Source URL (optional)', validators=[Optional(), Length(max=350), URL(require_tld=False, message="Invalid URL")])
    submit = SubmitField('Publish')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[InputRequired(), Email(), Length(max=150)])
    password = PasswordField('Password', validators=[InputRequired()])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    email = StringField('Email', validators=[InputRequired(), Email(), Length(max=150)])
    name = StringField('Name', validators=[Length(max=100)])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6)])
    password_confirm = PasswordField('Confirm Password', validators=[InputRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data.lower()).first():
            raise ValidationError('Email already registered.')

# -----------------------------------------------------------
# API keys and SMTP credentials

NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', 'your_newsapi_key_here')
NEWSDATA_API_KEY = os.environ.get('NEWSDATA_API_KEY',  'your_newsapi_key_here')
MEDIASTACK_KEY = os.environ.get('MEDIASTACK_KEY',  'your_newsapi_key_here')

SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS', 'ENTER YOU GMAIL HERE')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', 'ENTER YOUR APP PASSWORD HERE')  # Gmail app password, no spaces

# -----------------------------------------------------------
# Utility functions

def clean_html_content(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(['script', 'style', 'iframe', 'noscript', 'header', 'footer']):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.insert_after("\n\n")
    text = soup.get_text(separator='', strip=True)
    lines = [line.strip() for line in text.splitlines()]
    filtered_lines = []
    last_empty = False
    for line in lines:
        if line == '':
            if not last_empty:
                filtered_lines.append('')
            last_empty = True
        else:
            filtered_lines.append(line)
            last_empty = False
    return '\n'.join(filtered_lines)

def fetch_newsapi_articles():
    url = f"https://newsapi.org/v2/top-headlines?category=technology&language=en&apiKey={NEWSAPI_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for art in data.get('articles', []):
            yield {
                "title": art.get("title", "Untitled")[:200],
                "summary": clean_html_content(art.get("description")),
                "body": clean_html_content(art.get("content") or art.get("description")),
                "image_url": art.get("urlToImage"),
                "source_url": art.get("url"),
                "source_name": "NewsAPI",
            }
    except Exception as e:
        logging.error(f"NewsAPI fetch error: {e}")

def fetch_newsdata_articles():
    url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&category=technology,science&language=en"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for art in data.get('results', []):
            yield {
                "title": art.get("title", "Untitled")[:200],
                "summary": clean_html_content(art.get("description")),
                "body": clean_html_content(art.get("content") or art.get("description")),
                "image_url": art.get("image_url") or art.get("image"),
                "source_url": art.get("link"),
                "source_name": "NewsData.io",
            }
    except Exception as e:
        logging.error(f"NewsData.io fetch error: {e}")

def fetch_mediastack_articles():
    url = f"http://api.mediastack.com/v1/news?access_key={MEDIASTACK_KEY}&categories=technology,science&languages=en"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for art in data.get('data', []):
            yield {
                "title": art.get("title", "Untitled")[:200],
                "summary": clean_html_content(art.get("description")),
                "body": clean_html_content(art.get("description")),
                "image_url": art.get("image"),
                "source_url": art.get("url"),
                "source_name": "MediaStack",
            }
    except Exception as e:
        logging.error(f"MediaStack fetch error: {e}")

def import_external_articles():
    added = 0
    for fetcher in [fetch_newsapi_articles, fetch_newsdata_articles, fetch_mediastack_articles]:
        if not fetcher:
            continue
        for art in fetcher():
            if not art:
                continue
            url = art.get('source_url')
            if not url or Post.query.filter_by(source_url=url).first():
                continue
            post = Post(
                title=art.get('title', "Untitled"),
                summary=art.get('summary') or "",
                body=art.get('body') or "",
                image_url=art.get('image_url'),
                source_url=url,
                timestamp=datetime.utcnow(),
                is_imported=True,
                source_name=art.get('source_name', 'Unknown'),
            )
            try:
                db.session.add(post)
                added += 1
            except Exception as e:
                logging.error(f"DB add post error: {e}")
    if added > 0:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"DB commit error: {e}")
    logging.info(f"[Scheduler] Imported {added} new articles.")



# -----------------------------------------------------------
# Email handling functions

def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()
        logging.info(f"Email sent to {to_email}")
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {e}")

def send_welcome_email(to_email):
    subject = "Welcome to FutureAI Hub Newsletter"
    body = """
        <h2>Thank you for subscribing!</h2>
        <p>You will now receive the latest AI & Tech news updates directly in your inbox.</p>
        <p>We look forward to keeping you informed!</p>
        <br>
        <p>— FutureAI Hub Team</p>
    """
    send_email(to_email, subject, body)

def send_newsletter():
    latest_posts = Post.query.order_by(Post.timestamp.desc()).limit(5).all()
    subscribers = Subscriber.query.all()
    if not subscribers or not latest_posts:
        logging.info("No subscribers or posts to send newsletter.")
        return

    html_content = "<h2>Latest AI & Tech News from FutureAI Hub</h2><ul>"
    for post in latest_posts:
        link = url_for('post_detail', post_id=post.id, _external=True)
        html_content += f"<li><a href='{link}'>{post.title}</a> - {post.timestamp.strftime('%b %d')}</li>"
    html_content += "</ul><p>Thank you for subscribing!</p>"

    subject = "FutureAI Hub - Latest Newsletter"

    for subscriber in subscribers:
        send_email(subscriber.email, subject, html_content)

# -----------------------------------------------------------
# Flask-Admin setup with access control

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    @login_required
    def index(self):
        if not current_user.is_admin:
            abort(403)
        return super().index()

class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

admin = Admin(app, name='FutureAI Admin', template_mode='bootstrap5', index_view=MyAdminIndexView())
admin.add_view(AdminModelView(Post, db.session))
admin.add_view(AdminModelView(Subscriber, db.session))
admin.add_view(AdminModelView(User, db.session))

# -----------------------------------------------------------
# Routes

@app.route('/')
def home():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    recent_posts = posts
    return render_template('home.html', posts=posts, recent_posts=recent_posts)

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/admin/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if not current_user.is_admin:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        try:
            post = Post(
                title=form.title.data.strip(),
                summary=form.summary.data.strip() if form.summary.data else None,
                image_url=form.image_url.data.strip() if form.image_url.data else None,
                body=form.body.data.strip(),
                source_url=form.source_url.data.strip() if form.source_url.data else None,
                is_imported=bool(form.source_url.data),
                source_name="Admin Manual"
            )
            db.session.add(post)
            db.session.commit()
            flash("New article published!", "success")
            # Uncomment below to send newsletter after new post
            # send_newsletter()
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating new post: {e}")
            flash(f"Error creating article: {str(e)}", "danger")
    return render_template('new_post.html', form=form)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    posts = []
    if query:
        posts = Post.query.filter(
            or_(
                Post.title.ilike(f"%{query}%"),
                Post.body.ilike(f"%{query}%")
            )
        ).order_by(Post.timestamp.desc()).all()
    recent_posts = Post.query.order_by(Post.timestamp.desc()).all()
    return render_template('search.html', posts=posts, query=query, recent_posts=recent_posts)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form.get('email', '').strip()
    if not email:
        return jsonify({'status': 'fail', 'message': 'Please provide an email address.'}), 400
    if Subscriber.query.filter_by(email=email).first():
        return jsonify({'status': 'fail', 'message': 'This email is already subscribed.'}), 400
    try:
        subscriber = Subscriber(email=email)
        db.session.add(subscriber)
        db.session.commit()
        send_welcome_email(email)
        return jsonify({'status': 'success', 'message': 'Subscription successful! Please check your inbox.'}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Subscription error for email {email}: {e}")
        return jsonify({'status': 'fail', 'message': 'Internal error occurred. Please try later.'}), 500

# Authentication Routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash("Logged in successfully.", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash("Invalid email or password.", "danger")
    return render_template('login.html', form=form)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = SignupForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=16)
        user = User(
            email=form.email.data.lower(),
            name=form.name.data.strip() if form.name.data else '',
            password=hashed_password,
            is_admin=False
        )
        try:
            db.session.add(user)
            db.session.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"Signup error: {e}")
            flash("Error creating account. Please try again.", "danger")
    return render_template('signup.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

# Error handlers

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Scheduler for periodic tasks

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(import_external_articles, 'interval', hours=6, id='import_articles_task', replace_existing=True)
    # Uncomment to schedule daily newsletter sending at 8am
    # scheduler.add_job(send_newsletter, 'cron', hour=8, id='newsletter_task')
    scheduler.start()
    logging.info("[Scheduler] Scheduler started.")

with app.app_context():
    db.create_all()
    import_external_articles()

if __name__ == '__main__':
    with app.app_context():
        start_scheduler()
    app.run(debug=True)  # Turn off debug=True in production


