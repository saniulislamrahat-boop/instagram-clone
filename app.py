import os
import uuid
import time
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)

# --------------------------------------------------
# Flask App Configuration
# --------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-before-deploying")

# Database Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///instagram.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Upload Configuration
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy()
db.init_app(app)

# --------------------------------------------------
# Flask Login Setup
# --------------------------------------------------

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# --------------------------------------------------
# Database Models
# --------------------------------------------------

class User(UserMixin, db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    bio = db.Column(
        db.Text,
        default=""
    )

    profile_image_filename = db.Column(db.String(255), nullable=True)


class Post(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    image_filename = db.Column(
        db.String(255),
        nullable=False
    )

    caption = db.Column(
        db.Text,
        default=""
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "posts",
            lazy=True,
            order_by="Post.created_at.desc()"
        )
    )

# --------------------------------------------------
# Flask Login User Loader
# --------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


class Reaction(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="unique_user_post_reaction"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    reaction_type = db.Column(db.String(16), nullable=False)

    user = db.relationship("User", backref=db.backref("reactions", lazy=True))
    post = db.relationship("Post", backref=db.backref("reactions", lazy=True, cascade="all, delete-orphan"))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    body = db.Column(db.String(1000), nullable=False, default="")
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])


class Follow(db.Model):
    __table_args__ = (db.UniqueConstraint("follower_id", "followed_id", name="unique_follow"),)

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class FriendRequest(db.Model):
    __table_args__ = (db.UniqueConstraint("sender_id", "recipient_id", name="unique_friend_request"),)

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    status = db.Column(db.String(16), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    image_filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(500), default="", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship("User", backref=db.backref("stories", lazy=True))


# Create every declared table, then safely add columns for existing SQLite data.
with app.app_context():
    db.create_all()
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    if "profile_image_filename" not in user_columns:
        db.session.execute(text("ALTER TABLE user ADD COLUMN profile_image_filename VARCHAR(255)"))
        db.session.commit()
    message_columns = {column["name"] for column in inspect(db.engine).get_columns("message")}
    if "image_filename" not in message_columns:
        db.session.execute(text("ALTER TABLE message ADD COLUMN image_filename VARCHAR(255)"))
        db.session.commit()


def is_valid_image(file_storage):
    """Check common image file signatures instead of trusting the extension."""
    header = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.startswith((b"GIF87a", b"GIF89a"))
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )


def save_image(file_storage):
    """Validate and save an image upload, returning its generated filename."""
    if file_storage is None or not file_storage.filename:
        return None, "Please choose an image to upload."
    if not allowed_file(file_storage.filename):
        return None, "Unsupported file type. Use png, jpg, jpeg, gif, or webp."
    if not is_valid_image(file_storage):
        return None, "The uploaded file is not a valid image."
    original_name = secure_filename(file_storage.filename)
    if not original_name:
        return None, "Please choose a file with a valid name."
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
    return unique_name, None


def reaction_data(posts):
    """Return totals and the current user's selection for each post."""
    post_ids = [post.id for post in posts]
    data = {post_id: {"counts": {}, "mine": None} for post_id in post_ids}
    if not post_ids:
        return data
    reactions = Reaction.query.filter(Reaction.post_id.in_(post_ids)).all()
    for reaction in reactions:
        entry = data[reaction.post_id]
        entry["counts"][reaction.reaction_type] = entry["counts"].get(reaction.reaction_type, 0) + 1
        if reaction.user_id == current_user.id:
            entry["mine"] = reaction.reaction_type
    return data


def conversation_messages(other_user_id, after_id=0):
    return Message.query.filter(
        Message.id > after_id,
        db.or_(
            db.and_(Message.sender_id == current_user.id, Message.recipient_id == other_user_id),
            db.and_(Message.sender_id == other_user_id, Message.recipient_id == current_user.id),
        ),
    ).order_by(Message.id.asc()).all()


def message_json(message):
    return {
        "id": message.id,
        "body": message.body,
        "sender_id": message.sender_id,
        "created_at": message.created_at.isoformat(),
        "image_url": url_for("static", filename="uploads/" + message.image_filename)
        if message.image_filename else None,
    }


def friend_statuses(users):
    user_ids = [user.id for user in users]
    result = {user_id: None for user_id in user_ids}
    if not user_ids:
        return result
    requests = FriendRequest.query.filter(
        db.or_(
            db.and_(FriendRequest.sender_id == current_user.id, FriendRequest.recipient_id.in_(user_ids)),
            db.and_(FriendRequest.recipient_id == current_user.id, FriendRequest.sender_id.in_(user_ids)),
        )
    ).all()
    for item in requests:
        other_id = item.recipient_id if item.sender_id == current_user.id else item.sender_id
        if item.status == "accepted":
            result[other_id] = "friends"
        elif item.sender_id == current_user.id:
            result[other_id] = "sent"
        else:
            result[other_id] = "received"
    return result


