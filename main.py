import calendar
from datetime import datetime, timedelta, timezone, date
import json
import os
import shutil
import bcrypt
import logging
from pathlib import Path

from fastapi import (
    FastAPI, HTTPException, Header, Request, Depends, Form, UploadFile, File, status, Cookie
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlalchemy.orm import Session

from jwcrypto import jwt, jwk

from dependencies import get_db
from database import Base, engine
from models import User, Expense
from utils import generate_uuid
from config import JWT_KEY

# Security
security = HTTPBearer()

# Database setup
Base.metadata.create_all(bind=engine)

# FastAPI setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

# Authentication dependency
def get_current_user(db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    return verify_token(db, credentials)

# Authentication for HTML pages using cookies
def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('access_token')
    if not token:
        return None
    
    try:
        key = jwk.JWK(**json.loads(JWT_KEY))
        signed_token = jwt.JWT(key=key, jwt=token)
        claims = json.loads(signed_token.claims)
        db_user = db.query(User).filter(User.id == claims["id"]).first()
        if db_user and not db_user.is_deleted:
            return db_user
    except:
        pass
    
    return None


# -----------------------------
# JWT Token functions
# -----------------------------
def get_token(user_id: str, email: str):
    now_utc = datetime.now(timezone.utc)
    exp = now_utc + timedelta(hours=1)

    claims = {
        "id": user_id,
        "email": email,
        "iat": int(now_utc.timestamp()),
        "exp": int(exp.timestamp()),
    }

    key = jwk.JWK(**json.loads(JWT_KEY))
    token = jwt.JWT(header={"alg": "HS256"}, claims=claims)
    token.make_signed_token(key)
    return token.serialize()


def verify_token(db: Session, credentials: HTTPAuthorizationCredentials):
    token = credentials.credentials
    try:
        key = jwk.JWK(**json.loads(JWT_KEY))
        signed_token = jwt.JWT(key=key, jwt=token)
        claims = json.loads(signed_token.claims)

        db_user = db.query(User).filter(User.id == claims["id"]).first()
        if not db_user or db_user.is_deleted:
            raise HTTPException(status_code=401, detail="User not found")

        return db_user

    except jwt.JWTExpired:
        raise HTTPException(status_code=401, detail="Token has expired")
    except Exception as e:
        logging.error(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


# -----------------------------
# Routes
# -----------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == username).first()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = get_token(user.id, user.email)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=3600)
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...), role: str = Form(...), db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user = User(id=generate_uuid(), name=name, email=email, password=hashed_password.decode('utf-8'), role=role)
    db.add(user)
    db.commit()
    return RedirectResponse("/login", status_code=302)

@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(key="access_token")
    return response


# -----------------------------
# Expenses routes
# -----------------------------
@app.get("/expenses", response_class=HTMLResponse)
def expense_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    expenses = db.query(Expense).filter(Expense.user_id == user.id, Expense.is_deleted == False).all()
    return templates.TemplateResponse("expenses.html", {"request": request, "expenses": expenses})


@app.get("/expenses/add", response_class=HTMLResponse)
def add_expense_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("add_expense.html", {"request": request})


@app.post("/expenses/add")
def add_expense(request: Request, amount: float = Form(...), category: str = Form(...), date: str = Form(...), description: str = Form(""), bill: UploadFile = File(None), db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    file_path = None
    if bill and bill.filename:
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
        file_ext = Path(bill.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail="Invalid file type")
        
        os.makedirs("uploads", exist_ok=True)
        safe_filename = f"{generate_uuid()}{file_ext}"
        file_path = f"uploads/{safe_filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(bill.file, buffer)

    expense = Expense(
        id=generate_uuid(),
        user_id=user.id,
        amount=amount,
        category=category,
        date=datetime.fromisoformat(date).date(),
        description=description,
        bill_image=file_path,
    )
    db.add(expense)
    db.commit()
    return RedirectResponse("/expenses", status_code=302)


@app.put("/expenses/edit/{expense_id}")
def edit_expense(expense_id: str, request: Request, amount: float = Form(...), category: str = Form(...), db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense.amount = amount
    expense.category = category
    db.commit()
    return RedirectResponse(url="/expenses", status_code=302)


@app.get("/expenses/edit/{expense_id}", response_class=HTMLResponse)
def edit_expense_page(expense_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return templates.TemplateResponse("edit_expense.html", {"request": request, "expense": expense})


@app.delete("/expenses/delete/{expense_id}")
def delete_expense(expense_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    expense.is_deleted = True
    db.commit()
    return RedirectResponse("/expenses", status_code=302)


# -----------------------------
# Dashboard
# -----------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    expenses = db.query(Expense).filter(Expense.user_id == user.id, Expense.is_deleted == False).all()
    categories = {}
    for e in expenses:
        categories[e.category] = categories.get(e.category, 0) + e.amount
    return templates.TemplateResponse("dashboard.html", {"request": request, "categories": categories})


# -----------------------------
# Summary
# -----------------------------
@app.get("/summary", response_class=HTMLResponse)
def summary_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("summary.html", {"request": request})


@app.get("/expenses/summary/{year}/{month}")
def monthly_summary(year: int, month: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        month_int = list(calendar.month_name).index(month.capitalize())
        if month_int == 0:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid month name: {month}")

    start_date = date(year, month_int, 1)
    end_date = date(year + 1, 1, 1) if month_int == 12 else date(year, month_int + 1, 1)

    results = db.query(Expense.category, func.sum(Expense.amount).label("total")).filter(
        Expense.date >= start_date, Expense.date < end_date, Expense.user_id == user.id, Expense.is_deleted == False
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()

    return [{"category": r[0], "total": float(r[1])} for r in results]

@app.get("/expenses/summary/all")
def all_categories_summary(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    results = db.query(Expense.category, func.sum(Expense.amount).label("total")).filter(
        Expense.user_id == user.id, Expense.is_deleted == False
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()

    return [{"category": r[0], "total": float(r[1])} for r in results]

@app.get("/expenses/summary/year/{year}")
def yearly_summary(year: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    start_date = date(year, 1, 1)
    end_date = date(year + 1, 1, 1)

    results = db.query(Expense.category, func.sum(Expense.amount).label("total")).filter(
        Expense.date >= start_date, Expense.date < end_date, Expense.user_id == user.id, Expense.is_deleted == False
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()

    return [{"category": r[0], "total": float(r[1])} for r in results]
