from datetime import datetime
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from dependencies import get_db
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import shutil, os

from database import Base, engine, SessionLocal
from models import User, Expense

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")


# Fake session (replace with JWT/cookies for real auth)
current_user_id = 1

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/login")

# ---------- AUTH ----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == username, User.password == password).first()
    if user:
        global current_user_id
        current_user_id = user.id
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = User(username=username, password=password)
    db.add(user)
    db.commit()
    return RedirectResponse("/login", status_code=302)

# ---------- EXPENSES ----------
@app.get("/expenses", response_class=HTMLResponse)
def expense_list(request: Request, db: Session = Depends(get_db)):
    expenses = db.query(Expense).filter(Expense.user_id == current_user_id).all()
    return templates.TemplateResponse("expenses.html", {"request": request, "expenses": expenses})

@app.get("/expenses/add", response_class=HTMLResponse)
def add_expense_page(request: Request):
    return templates.TemplateResponse("add_expense.html", {"request": request})

@app.post("/expenses/add")
def add_expense(
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    description: str = Form(""),
    bill: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Save file if uploaded
    file_path = None
    if bill:
        os.makedirs("uploads", exist_ok=True)
        file_path = f"uploads/{bill.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(bill.file, buffer)

    expense = Expense(
        user_id=current_user_id,
        amount=amount,
        category=category,
        date=datetime.strptime(date, "%Y-%m-%d").date(),
        description=description,
        bill_image=file_path,
    )
    db.add(expense)
    db.commit()
    return RedirectResponse("/expenses", status_code=302)

@app.get("/expenses/delete/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user_id).first()
    if expense:
        db.delete(expense)
        db.commit()
    return RedirectResponse("/expenses", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    expenses = db.query(Expense).filter(Expense.user_id == current_user_id).all()
    categories = {}
    for e in expenses:
        categories[e.category] = categories.get(e.category, 0) + e.amount
    return templates.TemplateResponse("dashboard.html", {"request": request, "categories": categories})
