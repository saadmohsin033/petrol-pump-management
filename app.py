"""Streamlit dashboard for the Petrol Pump Management System."""
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from db import get_engine, test_connection, read_df, get_table_names, read_table, record_sale

st.set_page_config(
    page_title="Petrol Pump Management",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    div[data-testid="stMetric"] {
        background: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.18);
        padding: 14px 16px;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

st.title("⛽ Petrol Pump Management")
st.caption("Sales • Inventory • Payments • Operational insights")

@st.cache_resource
def cached_engine():
    return get_engine()

try:
    engine = cached_engine()
    status = test_connection(engine)
    st.sidebar.success(status)
except Exception as exc:
    st.error("Could not connect to MySQL.")
    st.code(str(exc))
    st.info("Check your .env credentials, Aiven service status, allowed IPs, SSL CA setting, and database name.")
    st.stop()

# Refresh is useful after inserts or when teammates make database changes.
if st.sidebar.button("🔄 Refresh dashboard"):
    st.cache_data.clear()
    st.rerun()

page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Sales & Analytics", "Record a Sale", "Database Explorer"],
)

def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    return read_df(engine, sql, params)

def money(value) -> str:
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"

if page == "Overview":
    st.subheader("Overview")
    try:
        summary = query("""
            SELECT
                COALESCE(SUM(CASE WHEN DATE(sale_datetime) = CURDATE()
                                  THEN total_amount ELSE 0 END), 0) AS today_revenue,
                COALESCE(SUM(CASE WHEN YEAR(sale_datetime) = YEAR(CURDATE())
                                   AND MONTH(sale_datetime) = MONTH(CURDATE())
                                  THEN total_amount ELSE 0 END), 0) AS month_revenue,
                COUNT(CASE WHEN DATE(sale_datetime) = CURDATE() THEN 1 END) AS today_transactions,
                COALESCE(SUM(quantity), 0) AS litres_sold
            FROM Fuel_Sale
        """).iloc[0]
        stock = query("SELECT fuel_name, unit_price, current_stock, capacity FROM Fuel ORDER BY fuel_name")
        recent = query("""
            SELECT s.sale_id, s.sale_datetime, f.fuel_name, s.quantity,
                   s.price_per_litre, s.total_amount, e.employee_name,
                   p.payment_method, p.payment_status
            FROM Fuel_Sale s
            JOIN Fuel f ON f.fuel_id = s.fuel_id
            JOIN Employee e ON e.employee_id = s.employee_id
            LEFT JOIN Payment p ON p.sale_id = s.sale_id
            ORDER BY s.sale_datetime DESC, s.sale_id DESC
            LIMIT 10
        """)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Today's revenue", money(summary["today_revenue"]))
        c2.metric("This month's revenue", money(summary["month_revenue"]))
        c3.metric("Today's transactions", f"{int(summary['today_transactions']):,}")
        c4.metric("Total litres sold", f"{float(summary['litres_sold']):,.2f} L")

        left, right = st.columns(2)
        with left:
            st.markdown("#### Current fuel stock")
            if not stock.empty:
                stock["Stock used (%)"] = (stock["current_stock"] / stock["capacity"] * 100).round(1)
                st.dataframe(
                    stock.rename(columns={
                        "fuel_name": "Fuel", "unit_price": "Price/L (₹)",
                        "current_stock": "Current stock (L)", "capacity": "Capacity (L)"
                    }),
                    use_container_width=True, hide_index=True
                )
                st.plotly_chart(px.bar(
                    stock, x="fuel_name", y="current_stock", color="fuel_name",
                    labels={"fuel_name": "Fuel", "current_stock": "Stock (litres)"},
                    title="Stock by fuel type"
                ), use_container_width=True)
            else:
                st.info("No fuel types found in Fuel.")
        with right:
            st.markdown("#### Stock capacity usage")
            if not stock.empty:
                fig = px.pie(stock, names="fuel_name", values="current_stock", hole=0.55,
                             title="Share of current stock")
                st.plotly_chart(fig, use_container_width=True)
                stock["Stock remaining (%)"] = (
                    stock["current_stock"] / stock["capacity"] * 100
                ).round(1)
                st.dataframe(stock[["fuel_name", "Stock remaining (%)"]].rename(
                    columns={"fuel_name": "Fuel"}
                ), use_container_width=True, hide_index=True)
        st.markdown("#### Recent transactions")
        st.dataframe(recent, use_container_width=True, hide_index=True)
    except SQLAlchemyError as exc:
        st.error("A dashboard query failed. Confirm the uploaded schema has been imported correctly.")
        st.exception(exc)

