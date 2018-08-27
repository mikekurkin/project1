import os
import requests

from flask import Flask, session, redirect, request, render_template
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


def error(message, code=400):
    """Renders message as an apology to user."""
    return render_template("error.html", code=code, message=message), code


def get_gr_res(isbn):
    """Returns books list extended with information from """
    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": os.getenv("GOODREADS_KEY"),
                               "isbns": isbn})
    return res


@app.route("/")
def index():
    try:
        books = db.execute(
            "SELECT * FROM books ORDER BY RANDOM() LIMIT 5"
        ).fetchall()
    except Exception:
        return error("Database error", 503)
    return render_template("index.html", books=books)


@app.route("/book/<int:book_id>")
def book(book_id):
    """Renders info page for book with given id"""
    try:
        rows = db.execute("SELECT * FROM books WHERE id = :id",
                          {"id": book_id})
    except Exception:
        return error("Database error", 503)

    if rows.rowcount == 0:
        return error("No suck book with this id", 404)

    book = rows.fetchone()

    cover = f"https://covers.openlibrary.org/b/isbn/{book.isbn}-L.jpg"
    gr_res = get_gr_res(book.isbn)

    print(gr_res.json())
    print(cover)
    return render_template("book.html",
                           book=book,
                           cover=cover,
                           gr_res=gr_res.json())


@app.route("/login", methods=['POST', 'GET'])
def login():
    """Log user in."""

    # Forget any user_id
    session.clear()

    # If user reaches via GET, render the form
    if request.method == 'GET':
        return render_template("login.html")

    # If user reaches via POST
    else:
        # Check the required attributes
        if not request.form["username"]:
            return error("Username is required")
        if not request.form["password"]:
            return error("Password is required")

        # Set variables
        username = str(request.form["username"])
        password = str(request.form["password"])

        # Get rows from database
        users = db.execute("SELECT * FROM users WHERE name = :username",
                           {"username": username})

        # Check if user with this username exists
        if users.rowcount == 0:
            return error("No such user with this username")
        user = users.fetchone()

        # Check the password
        if not check_password_hash(user.hash, password):
            return error("Invalid password")

        # Set the session
        session["user_id"] = user.id
        session["user_name"] = user.name

        # Redirect to index
        return redirect("/")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect to index
    return redirect("/")


@app.route("/register", methods=['POST', 'GET'])
def register():
    """Register user."""

    # Forget any user_id
    session.clear()

    # If user reaches via GET, render the form
    if request.method == 'GET':
        return render_template("register.html")

    # If user reaches via POST
    else:
        # Chack the required attributes
        if not request.form["username"]:
            return error("Username is required")
        if not request.form["password"] or not request.form["confirmation"]:
            return error("Password and confirmation are required")
        if not request.form["password"] == request.form["confirmation"]:
            return error("Password and confirmation should match")

        # Set variables
        username = str(request.form["username"])
        hashed = generate_password_hash(str(request.form["password"]))

        # Check if the username already taken
        if not db.execute("SELECT id FROM users WHERE name = :username",
                          {"username": username}).rowcount == 0:
            return error("Username already taken")

        # Write to database
        try:
            db.execute(
                "INSERT INTO users (name, hash) VALUES (:username, :hashed)",
                {"username": username, "hashed": hashed}
            )
            db.commit()
        except Exception:
            return error("Database error", 503)

        # Get the new user's id
        user = db.execute("SELECT id, name FROM users WHERE name = :username",
                          {"username": username}).fetchone()

        # Set the session
        session["user_id"] = user.id
        session["user_name"] = user.name

        # Redirect to index
        return redirect("/")


@app.route("/search")
def search():
    q = request.args.get('q')
    try:
        books = db.execute(
            "SELECT * FROM books WHERE LOWER(isbn) LIKE LOWER(:s) \
             OR LOWER(title) LIKE LOWER(:q) OR LOWER(author) LIKE LOWER(:q)",
            {"s": q+'%', "q": '%'+q+'%'}).fetchall()
    except Exception:
        return error("Database error", 503)
    return render_template("search.html", books=books, q=q)
