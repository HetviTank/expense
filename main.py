from datetime import datetime, timedelta, timezone
import json
from fastapi import FastAPI, HTTPException, Request, Depends, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from dependencies import get_db
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import shutil, os
from jwcrypto import jwt, jwk
from config import JWT_KEY

from database import Base, engine, SessionLocal
from models import User, Expense

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

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    global current_user_id
    user = db.query(User).filter(User.email == username).first()
    current_user_id = user.id
    if not user or user.password != password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = get_token(user.id, user.email, db)

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax"
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
    user = User(name=name, email=email, password=password, role=role)
    db.add(user)
    db.commit()
    return RedirectResponse("/login", status_code=302)

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