elif page == "Sales & Analytics":
    st.subheader("Sales & Analytics")
    try:
        sales = query("""
            SELECT s.sale_id, s.sale_datetime, f.fuel_name, s.quantity,
                   s.price_per_litre, s.total_amount, e.employee_name
            FROM Fuel_Sale s
            JOIN Fuel f ON f.fuel_id = s.fuel_id
            JOIN Employee e ON e.employee_id = s.employee_id
            ORDER BY s.sale_datetime
        """)
        if sales.empty:
            st.info("No sales yet. Record a sale to populate analytics.")
        else:
            sales["sale_datetime"] = pd.to_datetime(sales["sale_datetime"])
            min_date = sales["sale_datetime"].min().date()
            max_date = sales["sale_datetime"].max().date()
            d1, d2 = st.columns(2)
            start_date = d1.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
            end_date = d2.date_input("To", value=max_date, min_value=min_date, max_value=max_date)
            if start_date > end_date:
                st.warning("'From' date must be on or before 'To' date.")
                st.stop()
            filtered = sales[
                (sales["sale_datetime"].dt.date >= start_date)
                & (sales["sale_datetime"].dt.date <= end_date)
            ].copy()

            a, b, c = st.columns(3)
            a.metric("Revenue in selected period", money(filtered["total_amount"].sum()))
            b.metric("Litres sold", f"{filtered['quantity'].sum():,.2f} L")
            c.metric("Transactions", f"{len(filtered):,}")

            filtered["sale_day"] = filtered["sale_datetime"].dt.date
            daily = filtered.groupby("sale_day", as_index=False).agg(
                revenue=("total_amount", "sum"), litres=("quantity", "sum")
            )
            st.plotly_chart(px.line(
                daily, x="sale_day", y="revenue", markers=True,
                labels={"sale_day": "Date", "revenue": "Revenue (₹)"},
                title="Daily revenue trend"
            ), use_container_width=True)

            monthly = filtered.assign(month=filtered["sale_datetime"].dt.to_period("M").astype(str))
            monthly = monthly.groupby("month", as_index=False)["total_amount"].sum()
            st.plotly_chart(px.bar(
                monthly, x="month", y="total_amount",
                labels={"month": "Month", "total_amount": "Revenue (₹)"},
                title="Monthly revenue"
            ), use_container_width=True)

            by_fuel = filtered.groupby("fuel_name", as_index=False).agg(
                revenue=("total_amount", "sum"), litres=("quantity", "sum")
            )
            left, right = st.columns(2)
            left.plotly_chart(px.bar(
                by_fuel, x="fuel_name", y="revenue", color="fuel_name",
                labels={"fuel_name": "Fuel type", "revenue": "Revenue (₹)"},
                title="Revenue by fuel type"
            ), use_container_width=True)
            right.plotly_chart(px.pie(
                by_fuel, names="fuel_name", values="litres", hole=0.5,
                title="Litres sold by fuel type"
            ), use_container_width=True)

            st.markdown("#### Sales records")
            st.dataframe(filtered.drop(columns=["sale_day"], errors="ignore"),
                         use_container_width=True, hide_index=True)
            st.download_button(
                "Download filtered sales as CSV",
                data=filtered.to_csv(index=False).encode("utf-8"),
                file_name="petrol_pump_sales.csv",
                mime="text/csv",
            )
            st.caption("Nozzle-wise revenue is not available in the supplied schema because Fuel_Sale has no nozzle/pump identifier. Add a Pump_Nozzle table and a foreign key before reporting by nozzle.")
    except SQLAlchemyError as exc:
        st.error("Unable to load analytics.")
        st.exception(exc)