def validate_registration(username, email, password):
    if not 3 <= len(username) <= 50 or not username.replace("_", "").isalnum():
        return "Username must be 3–50 characters and use only letters, numbers, or underscores."
    if not 3 <= len(email) <= 100 or "@" not in email.rsplit(".", 1)[0]:
        return "Please enter a valid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    return None

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("feed"))
    return redirect(url_for("login"))

# --------------------------------------------------
# Register
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        validation_error = validate_registration(username, email, password)
        if validation_error:
            return render_template("register.html", error=validation_error), 400

        # Username Check
        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:
            return render_template("register.html", error="Username already exists!")

        # Email Check
        existing_email = User.query.filter_by(
            email=email
        ).first()

        if existing_email:
            return render_template("register.html", error="Email already exists!")

        # Password Hashing
        hashed_password = generate_password_hash(password)

        # Create User
        new_user = User(
            username=username,
            email=email,
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        return render_template("login.html", success="Account created! You can log in now.")

    return render_template("register.html")

# --------------------------------------------------
# Login
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(
            user.password,
            password
        ):

            login_user(user)

            return redirect(
                url_for("feed")
            )

        return render_template("login.html", error="Invalid username or password!")

    return render_template("login.html")

# --------------------------------------------------
# Profile
# --------------------------------------------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    if request.method == "POST":
        image = request.files.get("profile_image")
        filename, error = save_image(image)
        if error:
            return render_template("profile.html", user=current_user, posts=current_user.posts, error=error,
                                   following_count=Follow.query.filter_by(follower_id=current_user.id).count(),
                                   follower_count=Follow.query.filter_by(followed_id=current_user.id).count(),
                                   friend_count=FriendRequest.query.filter(
                                       FriendRequest.status == "accepted",
                                       db.or_(FriendRequest.sender_id == current_user.id,
                                              FriendRequest.recipient_id == current_user.id),
                                   ).count()), 400
        old_filename = current_user.profile_image_filename
        current_user.profile_image_filename = filename
        db.session.commit()
        if old_filename:
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        return redirect(url_for("profile"))

    posts = Post.query.filter_by(
        user_id=current_user.id
    ).order_by(Post.created_at.desc()).all()

    following_count = Follow.query.filter_by(follower_id=current_user.id).count()
    follower_count = Follow.query.filter_by(followed_id=current_user.id).count()
    friend_count = FriendRequest.query.filter(
        FriendRequest.status == "accepted",
        db.or_(FriendRequest.sender_id == current_user.id, FriendRequest.recipient_id == current_user.id),
    ).count()
    return render_template(
        "profile.html",
        user=current_user,
        posts=posts,
        following_count=following_count,
        follower_count=follower_count,
        friend_count=friend_count,
    )

# --------------------------------------------------
# Feed
# --------------------------------------------------

@app.route("/feed")
@login_required
def feed():

    posts = Post.query.order_by(
        Post.created_at.desc()
    ).all()

    stories = Story.query.filter(Story.expires_at > datetime.utcnow()).order_by(Story.created_at.desc()).all()
    return render_template(
        "feed.html",
        posts=posts,
        reaction_data=reaction_data(posts),
        stories=stories,
    )


@app.route("/people")
@login_required
def people():
    users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    followed_ids = {item.followed_id for item in Follow.query.filter_by(follower_id=current_user.id).all()}
    return render_template("people.html", users=users, followed_ids=followed_ids,
                           friend_status=friend_statuses(users))


@app.post("/follow/<int:user_id>")
@login_required
def toggle_follow(user_id):
    if user_id == current_user.id or db.session.get(User, user_id) is None:
        abort(404)
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if follow:
        db.session.delete(follow)
    else:
        db.session.add(Follow(follower_id=current_user.id, followed_id=user_id))
    db.session.commit()
    return redirect(request.referrer or url_for("people"))


@app.post("/friend/<int:user_id>")
@login_required
def friend_request(user_id):
    if user_id == current_user.id or db.session.get(User, user_id) is None:
        abort(404)
    outgoing = FriendRequest.query.filter_by(sender_id=current_user.id, recipient_id=user_id).first()
    incoming = FriendRequest.query.filter_by(sender_id=user_id, recipient_id=current_user.id).first()
    if incoming and incoming.status == "pending":
        incoming.status = "accepted"
    elif outgoing and outgoing.status == "pending":
        db.session.delete(outgoing)
    elif not outgoing and not incoming:
        db.session.add(FriendRequest(sender_id=current_user.id, recipient_id=user_id))
    db.session.commit()
    return redirect(request.referrer or url_for("people"))


@app.route("/stories", methods=["GET", "POST"])
@login_required
def stories():
    if request.method == "POST":
        caption = request.form.get("caption", "").strip()
        if len(caption) > 500:
            return render_template("stories.html", stories=[], error="Story captions can be at most 500 characters."), 400
        image_filename, error = save_image(request.files.get("image"))
        if error:
            return render_template("stories.html", stories=[], error=error), 400
        db.session.add(Story(user_id=current_user.id, image_filename=image_filename, caption=caption,
                             expires_at=datetime.utcnow() + timedelta(hours=24)))
        db.session.commit()
        return redirect(url_for("stories"))
    active_stories = Story.query.filter(Story.expires_at > datetime.utcnow()).order_by(Story.created_at.desc()).all()
    return render_template("stories.html", stories=active_stories)


@app.post("/post/<int:post_id>/reaction")
@login_required
def react_to_post(post_id):
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404)
    reaction_type = request.form.get("reaction_type", "")
    if reaction_type not in {"like", "love"}:
        abort(400)
    reaction = Reaction.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if reaction and reaction.reaction_type == reaction_type:
        db.session.delete(reaction)
    elif reaction:
        reaction.reaction_type = reaction_type
    else:
        db.session.add(Reaction(user_id=current_user.id, post_id=post_id, reaction_type=reaction_type))
    db.session.commit()
    return redirect(request.referrer or url_for("feed"))


