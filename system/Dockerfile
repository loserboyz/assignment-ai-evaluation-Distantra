
# Menggunakan Python 3.11 versi ringan
FROM python:3.11-slim

# Menentukan direktori kerja di dalam container
WORKDIR /app

# Menyalin requirements terlebih dahulu
COPY requirements.txt .

# Menginstal seluruh dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Menyalin seluruh source code aplikasi
COPY . .

# Membuka port aplikasi
EXPOSE 8000

# Menjalankan aplikasi FastAPI menggunakan Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