elif page == "Record a Sale":
    st.subheader("Record a Sale")
    st.caption("The form uses your existing Fuel_Sale and Payment tables. Stock deduction and total calculation are handled by your database trigger.")
    try:
        fuels = query("SELECT fuel_id, fuel_name, unit_price, current_stock FROM Fuel ORDER BY fuel_name")
        employees = query("SELECT employee_id, employee_name, role FROM Employee ORDER BY employee_name")
        customers = query("SELECT customer_id, customer_name FROM Customer ORDER BY customer_name")

        if fuels.empty or employees.empty:
            st.warning("Add at least one fuel type and one employee before recording sales.")
        else:
            fuel_labels = {
                f"{r.fuel_name} — ₹{float(r.unit_price):.2f}/L — {float(r.current_stock):,.2f} L available": int(r.fuel_id)
                for r in fuels.itertuples()
            }
            employee_labels = {
                f"{r.employee_name} ({r.role})": int(r.employee_id)
                for r in employees.itertuples()
            }
            customer_labels = {"Walk-in / no customer record": None}
            customer_labels.update({
                f"{r.customer_name} (ID {int(r.customer_id)})": int(r.customer_id)
                for r in customers.itertuples()
            })

            with st.form("sale_form", clear_on_submit=True):
                fuel_label = st.selectbox("Fuel type", list(fuel_labels))
                fuel_id = fuel_labels[fuel_label]
                fuel_row = fuels.loc[fuels["fuel_id"] == fuel_id].iloc[0]
                employee_label = st.selectbox("Processed by", list(employee_labels))
                customer_label = st.selectbox("Customer (optional)", list(customer_labels))
                quantity = st.number_input("Quantity (litres)", min_value=0.01, max_value=100000.0,
                                           value=10.0, step=1.0)
                price = st.number_input("Price per litre (₹)", min_value=0.0, max_value=10000.0,
                                        value=float(fuel_row["unit_price"]), step=0.5)
                payment_method = st.selectbox("Payment method", ["Cash", "UPI", "Card", "Credit"])
                st.write(f"**Estimated total:** ₹{quantity * price:,.2f}")
                submitted = st.form_submit_button("Save sale", type="primary")

            if submitted:
                if quantity > float(fuel_row["current_stock"]):
                    st.error(f"Insufficient stock. Available: {float(fuel_row['current_stock']):,.2f} L")
                else:
                    try:
                        sale_id = record_sale(
                            engine=engine,
                            fuel_id=fuel_id,
                            employee_id=employee_labels[employee_label],
                            customer_id=customer_labels[customer_label],
                            quantity=float(quantity),
                            price_per_litre=float(price),
                            payment_method=payment_method,
                        )
                        st.success(f"Sale #{sale_id} recorded successfully.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error("Sale could not be saved. The database transaction was rolled back.")
                        st.exception(exc)
    except SQLAlchemyError as exc:
        st.error("Unable to load form options.")
        st.exception(exc)

elif page == "Database Explorer":
    st.subheader("Database Explorer")
    st.caption("Read-only explorer for tables and views. Use a database client for schema changes.")
    try:
        tables = get_table_names(engine)
        if not tables:
            st.info("No tables or views found in the selected database.")
        else:
            selected = st.selectbox("Select a table or view", tables)
            limit = st.select_slider("Maximum rows to display", options=[50, 100, 250, 500, 1000], value=250)
            data = read_table(engine, selected, int(limit))
            st.write(f"**{selected}** — showing {len(data)} row(s)")
            st.dataframe(data, use_container_width=True, hide_index=True)
            st.download_button(
                f"Download {selected} as CSV",
                data=data.to_csv(index=False).encode("utf-8"),
                file_name=f"{selected}.csv",
                mime="text/csv",
            )
            with st.expander("Column / schema details"):
                st.dataframe(pd.DataFrame({"Column": data.columns}), use_container_width=True, hide_index=True)
    except SQLAlchemyError as exc:
        st.error("Unable to inspect the database.")
        st.exception(exc)

st.sidebar.divider()
st.sidebar.caption("PBL prototype • Keep database credentials private.")
