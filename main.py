from datetime import datetime, timedelta, timezone
import json
from fastapi import FastAPI, HTTPException, Request, Depends, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from dependencies import get_db
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import shutil, os
from jwcrypto import jwt, jwk
from config import JWT_KEY

from database import Base, engine, SessionLocal
from models import User, Expense
from utils import generate_uuid

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")


def get_token(admin_user_id, email, db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc)
    expiration_datetime = now_utc + timedelta(hours=1)
    claims = {
        "id": admin_user_id,
        "email": email,
        "iat": now_utc.timestamp(),
        "exp": expiration_datetime.timestamp(),
    }

    key = jwk.JWK(**json.loads(JWT_KEY))
    token = jwt.JWT(header={"alg": "HS256"}, claims=claims)
    token.make_signed_token(key)

    encrypted_token = jwt.JWT(
        header={"alg": "A256KW", "enc": "A256CBC-HS512"},
        claims=token.serialize()
    )
    encrypted_token.make_encrypted_token(key)

    return encrypted_token.serialize()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    global current_user_id

    user = db.query(User).filter(User.email == username).first()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "User not found"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if user.password != password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    current_user_id = user.id
    access_token = get_token(user.id, user.email, db)

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    user = User(id=generate_uuid(), name=name, email=email, password=password, role=role)
    db.add(user)
    db.commit()
    return RedirectResponse("/login", status_code=302)

@app.get("/expenses", response_class=HTMLResponse)
def expense_list(request: Request, db: Session = Depends(get_db)):
    expenses = db.query(Expense).filter(Expense.user_id == current_user_id, Expense.is_deleted == False).all()
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
    file_path = None
    if bill:
        os.makedirs("uploads", exist_ok=True)
        file_path = f"uploads/{bill.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(bill.file, buffer)

    expense = Expense(
        id=generate_uuid(),
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

@app.put("/expenses/edit/{expense_id}", response_class=HTMLResponse)
def edit_expense(
    expense_id: str,
    amount: float = Form(...),
    category: str = Form(...),
    db: Session = Depends(get_db)
):
    print(expense_id)
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense.amount = amount
    expense.category = category
    db.commit()
    db.refresh(expense)

    return RedirectResponse(url="/expenses", status_code=302)

@app.get("/expenses/edit/{expense_id}", response_class=HTMLResponse)
def edit_expense_page(expense_id: str, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return templates.TemplateResponse(
        "edit_expense.html",
        {"request": {}, "expense": expense}
    )

@app.delete("/expenses/delete/{expense_id}")
def delete_expense(expense_id: str, db: Session = Depends(get_db)):
    print(expense_id)
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user_id).first()
    print(expense)
    if expense:
        expense.is_deleted = True
        db.commit()
    return RedirectResponse("/expenses", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    expenses = db.query(Expense).filter(Expense.user_id == current_user_id, Expense.is_deleted == False).all()
    categories = {}
    for e in expenses:
        categories[e.category] = categories.get(e.category, 0) + e.amount
    return templates.TemplateResponse("dashboard.html", {"request": request, "categories": categories})

@app.get("/expenses/summary/{year}/{month}")
def monthly_summary(year: int, month: int, db: Session = Depends(get_db)):
    start_date = datetime.date(year, month, 1)
    if month == 12:
        end_date = datetime.date(year + 1, 1, 1)
    else:
        end_date = datetime.date(year, month + 1, 1)
 
    results = (
        db.query(Expense.category, func.sum(Expense.amount).label("total"))
        .filter(Expense.date >= start_date, Expense.date < end_date)
        .group_by(Expense.category)
        .all()
    )
 
    return [{"category": r[0], "total": r[1]} for r in results]

