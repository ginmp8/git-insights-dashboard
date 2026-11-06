$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git não encontrado no PATH.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3 -m venv .venv
}
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $Python -c 'import streamlit, plotly, pandas' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha na instalação das dependências.' }
}
& $Python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
