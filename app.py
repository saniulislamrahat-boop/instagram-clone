from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import quote_plus
from flask import Flask, render_template, request
from werkzeug.security import generate_password_hash, check_password_hash
app = Flask(__name__)
password = quote_plus("rahat32312@#$")


# mysql connection

app.config['SQLALCHEMY_DATABASE_URI'] = \
f"mysql+pymysql://root:{password}@localhost/instagram_db"

db = SQLAlchemy(app)



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

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

    bio = db.Column(db.Text)


with app.app_context():
    db.create_all()



@app.route("/")
def home():
    return "instagram clone "

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        # Hash password
        hashed_password = generate_password_hash(password)

        
        new_user = User(
            username=username,
            email=email,
            password=hashed_password
        )

        # Save to database
        db.session.add(new_user)
        db.session.commit()

        return "Registration successful!"

    return render_template("register.html")



@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        # Find user in database
        user = User.query.filter_by(
            username=username
        ).first()

        # Verify password
        if user and check_password_hash(
                user.password,
                password):

            return "Login Successful!"

        return "Invalid username or password!"

    return render_template("login.html")








if __name__ =="__main__":
    app.run(debug=True)