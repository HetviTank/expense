# Expense Tracker Application

A modern web-based expense tracking application built with FastAPI and SQLAlchemy.

## Features

- **User Authentication**: Secure login/registration with JWT tokens
- **Expense Management**: Add, edit, delete, and view expenses
- **Category-wise Tracking**: Organize expenses by categories
- **Receipt Upload**: Upload and view receipt images/PDFs
- **Summary Reports**: Monthly, yearly, and all-time expense summaries
- **Visual Charts**: Interactive doughnut charts for expense breakdown
- **Responsive Design**: Modern UI with blue-teal gradient theme

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL
- **Frontend**: HTML, CSS, JavaScript, Chart.js
- **Authentication**: JWT with bcrypt password hashing
- **Database**: PostgreSQL with Alembic migrations

## Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd expense
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up database**
```bash
# Update database credentials in config.py
# Run migrations
alembic upgrade head
```

4. **Start the application**
```bash
uvicorn main:app --reload --port 5001
```

5. **Access the application**
Open http://127.0.0.1:5001 in your browser

## Usage

1. **Register/Login**: Create an account or login with existing credentials
2. **Add Expenses**: Navigate to "Add Expense" and fill in the details
3. **View Expenses**: See all your expenses in the "Expenses" section
4. **Generate Reports**: Use "Summary" to view category-wise breakdowns
5. **Manage Data**: Edit or delete expenses using the action buttons

## API Endpoints

- `POST /login` - User authentication
- `POST /register` - User registration
- `GET /expenses` - View expenses
- `POST /expenses/add` - Add new expense
- `PUT /expenses/edit/{id}` - Edit expense
- `DELETE /expenses/delete/{id}` - Delete expense
- `GET /expenses/summary/{year}/{month}` - Monthly summary
- `GET /expenses/summary/year/{year}` - Yearly summary
- `GET /expenses/summary/all` - All-time summary

## Configuration

Update `config.py` with your database credentials:
```python
DB_HOST = "localhost"
DB_USER = "your_username"
DB_PASSWORD = "your_password"
DB_NAME = "expense"
```

## Security Features

- Password hashing with bcrypt
- JWT token authentication
- File upload validation
- SQL injection prevention
- XSS protection
