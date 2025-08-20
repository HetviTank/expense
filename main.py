import calendar
from datetime import datetime, timedelta, timezone, date
import json
import os
import shutil

from fastapi import (
    FastAPI, HTTPException, Header, Request, Depends, Form, UploadFile, File, status
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
security = HTTPBearer(auto_error=False)

# Database setup
Base.metadata.create_all(bind=engine)

# FastAPI setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

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


def verify_token(
    db: Session = Depends(get_db),
    request: Request = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    jwt_token = request.cookies.get("access_token") if request else None
    if not jwt_token and credentials:
        jwt_token = credentials.credentials

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        key = jwk.JWK(**json.loads(JWT_KEY))
        signed_token = jwt.JWT(key=key, jwt=jwt_token)
        claims = json.loads(signed_token.claims)

        db_user = db.query(User).filter(User.id == claims["id"]).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found or deleted")

        return db_user
    except jwt.JWTExpired:
        raise HTTPException(status_code=401, detail="Token has expired")
    except Exception as e:
        print(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")



@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == username).first()
    if not user or user.password != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = get_token(user.id, user.email)
    return {"access_token": token, "token_type": "bearer"}



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


# -----------------------------
# Expenses routes
# -----------------------------
@app.get("/expenses", response_class=HTMLResponse)
def expense_list(request: Request, db_user: User = Depends(verify_token), db: Session = Depends(get_db)):
    expenses = db.query(Expense).filter(Expense.user_id == db_user.id, Expense.is_deleted == False).all()
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
    db_user: User = Depends(verify_token),
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
        user_id=db_user.id,
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
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    db_user: User = Depends(lambda db=Depends(get_db), cred=Depends(security): verify_token(db, cred))
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == db_user.id).first()
    if expense:
        expense.is_deleted = True
        db.commit()
    return RedirectResponse("/expenses", status_code=302)


# -----------------------------
# Dashboard
# -----------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db_user: User = Depends(verify_token),
    db: Session = Depends(get_db)
):
    expenses = db.query(Expense).filter(
        Expense.user_id == db_user.id,
        Expense.is_deleted == False
    ).all()

    categories = {}
    for e in expenses:
        categories[e.category] = categories.get(e.category, 0) + e.amount

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "categories": categories}
    )



# -----------------------------
# Summary
# -----------------------------
@app.get("/summary", response_class=HTMLResponse)
def summary_page(request: Request):
    return templates.TemplateResponse("summary.html", {"request": request})


@app.get("/expenses/summary/{year}/{month}")
def monthly_summary(year: int, month: str, db_user: User = Depends(verify_token), db: Session = Depends(get_db)):
    try:
        month_int = list(calendar.month_name).index(month.capitalize())
        if month_int == 0:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid month name: {month}")

    start_date = datetime(year, month_int, 1).date()
    end_date = datetime(year + (month_int // 12), (month_int % 12) + 1, 1).date()

    results = (
        db.query(Expense.category, func.sum(Expense.amount).label("total"))
        .filter(
            Expense.user_id == db_user.id,
            Expense.date >= start_date,
            Expense.date < end_date,
            Expense.is_deleted == False
        )
        .group_by(Expense.category)
        .all()
    )

    return [{"category": r[0], "total": float(r[1])} for r in results]
