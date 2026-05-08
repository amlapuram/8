import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- CONFIGURATION & TICKER MAPPING ---
TICKERS = {
    "SBI": "SBIN.NS",
    "Canara Bank": "CANBK.NS",
    "Wipro": "WIPRO.NS",
    "Petronet LNG": "PETRONET.NS",
    "IOB": "IOB.NS",
    "Morepen Labs": "MOREPENLAB.NS",
    "Tata Motors Commercial": "TMCV.NS",
    "Yes Bank": "YESBANK.NS",
    "HINDZINC": "HINDZINC.NS",
    "ITC": "ITC.NS",
    "Bank of Baroda": "BANKBARODA.NS",
}

DB_NAME = "stocks_data.db"


# --- DATABASE OPERATIONS ---
def init_db():
    """Initializes a table specifically designed to hold historical 5-minute ticks."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS intraday_data (
            ticker TEXT,
            company_name TEXT,
            timestamp TEXT,
            price REAL,
            volume INTEGER,
            PRIMARY KEY (ticker, timestamp)
        )
    ''')
    conn.commit()
    conn.close()


def purge_old_data():
    """Deletes all records from previous days, keeping only today's data."""
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM intraday_data WHERE timestamp NOT LIKE ?", (f"{today_prefix}%",))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        st.toast(f"🗑️ Cleared {deleted} stale records from previous day(s).", icon="🗑️")


def fetch_and_store_data():
    """Fetches today's 5-minute interval data and saves it to the database."""
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for name, ticker in TICKERS.items():
        try:
            stock = yf.Ticker(ticker)
            # Fetch data for today in 5-minute intervals
            hist = stock.history(period="1d", interval="5m")

            if not hist.empty:
                for timestamp, row in hist.iterrows():
                    # Convert Yahoo Finance timestamp to local IST string
                    if timestamp.tzinfo is not None:
                        ts_str = timestamp.tz_convert('Asia/Kolkata').strftime("%Y-%m-%d %H:%M")
                    else:
                        ts_str = timestamp.strftime("%Y-%m-%d %H:%M")

                    # ✅ Skip any candle not belonging to today (safety guard)
                    if not ts_str.startswith(today_prefix):
                        continue

                    price = round(row['Close'], 2)
                    volume = int(row['Volume'])

                    cursor.execute('''
                        INSERT OR REPLACE INTO intraday_data 
                        (ticker, company_name, timestamp, price, volume)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (ticker, name, ts_str, price, volume))

        except Exception as e:
            st.error(f"Failed to fetch data for {name} ({ticker}): {e}")

    conn.commit()
    conn.close()


def load_data_from_db():
    """Reads only TODAY's intraday market data from SQLite."""
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(
        "SELECT * FROM intraday_data WHERE timestamp LIKE ? ORDER BY timestamp ASC",
        conn,
        params=(f"{today_prefix}%",)
    )
    conn.close()
    return df


# --- UI DESIGN (STREAMLIT) ---
st.set_page_config(page_title="Intraday Stock Tracker", page_icon="📊", layout="wide")

# Trigger Auto-Refresh every 5 minutes (300,000 milliseconds)
st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

# Initialize Database
init_db()

st.title("📊 Live 5-Minute Volume & Price Tracker")
st.markdown(
    "This dashboard tracks **intraday volume and price** in 5-minute intervals. Select a tab below to view the specific stock.")
st.divider()

# Purge stale previous-day records first
purge_old_data()

# Fetch latest data
with st.spinner("Syncing latest 5-minute intervals from NSE..."):
    fetch_and_store_data()

# Load Data for UI
df = load_data_from_db()

if not df.empty:
    st.caption(f"**Last Sync:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Create a tab for each company
    company_names = list(TICKERS.keys())
    tabs = st.tabs(company_names)

    for tab, company_name in zip(tabs, company_names):
        with tab:
            ticker = TICKERS[company_name]
            df_stock = df[df['ticker'] == ticker].copy()

            if not df_stock.empty:
                latest_price = df_stock['price'].iloc[-1]
                latest_vol = df_stock['volume'].iloc[-1]
                latest_time = df_stock['timestamp'].iloc[-1]

                st.subheader(f"{company_name} ({ticker})")
                st.markdown(f"**Latest Data ({latest_time}):** ₹{latest_price:,.2f} | **Volume:** {latest_vol:,}")

                # --- PLOTLY DUAL-AXIS CHART ---
                fig = make_subplots(specs=[[{"secondary_y": True}]])

                fig.add_trace(
                    go.Bar(x=df_stock['timestamp'], y=df_stock['volume'], name="Volume", opacity=0.3,
                           marker_color='blue'),
                    secondary_y=False,
                )

                fig.add_trace(
                    go.Scatter(x=df_stock['timestamp'], y=df_stock['price'], name="Price (₹)", mode='lines+markers',
                               marker_color='red'),
                    secondary_y=True,
                )

                fig.update_layout(
                    title_text=f"Intraday Performance: {company_name}",
                    height=500,
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )

                fig.update_yaxes(title_text="<b>Volume</b>", secondary_y=False)
                fig.update_yaxes(title_text="<b>Stock Price (₹)</b>", secondary_y=True)

                st.plotly_chart(fig, use_container_width=True)

                with st.expander("View Raw Data Table"):
                    st.dataframe(
                        df_stock[['timestamp', 'price', 'volume']].sort_values(by='timestamp', ascending=False),
                        hide_index=True)

            else:
                st.info(f"No intraday data available yet for {company_name}.")

else:
    st.warning("No data found in the database. Check your connection.")