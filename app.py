from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import shutil

from logic import zpracuj_pdf

app = FastAPI()

TEMP = Path("temp")
TEMP.mkdir(exist_ok=True)

# =========================
# HLAVNÍ STRÁNKA
# =========================
@app.get("/")
def index():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<title>Smolka – Souhrn skladu</title>

<style>
* { box-sizing: border-box; }

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f4f6f8;
}

/* HLAVIČKA */
.header {
    height: 70px;
    background: white;
    display: flex;
    align-items: center;
    padding: 0 30px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}

.logo {
    font-weight: bold;
    font-size: 18px;
}

/* LAYOUT */
.wrapper {
    display: flex;
    height: calc(100vh - 70px);
}

/* LEVÉ MENU */
.sidebar {
    width: 220px;
    background: linear-gradient(#fff7cc, #ffe27a);
    padding: 20px;
}

.menu-item {
    padding: 12px 15px;
    margin-bottom: 10px;
    border-radius: 8px;
    background: rgba(255,255,255,0.6);
    cursor: pointer;
    font-weight: bold;
}

.menu-item:hover {
    background: white;
}

/* HLAVNÍ OBSAH */
.content {
    flex: 1;
    padding: 40px;
}

.card {
    background: white;
    max-width: 420px;
    padding: 30px;
    border-radius: 14px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.12);
}

input[type=file] {
    width: 100%;
    margin: 15px 0;
}

button {
    width: 100%;
    padding: 14px;
    font-size: 16px;
    background: #ef4444;
    border: none;
    border-radius: 8px;
    color: white;
    cursor: pointer;
}

button:hover {
    opacity: 0.9;
}

.note {
    margin-top: 15px;
    font-size: 13px;
    color: #666;
}
</style>
</head>

<body>

<div class="header">
    <div class="logo">SMOLKA • LŮŽKOVINY</div>
</div>

<div class="wrapper">

    <div class="sidebar">
        <div class="menu-item">📄 PDF → Excel</div>
        <div class="menu-item">📦 Stav skladu</div>
        <div class="menu-item">📊 Statistiky</div>
        <div class="menu-item">⚙️ Nastavení</div>
    </div>

    <div class="content">
        <div class="card">
            <h2>Nahrát soubory</h2>

            <form action="/upload" method="post" enctype="multipart/form-data">

                <label><b>PDF objednávek</b></label>
                <input type="file" name="pdf" accept=".pdf" required>

                <label><b>Excel – stav skladu</b></label>
                <input type="file" name="sklad" accept=".xlsx" required>

                <button type="submit">ZPRACOVAT</button>
            </form>

            <div class="note">
                PDF → soupis objednávek → automatický odečet skladu
            </div>
        </div>
    </div>

</div>

</body>
</html>
""")


# =========================
# ZPRACOVÁNÍ
# =========================
@app.post("/upload")
async def upload(
    pdf: UploadFile = File(...),
    sklad: UploadFile = File(...)
):
    pdf_path = TEMP / pdf.filename
    sklad_path = TEMP / sklad.filename

    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(pdf.file, f)

    with open(sklad_path, "wb") as f:
        shutil.copyfileobj(sklad.file, f)

    zpracuj_pdf(
        cesta_k_pdf=str(pdf_path),
        cesta_ke_skladu=str(sklad_path)
    )

    return HTMLResponse("""
<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<title>Hotovo</title>

<style>
body {
    font-family: Arial, sans-serif;
    background: #f4f6f8;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
}

.box {
    background: white;
    padding: 40px;
    border-radius: 14px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.15);
    text-align: center;
    max-width: 420px;
}

a {
    display: block;
    margin: 15px 0;
    padding: 14px;
    border-radius: 8px;
    text-decoration: none;
    font-weight: bold;
}

.green { background: #16a34a; color: white; }
.blue { background: #2563eb; color: white; }
.gray { background: #e5e7eb; color: #111; }
</style>
</head>

<body>
<div class="box">
    <h2>✅ Hotovo</h2>

    <a class="green" href="/download/sklad">📦 Stav skladu po odečtu</a>
    <a class="gray" href="/">⬅️ Zpět</a>
</div>
</body>
</html>
""")


# =========================
# DOWNLOAD
# =========================
@app.get("/download/sklad")
def download_sklad():
    return FileResponse(
        TEMP / "STAV_SKLADU_PO_ODECTU.xlsx",
        filename="STAV_SKLADU_PO_ODECTU.xlsx"
    )

