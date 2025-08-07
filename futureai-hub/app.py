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

# Absolute path for SQLite DB – ensure same DB used everywhere to avoid "no such table" errors
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "blog.db")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', f'sqlite:///{DB_PATH}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret key for session and CSRF protection; set via env var in production
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secure-key-here')

db = SQLAlchemy(app)

@app.context_processor
def inject_now():
    return {'datetime': datetime}

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

class PostForm(FlaskForm):
    title = StringField('Title', validators=[InputRequired(), Length(max=200)])
    summary = TextAreaField('Summary', validators=[Length(max=300)])
    image_url = StringField('Image URL (optional)', validators=[Optional(), Length(max=300), URL(require_tld=False, message="Invalid URL")])
    body = TextAreaField('Content', validators=[InputRequired()])
    source_url = StringField('Source URL (optional)', validators=[Optional(), Length(max=350), URL(require_tld=False, message="Invalid URL")])
    submit = SubmitField('Publish')

# API Keys from environment variables; replace with valid keys before deployment
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '19d39af2cccc4fa0b3c70728bdc4f114')
NEWSDATA_API_KEY = os.environ.get('NEWSDATA_API_KEY', 'pub_37394367ea33be6bbe3bd4d040f6f79d3a0d')
MEDIASTACK_KEY = os.environ.get('MEDIASTACK_KEY', '4fc7273b6b7b544697d35a6817135fdf')
GUARDIAN_KEY = os.environ.get('GUARDIAN_KEY', 'd53ef06b-46c1-4273-8c83-77c51dc07696')

def clean_html_content(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    # Remove unwanted tags
    for tag in soup(['script', 'style', 'iframe', 'noscript', 'header', 'footer']):
        tag.decompose()
    # Preserve paragraphs as line breaks
    text = ''
    for elem in soup.find_all(['p', 'br']):
        elem.append('\n')
    text = soup.get_text(separator='\n', strip=True)
    # Clean multiple blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)

def fetch_newsapi_articles():
    url = f"https://newsapi.org/v2/top-headlines?category=technology&language=en&apiKey={NEWSAPI_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for art in data.get('articles', []):
            yield {
                "title": art.get("title")[:200] if art.get("title") else "Untitled",
                "summary": clean_html_content(art.get("description")),
                "body": clean_html_content(art.get("content") or art.get("description")),
                "image_url": art.get("urlToImage"),
                "source_url": art.get("url"),
                "source_name": "NewsAPI",
            }
    except Exception as e:
        yield {"title": f"Error NewsAPI: {str(e)}", "summary": "", "body": "", "source_name": "NewsAPI"}

def fetch_newsdata_articles():
    url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&category=technology,science&language=en"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for art in data.get('results', []):
            yield {
                "title": art.get("title", "")[:200] or "Untitled",
                "summary": clean_html_content(art.get("description")),
                "body": clean_html_content(art.get("content") or art.get("description")),
                "image_url": art.get("image_url") or art.get("image"),
                "source_url": art.get("link"),
                "source_name": "NewsData.io",
            }
    except Exception as e:
        yield {"title": f"Error NewsData.io: {str(e)}", "summary": "", "body": "", "source_name": "NewsData.io"}

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
                "source_name": "Mediastack",
            }
    except Exception as e:
        yield {"title": f"Error Mediastack: {str(e)}", "summary": "", "body": "", "source_name": "Mediastack"}

def fetch_guardian_articles():
    url = f"https://content.guardianapis.com/search?q=AI+OR+technology&api-key={GUARDIAN_KEY}&show-fields=thumbnail,trailText,body&order-by=newest"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for art in data.get('response', {}).get('results', []):
            fields = art.get('fields', {})
            yield {
                "title": art.get('webTitle', '')[:200] or "Untitled",
                "summary": clean_html_content(fields.get('trailText')),
                "body": clean_html_content(fields.get('body') or fields.get('trailText')),
                "image_url": fields.get('thumbnail'),
                "source_url": art.get('webUrl'),
                "source_name": "The Guardian",
            }
    except Exception as e:
        yield {"title": f"Error Guardian: {str(e)}", "summary": "", "body": "", "source_name": "The Guardian"}

def import_external_articles():
    added = 0
    for fetcher in [fetch_newsapi_articles, fetch_newsdata_articles, fetch_mediastack_articles, fetch_guardian_articles]:
        for art in fetcher():
            url = art.get('source_url')
            if not url or Post.query.filter_by(source_url=url).first():
                continue
            post = Post(
                title=art.get('title', 'Untitled'),
                summary=art.get('summary') or '',
                body=art.get('body') or '',
                image_url=art.get('image_url'),
                source_url=url,
                timestamp=datetime.utcnow(),
                is_imported=True,
                source_name=art.get('source_name', 'unknown')
            )
            db.session.add(post)
            added += 1
    if added > 0:
        db.session.commit()
    print(f"[Scheduler] Imported {added} new articles from all sources.")

@app.route('/')
def home():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    recent_posts = Post.query.order_by(Post.timestamp.desc()).limit(5).all()
    return render_template('home.html', posts=posts, recent_posts=recent_posts)

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/admin/new', methods=['GET', 'POST'])
def new_post():
    form = PostForm()
    if form.validate_on_submit():
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
        flash('New article published!', 'success')
        return redirect(url_for('home'))
    return render_template('new_post.html', form=form)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    posts = []
    if query:
        posts = Post.query.filter(
            or_(
                Post.title.ilike(f'%{query}%'),
                Post.body.ilike(f'%{query}%')
            )
        ).order_by(Post.timestamp.desc()).all()
    recent_posts = Post.query.order_by(Post.timestamp.desc()).limit(5).all()
    return render_template('search.html', posts=posts, query=query, recent_posts=recent_posts)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=import_external_articles,
        trigger='interval',
        hours=6,
        id='import_articles_task',
        replace_existing=True
    )
    scheduler.start()
    print("[Scheduler] Article updater started.")

# Initialize tables and import on every app start
with app.app_context():
    db.create_all()
    import_external_articles()

if __name__ == '__main__':
    with app.app_context():
        start_scheduler()
    app.run(debug=True)
