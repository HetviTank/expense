import os

DB_HOST = os.environ.get("KN_DB_HOST")
DB_USER = os.environ.get("KN_DB_USER")
DB_PASSWORD = os.environ.get("KN_DB_PASSWORD")
DB_NAME = os.environ.get("KN_DB_NAME")
JWT_KEY = os.environ.get("KN_JWT_KEY")