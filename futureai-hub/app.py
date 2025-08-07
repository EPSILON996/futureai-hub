import os
import requests
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length, URL, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_
from bs4 import BeautifulSoup

app = Flask(__name__)

# === DB Setup (absolute path for SQLite DB) ===
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "blog.db")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', f"sqlite:///{DB_PATH}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secure-key')

db = SQLAlchemy(app)

@app.context_processor
def inject_now():
    return {'datetime': datetime}

# === Models ===
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

# === Forms ===
class PostForm(FlaskForm):
    title = StringField('Title', validators=[InputRequired(), Length(max=200)])
    summary = TextAreaField('Summary', validators=[Length(max=300)])
    image_url = StringField('Image URL', validators=[Optional(), Length(max=300), URL(require_tld=False, message="Invalid URL")])
    body = TextAreaField('Content', validators=[InputRequired()])
    source_url = StringField('Source URL', validators=[Optional(), Length(max=350), URL(require_tld=False, message="Invalid URL")])
    submit = SubmitField('Publish')

# === API Keys ===
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '19b471bfebfb...')  # Replace with your key if needed
NEWSDATA_API_KEY = 'pub_2b471bfebf...61'  # Your provided NewsData.io key
MEDIASTACK_KEY = os.environ.get('MEDIASTACK_KEY', '4fc727bfeb...')  # Existing
# GUARDIAN_API_DISABLED — Guardian is deactivated (no key or calls)

# === Helper: Clean HTML content to readable plain text preserving paragraphs ===
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
        if not line:
            if not last_empty:
                filtered_lines.append('')
            last_empty = True
        else:
            filtered_lines.append(line)
            last_empty = False
    return '\n'.join(filtered_lines)

# === API Fetchers ===
def fetch_newsapi_articles():
    url = f"https://newsapi.org/v2/top-headlines?category=technology&language=en&apiKey={NEWSAPI_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for article in data.get("articles", []):
            yield dict(
                title=article.get("title", "No title")[:200],
                summary=clean_html_content(article.get("description")),
                body=clean_html_content(article.get("content") or article.get("description")),
                image_url=article.get("urlToImage"),
                source_url=article.get("url"),
                source_name="NewsAPI"
            )
    except Exception as e:
        yield dict(
            title=f"Error fetching NewsAPI articles: {e}",
            summary="",
            body="",
            source_url=None,
            image_url=None,
            source_name="NewsAPI"
        )

def fetch_newsdata_articles():
    url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&category=technology,science&language=en"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for article in data.get("results", []):
            yield dict(
                title=article.get("title", "No title")[:200],
                summary=clean_html_content(article.get("description")),
                body=clean_html_content(article.get("content") or article.get("description")),
                image_url=article.get("image_url") or article.get("image"),
                source_url=article.get("link"),
                source_name="NewsData.io"
            )
    except Exception as e:
        yield dict(
            title=f"Error fetching NewsData.io articles: {e}",
            summary="",
            body="",
            source_url=None,
            image_url=None,
            source_name="NewsData.io"
        )

def fetch_mediastack_articles():
    url = f"http://api.mediastack.com/v1/news?access_key={MEDIASTACK_KEY}&categories=technology,science&languages=en"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for article in data.get("data", []):
            yield dict(
                title=article.get("title", "No title")[:200],
                summary=clean_html_content(article.get("description")),
                body=clean_html_content(article.get("description")),
                image_url=article.get("image"),
                source_url=article.get("url"),
                source_name="MediaStack"
            )
    except Exception as e:
        yield dict(
            title=f"Error fetching MediaStack articles: {e}",
            summary="",
            body="",
            source_url=None,
            image_url=None,
            source_name="MediaStack"
        )

# Note: Guardian API is deactivated as requested — no fetch_guardian_articles()

# === Importer function: loops over enabled sources only ===
def import_external_articles():
    added = 0
    for fetcher in [fetch_newsapi_articles, fetch_newsdata_articles, fetch_mediastack_articles]:
        for article in fetcher():
            source_url = article.get("source_url")
            if not source_url:
                continue
            exists = Post.query.filter_by(source_url=source_url).first()
            if exists:
                continue
            post = Post(
                title=article.get("title", "No title"),
                summary=article.get("summary") or "",
                body=article.get("body") or "",
                image_url=article.get("image_url"),
                source_url=source_url,
                timestamp=datetime.utcnow(),
                is_imported=True,
                source_name=article.get("source_name", "Unknown")
            )
            db.session.add(post)
            added += 1
    if added:
        db.session.commit()
    print(f"[Scheduler] Imported {added} new articles.")

# === Flask routes ===
@app.route("/")
def home():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    recent_posts = Post.query.order_by(Post.timestamp.desc()).limit(5).all()
    return render_template("home.html", posts=posts, recent_posts=recent_posts)

@app.route("/post/<int:post_id>")
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template("post.html", post=post)

@app.route("/admin/new", methods=["GET", "POST"])
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(
            title=form.title.data.strip(),
            summary=form.summary.data.strip(),
            body=form.body.data.strip(),
            image_url=form.image_url.data.strip() if form.image_url.data else None,
            source_url=form.source_url.data.strip() if form.source_url.data else None,
            is_imported=bool(form.source_url.data),
            source_name="Manual"
        )
        db.session.add(post)
        db.session.commit()
        flash("Article successfully posted!", "success")
        return redirect(url_for("home"))
    return render_template("new_post.html", form=form)

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    posts = []
    if query:
        posts = Post.query.filter(
            or_(
                Post.title.ilike(f"%{query}%"),
                Post.body.ilike(f"%{query}%"),
            )
        ).order_by(Post.timestamp.desc()).all()
    recent_posts = Post.query.order_by(Post.timestamp.desc()).limit(5).all()
    return render_template("search.html", posts=posts, query=query, recent_posts=recent_posts)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# Scheduler - runs import every 6 hours
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=import_external_articles,
        trigger="interval",
        hours=6,
        id="import_articles_task",
        replace_existing=True,
    )
    scheduler.start()
    print("[Scheduler] Started article updater task.")

# Initialize DB and import on startup
with app.app_context():
    db.create_all()
    import_external_articles()

if __name__ == "__main__":
    with app.app_context():
        start_scheduler()
    app.run(debug=True)
