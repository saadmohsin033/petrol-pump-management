# Petrol Pump Management Dashboard

Streamlit dashboard connected to the existing MySQL `petrol_pump_db`.

## Features
- Connection test and pooled SSL MySQL connections
- Overview metrics, stock view, recent sales
- Daily/monthly sales charts and fuel-wise revenue
- Sale entry that inserts `Fuel_Sale` and `Payment` atomically
- Read-only table/view explorer and CSV export

## Important schema notes
- The existing `Fuel_Sale` BEFORE INSERT trigger computes `total_amount` and deducts stock. The app does not deduct stock a second time.
- `Payment` stores the payment method, so sale entry inserts both records in one transaction.
- The supplied schema has no pump/nozzle identifier on `Fuel_Sale`; nozzle-wise analytics require a schema extension.
- The app assumes your Aiven database has the uploaded schema imported, including its triggers and views.

## Setup on Windows / VS Code
1. Open this folder in VS Code.
2. In the terminal, create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again.

3. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, then replace `DB_PASSWORD` with the rotated Aiven password. Keep `.env` private and never commit it.
5. In Aiven, allow connections from your current public IP (or use the provider's secure networking option). Download the Aiven CA certificate and set `DB_SSL_CA` to its path for certificate verification.
6. Launch:

   ```powershell
   streamlit run app.py
   ```

7. Streamlit prints a local URL, usually `http://localhost:8501`. Open it in your browser.

## Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Edit .env securely, then:
streamlit run app.py
```

## Troubleshooting
- **Access denied / timeout:** check host, port, username, password, Aiven service status, and allowed IPs.
- **SSL error:** download the CA certificate from Aiven and set `DB_SSL_CA` to the correct file path.
- **Missing table/column:** ensure the dump was imported into `petrol_pump_db` on Aiven. Do not re-import the dump over a live database without a backup because it contains `DROP TABLE` statements.
- **Sale fails with insufficient stock:** check `Fuel.current_stock`; the database trigger blocks sales above available stock.
- **Nozzle charts:** add a nozzle/pump relationship to the schema before claiming nozzle-level reporting.
