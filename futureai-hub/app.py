import os
import requests
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length, URL, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)

# Absolute path for SQLite DB
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "blog.db")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', f'sqlite:///{DB_PATH}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret key for session and CSRF - set securely in environment for production
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secure-key-here')

db = SQLAlchemy(app)

@app.context_processor
def inject_now():
    return {'datetime': datetime}

# Models
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

# Forms
class PostForm(FlaskForm):
    title = StringField('Title', validators=[InputRequired(), Length(max=200)])
    summary = TextAreaField('Summary', validators=[Length(max=300)])
    image_url = StringField('Image URL (optional)', validators=[Optional(), Length(max=300), URL(require_tld=False, message="Invalid URL")])
    body = TextAreaField('Content', validators=[InputRequired()])
    source_url = StringField('Source URL (optional)', validators=[Optional(), Length(max=350), URL(require_tld=False, message="Invalid URL")])
    submit = SubmitField('Publish')

# API keys loaded securely via environment variables or defaults
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', 'your_newsapi_key_here')
NEWSDATA_API_KEY = os.environ.get('NEWSDATA_API_KEY', 'pub_2b9b4717bfeb4d6e800bd5b91a8ddc61')
MEDIASTACK_KEY = os.environ.get('MEDIASTACK_KEY', '9dfd4c59b57df73b3bf47bf77bdd28f8')

# Gmail SMTP configuration - use env variables for security
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS', 'geopolitics.finance@gmail.com')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', 'Mayur@123')  # Remove spaces if any

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
    filtered = []
    last_empty = False
    for line in lines:
        if line == '':
            if not last_empty:
                filtered.append('')
            last_empty = True
        else:
            filtered.append(line)
            last_empty = False
    return '\n'.join(filtered)

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
                "source_name": "NewsAPI"
            }
    except Exception as e:
        print(f"NewsAPI fetch error: {e}")

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
                "source_name": "NewsData.io"
            }
    except Exception as e:
        print(f"NewsData.io fetch error: {e}")

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
                "source_name": "MediaStack"
            }
    except Exception as e:
        print(f"MediaStack fetch error: {e}")

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
                source_name=art.get('source_name', 'Unknown')
            )
            db.session.add(post)
            added += 1
    if added > 0:
        db.session.commit()
    print(f"[Scheduler] Imported {added} new articles.")

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
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

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
        print("No subscribers or posts to send.")
        return

    html_content = "<h2>Latest AI & Tech News from FutureAI Hub</h2><ul>"
    for post in latest_posts:
        link = url_for('post_detail', post_id=post.id, _external=True)
        html_content += f"<li><a href='{link}'>{post.title}</a> - {post.timestamp.strftime('%b %d')}</li>"
    html_content += "</ul><p>Thank you for subscribing!</p>"

    subject = "FutureAI Hub - Latest Newsletter"

    for subscriber in subscribers:
        send_email(subscriber.email, subject, html_content)

@app.route('/')
def home():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    recent_posts = posts
    return render_template("home.html", posts=posts, recent_posts=recent_posts)

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template("post.html", post=post)

@app.route('/admin/new', methods=['GET', 'POST'])
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        try:
            post = Post(
                title=form.title.data.strip(),
                summary=form.summary.data.strip(),
                image_url=form.image_url.data.strip() if form.image_url.data else None,
                body=form.body.data.strip(),
                source_url=form.source_url.data.strip() if form.source_url.data else None,
                is_imported=bool(form.source_url.data),
                source_name="Manual"
            )
            db.session.add(post)
            db.session.commit()
            flash("New article published!", "success")
            # Optionally send newsletter here if you want:
            # send_newsletter()
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating article: {str(e)}", "danger")
    return render_template("new_post.html", form=form)

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

    subscriber = Subscriber(email=email)
    db.session.add(subscriber)
    db.session.commit()
    send_welcome_email(email)
    return jsonify({'status': 'success', 'message': 'Subscription successful! Please check your inbox.'}), 200

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=import_external_articles, trigger='interval', hours=6, id='import_articles_task', replace_existing=True)
    # Uncomment next line to send newsletter daily at 8 am
    # scheduler.add_job(func=send_newsletter, trigger='cron', hour=8, id='send_newsletter_task')
    scheduler.start()
    print("[Scheduler] Scheduler started.")

with app.app_context():
    db.create_all()
    import_external_articles()

if __name__ == '__main__':
    with app.app_context():
        start_scheduler()
    app.run(debug=True)
