from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import quote_plus
from flask import Flask, render_template, request



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

        return f"User {username} registered successfully!"

    return render_template("register.html")




















if __name__ =="__main__":
    app.run(debug=True)