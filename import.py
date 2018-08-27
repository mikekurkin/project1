import csv

# Get database info from the main app
from application import db

# Open csv file
with open("books.csv") as csvfile:
    # Read as a dictionary
    reader = csv.DictReader(csvfile)
    for row in reader:
        db.execute("INSERT INTO books (isbn, title, author, year) VALUES (:isbn, :title, :author, :year)", {"isbn": row["isbn"], "title": row["title"], "author": row["author"], "year": row["year"]})
        print(row)

# Commit to db
db.commit()