from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import or_, and_
from collections import defaultdict
from flask_migrate import Migrate

# Import CATEGORIES safely
try:
    from config import CATEGORIES
except ImportError:
    CATEGORIES = {}  # Default to empty if not available

app = Flask(__name__, template_folder="templates")

app.secret_key = "your_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ✅ User Model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


# ✅ Expense Model
class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255))


# ✅ Ensure DB tables are created
with app.app_context():
    db.create_all()


# ✅ User Loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        hashed_password = generate_password_hash(password, method="pbkdf2:sha256")

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "warning")
        else:
            new_user = User(username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful! You can now log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


# ✅ Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("home"))
        else:
            flash("Invalid credentials", "danger")

    return render_template("login.html")


# ✅ Logout Route
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully!", "info")
    return redirect(url_for("login"))


# ✅ Home Route
@app.route("/home")
@login_required
def home():
    return render_template("home.html")


# ✅ Dashboard Route
@app.route("/dashboard")
@login_required
def dashboard():
    # Get search and filter parameters from the request
    search_term = request.args.get("search", "")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # Query expenses for the logged-in user
    expenses_query = Expense.query.filter_by(user_id=current_user.id)

    # Apply search filtering
    if search_term:
        expenses_query = expenses_query.filter(
            (Expense.category.ilike(f"%{search_term}%")) |
            (Expense.description.ilike(f"%{search_term}%"))
        )

    # Apply date filtering
    if start_date:
        expenses_query = expenses_query.filter(Expense.date >= start_date)
    if end_date:
        expenses_query = expenses_query.filter(Expense.date <= end_date)

    expenses = expenses_query.order_by(Expense.date.desc()).all()

    # ✅ Calculate total expenses
    total_expense = sum(expense.amount for expense in expenses)

    # ✅ Find the top spending category
    category_totals = {}
    for expense in expenses:
        category_totals[expense.category] = category_totals.get(expense.category, 0) + expense.amount
    top_category = max(category_totals, key=category_totals.get, default="N/A")

    # ✅ Prepare data for Expenses Pie Chart
    expense_labels = list(category_totals.keys())
    expense_values = list(category_totals.values())

    # ✅ Prepare data for Trend Graph (Expenses over time)
    expense_trends = {}
    for expense in expenses:
        date_str = expense.date.strftime("%Y-%m-%d")
        expense_trends[date_str] = expense_trends.get(date_str, 0) + expense.amount
    expense_dates = list(expense_trends.keys())
    expense_amounts = list(expense_trends.values())

    return render_template(
        "dashboard.html",
        expenses=expenses,
        total_expense=total_expense,
        top_category=top_category,
        expense_labels=expense_labels,
        expense_values=expense_values,
        expense_dates=expense_dates,
        expense_amounts=expense_amounts,
        search_term=search_term,
        start_date=start_date,
        end_date=end_date,
        CATEGORIES=CATEGORIES
    )


# ✅ Add Expense Route
@app.route("/add_expense", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        try:
            category = request.form.get("category")
            amount = float(request.form.get("amount"))
            date = datetime.strptime(request.form.get("date"), "%Y-%m-%d")
            description = request.form.get("description")

            new_expense = Expense(
                user_id=current_user.id,
                category=category,
                amount=amount,
                date=date,
                description=description
            )
            db.session.add(new_expense)
            db.session.commit()

            flash("Expense added successfully!", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            flash(f"Error adding expense: {str(e)}", "danger")

    return render_template("add_expense.html", CATEGORIES=CATEGORIES)


# ✅ Edit Expense Route
@app.route("/edit_expense/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first()
    if not expense:
        flash("Expense not found!", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        expense.category = request.form["category"]
        expense.amount = float(request.form["amount"])
        expense.date = datetime.strptime(request.form["date"], "%Y-%m-%d")
        expense.description = request.form["description"]

        db.session.commit()
        flash("Expense updated successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_expense.html", expense=expense, CATEGORIES=CATEGORIES)

@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    expense = Expense.query.get(expense_id)
    if expense:
        db.session.delete(expense)
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False, error="Expense not found"), 404


# ✅ Run the Flask App
if __name__ == "__main__":
    app.run(debug=True)
