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


# ✅ Income Model
class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.Date, default=datetime.utcnow)

    user = db.relationship('User', backref='income')


# ✅ Ensure DB tables are created
with app.app_context():
    db.create_all()


# ✅ User Loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
            return redirect(url_for("dashboard"))
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
    search_term = request.args.get("search", "")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # Query expenses for the logged-in user
    expenses_query = Expense.query.filter_by(user_id=current_user.id)

    if search_term:
        expenses_query = expenses_query.filter(
            or_(
                Expense.category.ilike(f"%{search_term}%"),
                Expense.description.ilike(f"%{search_term}%")
            )
        )

    if start_date:
        expenses_query = expenses_query.filter(Expense.date >= start_date)
    if end_date:
        expenses_query = expenses_query.filter(Expense.date <= end_date)

    expenses = expenses_query.order_by(Expense.date.desc()).all()

    # ✅ Query incomes for the logged-in user
    incomes_query = Income.query.filter_by(user_id=current_user.id)

    if start_date:
        incomes_query = incomes_query.filter(Income.date >= start_date)
    if end_date:
        incomes_query = incomes_query.filter(Income.date <= end_date)

    incomes = incomes_query.order_by(Income.date.desc()).all()

    # ✅ Ensure `total_income` and `total_expense` always exist
    total_expense = sum(exp.amount for exp in expenses) if expenses else 0
    total_income = sum(inc.amount for inc in incomes) if incomes else 0

    # ✅ Find the top spending category
    category_totals = {}
    for expense in expenses:
        category_totals[expense.category] = category_totals.get(expense.category, 0) + expense.amount
    top_category = max(category_totals, key=category_totals.get, default="N/A")

    # ✅ Prepare data for pie chart (expenses by category)
    expense_labels = list(category_totals.keys()) if category_totals else []
    expense_values = list(category_totals.values()) if category_totals else []

    # ✅ Prepare data for pie chart (income vs. expenses)
    income_expense_labels = ["Income", "Expenses"]
    income_expense_values = [total_income, total_expense]

    # ✅ Prepare data for line chart (expense trends)
    expense_dates = [exp.date.strftime("%Y-%m-%d") for exp in expenses] if expenses else []
    expense_amounts = [exp.amount for exp in expenses] if expenses else []

    # ✅ Prepare data for line chart (income vs. expense trends)
    income_dates = [inc.date.strftime("%Y-%m-%d") for inc in incomes] if incomes else []
    income_amounts = [inc.amount for inc in incomes] if incomes else []

    return render_template(
        "dashboard.html",
        expenses=expenses,
        total_expense=total_expense,  # ✅ Fix: Ensure `total_expense` is passed
        total_income=total_income,    # ✅ Fix: Ensure `total_income` is passed
        top_category=top_category,
        expense_labels=expense_labels,
        expense_values=expense_values,
        income_expense_labels=income_expense_labels,
        income_expense_values=income_expense_values,
        expense_dates=expense_dates,
        expense_amounts=expense_amounts,
        income_dates=income_dates,
        income_amounts=income_amounts,
        search_term=search_term,
        start_date=start_date,
        end_date=end_date,
        CATEGORIES=CATEGORIES
    )

# ✅ Add Income Route
@app.route("/add_income", methods=["GET", "POST"])
@login_required
def add_income():
    if request.method == "POST":
        try:
            category = request.form.get("category")
            amount = float(request.form.get("amount"))
            date = datetime.strptime(request.form.get("date"), "%Y-%m-%d")
            description = request.form.get("description")

            new_income = Income(
                user_id=current_user.id,
                category=category,
                amount=amount,
                date=date,
                description=description
            )
            db.session.add(new_income)
            db.session.commit()

            flash("Income added successfully!", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            flash(f"Error adding income: {str(e)}", "danger")

    return render_template("add_income.html")




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


# ✅ Run the Flask App
if __name__ == "__main__":
    app.run(debug=True)