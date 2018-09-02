import os
import requests

from flask import Flask, abort, session, jsonify, redirect, request,\
                  render_template
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

app.config["JSON_SORT_KEYS"] = False

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


@app.route("/api/<book_isbn>")
def api(book_isbn):
    """Return number of reviews and an average score"""
    # Get book
    rows = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                      {"isbn": book_isbn})
    if not rows.rowcount == 1:
        abort(404)
    book = rows.fetchone()

    # Get reviews
    rows = db.execute("SELECT * FROM reviews WHERE book_id = :book_id",
                      {"book_id": book.id})
    count = rows.rowcount
    reviews = rows.fetchall()

    # Calculate average
    sum = 0
    for review in reviews:
        sum += review.score
    average = sum / count

    # Create dictionary
    output = {"title": book.title,
              "author": book.author,
              "year": book.year,
              "isbn": book.isbn,
              "review_count": count,
              "average_score": average}

    print(output)
    return jsonify(output)


@app.route("/book/<int:book_id>", methods=['POST', 'GET'])
def book(book_id):
    """Render book page or post a review"""
    # If user reaches via GET, render info page for book with given id
    if request.method == 'GET':
        rows = db.execute("SELECT * FROM books WHERE id = :id",
                          {"id": book_id})

        if rows.rowcount == 0:
            return error("No suck book with this id", 404)

        book = rows.fetchone()

        # Check if user already reviewed this book
        reviewed = True
        if session["user_id"]:
            rows = db.execute("SELECT * FROM reviews WHERE user_id = :user_id\
                               AND book_id = :book_id",
                              {"user_id": session["user_id"],
                               "book_id": book_id})
            if rows.rowcount == 0:
                print(rows.fetchall())
                reviewed = False

        # Get own reviews
        reviews = db.execute("SELECT reviews.id, reviews.timestamp,\
                              reviews.content, reviews.score, users.name\
                              FROM reviews INNER JOIN users ON\
                              (reviews.user_id = users.id) WHERE\
                              book_id = :book_id",
                             {"book_id": book_id}).fetchall()

        # Get cover from OpenLibrary
        cover = f"https://covers.openlibrary.org/b/isbn/{book.isbn}-L.jpg"
        # Get reviews info from Goodreads
        gr_res = get_gr_res(book.isbn).json()["books"][0]

        return render_template("book.html",
                               book=book,
                               cover=cover,
                               reviewed=reviewed,
                               reviews=reviews,
                               gr_res=gr_res)

    # If user reaches via POST, then post review
    else:
        if not session["user_id"]:
            return error("Unauthorized", 403)

        content = request.form.get('content')
        if not content:
            return error("Please write a review")

        # Check if score is integer
        try:
            score = int(request.form.get('score'))
        except Exception:
            return error("Please rate a book")

        # Write to database
        try:
            db.execute("INSERT INTO reviews (book_id, user_id, content, score)\
                        VALUES (:book_id, :user_id, :content, :score)",
                       {"book_id": book_id,
                        "user_id": session["user_id"],
                        "content": content,
                        "score": score})
        except Exception:
            return error("Database error", 503)
        db.commit()

        return redirect(f"/book/{book_id}")


@app.route("/login", methods=['POST', 'GET'])
def login():
    """Log user in"""

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
    """Register user"""

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
    """Searches for specified request"""
    q = request.args.get('q')

    try:
        books = db.execute(
            "SELECT * FROM books WHERE LOWER(isbn) LIKE LOWER(:s) \
             OR LOWER(title) LIKE LOWER(:q) OR LOWER(author) LIKE LOWER(:q)",
            {"s": q+'%', "q": '%'+q+'%'}).fetchall()
    except Exception:
        return error("Database error", 503)

    return render_template("search.html", books=books, q=q)


# This is for Heroku
if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
