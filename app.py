from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import shutil

from logic import zpracuj_pdf

app = FastAPI()

TEMP = Path("temp")
TEMP.mkdir(exist_ok=True)


@app.get("/")
def index():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Shoptet – Souhrn objednávek</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f6f8;
            padding: 40px;
        }
        .box {
            background: white;
            max-width: 480px;
            margin: auto;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        h2 {
            text-align: center;
        }
        input[type=file] {
            width: 100%;
            margin: 20px 0;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
        }
        button:hover {
            background: #1e4fd1;
        }
        .note {
            font-size: 13px;
            color: #666;
            margin-top: 15px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="box">
        <h2>Nahrát PDF objednávek</h2>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".pdf" required>
            <button type="submit">Zpracovat PDF</button>
        </form>
        <div class="note">
            PDF z Shoptetu • Automatický souhrn skladu
        </div>
    </div>
</body>
</html>
""")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    pdf_path = TEMP / file.filename

    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    zpracuj_pdf(str(pdf_path))

    return HTMLResponse("""
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Hotovo – Souhrn skladu</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f6f8;
            padding: 40px;
        }
        .box {
            background: white;
            max-width: 520px;
            margin: auto;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.12);
            text-align: center;
        }
        h2 {
            color: #16a34a;
        }
        p {
            color: #555;
        }
        .btn {
            display: block;
            text-decoration: none;
            margin: 15px 0;
            padding: 14px;
            font-size: 16px;
            border-radius: 8px;
            font-weight: bold;
        }
        .blue {
            background: #2563eb;
            color: white;
        }
        .green {
            background: #16a34a;
            color: white;
        }
        .gray {
            background: #e5e7eb;
            color: #111;
        }
        .btn:hover {
            opacity: 0.9;
        }
    </style>
</head>
<body>
    <div class="box">
        <h2>✅ Hotovo</h2>
        <p>PDF bylo úspěšně zpracováno.</p>

        <a class="btn green" href="/download/povleceni">
            🛏️ Stáhnout povlečení
        </a>

        <a class="btn blue" href="/download/ostatni">
            📦 Stáhnout ostatní sortiment
        </a>

        <a class="btn gray" href="/">
            ⬅️ Nahrát další PDF
        </a>
    </div>
</body>
</html>
""")


@app.get("/download/povleceni")
def download_povleceni():
    cesta = TEMP / "soupis_povleceni.xlsx"
    return FileResponse(cesta, filename="soupis_povleceni.xlsx")


@app.get("/download/ostatni")
def download_ostatni():
    cesta = TEMP / "soupis_ostatni_sortiment.xlsx"
    return FileResponse(cesta, filename="soupis_ostatni_sortiment.xlsx")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
