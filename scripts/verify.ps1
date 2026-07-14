$ErrorActionPreference = "Stop"
& .\.venv\Scripts\python.exe manage.py check
& .\.venv\Scripts\python.exe manage.py test
ruff check .