@app.route("/messages")
@login_required
def messages():
    users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    return render_template("messages.html", users=users)


@app.route("/messages/<int:user_id>")
@login_required
def conversation(user_id):
    other_user = db.session.get(User, user_id)
    if other_user is None or other_user.id == current_user.id:
        abort(404)
    initial_messages = conversation_messages(user_id)
    return render_template("conversation.html", other_user=other_user, messages=initial_messages)


@app.route("/api/messages/<int:user_id>", methods=["GET", "POST"])
@login_required
def message_api(user_id):
    other_user = db.session.get(User, user_id)
    if other_user is None or other_user.id == current_user.id:
        abort(404)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if len(body) > 1000:
            return jsonify(error="Messages can be at most 1,000 characters."), 400
        image_filename = None
        image = request.files.get("image")
        if image and image.filename:
            image_filename, error = save_image(image)
            if error:
                return jsonify(error=error), 400
        if not body and not image_filename:
            return jsonify(error="Write a message or choose a photo."), 400
        message = Message(sender_id=current_user.id, recipient_id=user_id, body=body,
                          image_filename=image_filename)
        db.session.add(message)
        db.session.commit()
        return jsonify(message_json(message)), 201

    try:
        after_id = max(0, int(request.args.get("after", 0)))
    except ValueError:
        abort(400)
    # Long polling keeps the request open briefly so messages appear promptly.
    deadline = time.monotonic() + 20
    new_messages = conversation_messages(user_id, after_id)
    while not new_messages and time.monotonic() < deadline:
        time.sleep(1)
        db.session.expire_all()
        new_messages = conversation_messages(user_id, after_id)
    return jsonify(messages=[message_json(message) for message in new_messages])

# --------------------------------------------------
# Create Post
# --------------------------------------------------

@app.route("/post/new", methods=["GET", "POST"])
@login_required
def create_post():

    if request.method == "POST":

        caption = request.form.get("caption", "").strip()
        image = request.files.get("image")

        if len(caption) > 2200:
            return render_template("create_post.html", error="Captions can be at most 2,200 characters."), 400

        unique_name, error = save_image(image)
        if error:
            return render_template("create_post.html", error=error), 400
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)

        new_post = Post(
            user_id=current_user.id,
            image_filename=unique_name,
            caption=caption
        )

        try:
            db.session.add(new_post)
            db.session.commit()
        except Exception:
            db.session.rollback()
            if os.path.exists(image_path):
                os.remove(image_path)
            raise

        return redirect(url_for("feed"))

    return render_template("create_post.html")

# --------------------------------------------------
# Logout
# --------------------------------------------------

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


@app.errorhandler(413)
def file_too_large(_error):
    return render_template("create_post.html", error="Image files must be 8 MB or smaller."), 413

# --------------------------------------------------
# Run Application
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
