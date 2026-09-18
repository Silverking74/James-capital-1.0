import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta, date
import json
import os
import uuid
import io

st.set_page_config(
    page_title="Hedge Fund Terminal – Spot + CFD Pro",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ====================== THEME ======================
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

def apply_theme():
    if st.session_state.theme == "dark":
        st.markdown(""" <style> .stApp { background-color: #0e1117; color: #fafafa; } .stMetric { background-color: #1a1d24; padding: 14px; border-radius: 10px; border: 1px solid #2d3340; } section[data-testid="stSidebar"] { background-color: #161b22; } .stTabs [data-baseweb="tab"] { background-color: #1a1d24; border-radius: 8px; } div[data-testid="stExpander"] { background-color: #1a1d24; border-radius: 8px; } </style> """, unsafe_allow_html=True)
    else:
        st.markdown(""" <style> .stApp { background-color: #f8f9fa; color: #212529; } .stMetric { background-color: #ffffff; padding: 14px; border-radius: 10px; border: 1px solid #dee2e6; } section[data-testid="stSidebar"] { background-color: #e9ecef; } </style> """, unsafe_allow_html=True)

apply_theme()

# ====================== STATE ======================
STARTING_CAPITAL = 1_000_000.0
DATA_FILE = "hf_terminal_final.json"

def default_state():
    return {
        "cash": STARTING_CAPITAL,
        "positions": {},
        "trade_history": [],
        "open_orders": [],
        "equity_curve": [{"date": datetime.now().isoformat(), "equity": STARTING_CAPITAL}],
        "watchlist": ["AAPL", "NVDA", "MSFT", "BTC-USD", "ETH-USD", "EURUSD=X", "TSLA"],
        "realized_pnl": 0.0,
        "financing_paid": 0.0,
        "financing_history": [],
        "settings": {
            "max_position_pct": 0.30,
            "default_risk_pct": 0.01,
            "commission_pct": 0.0005,
            "cfd_long_rate": 0.085,
            "cfd_short_rate": -0.015,
            "margin_call_threshold": 0.15
        }
    }

def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
                base = default_state()
                base.update(data)
                return base
        except:
            pass
    return default_state()

def save_state(state):
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)

if "state" not in st.session_state:
    st.session_state.state = load_state()

state = st.session_state.state
settings = state["settings"]

# ====================== HELPERS ======================
def normalize_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    crypto = {"BTC":"BTC-USD","ETH":"ETH-USD","SOL":"SOL-USD","BNB":"BNB-USD","XRP":"XRP-USD","ADA":"ADA-USD","DOGE":"DOGE-USD"}
    forex = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","AUDUSD":"AUDUSD=X","USDCAD":"USDCAD=X"}
    return crypto.get(symbol, forex.get(symbol, symbol))

def get_alpha_vantage_key():
    """Read the Alpha Vantage API key from Streamlit secrets or an environment variable."""
    try:
        key = st.secrets.get("ALPHAVANTAGE_API_KEY")
        if key:
            return str(key).strip()
    except Exception:
        pass
    return os.getenv("ALPHAVANTAGE_API_KEY", "").strip()


@st.cache_data(ttl=60, show_spinner=False)
def get_quote(symbol: str):
    """Fetch a quote from Alpha Vantage while preserving the app's existing symbols."""
    try:
        original = symbol.upper().strip()
        symbol = normalize_symbol(original)
        api_key = get_alpha_vantage_key()

        if not api_key:
            return None

        base_url = "https://www.alphavantage.co/query"

        # Forex symbols used by the original app are represented as EURUSD=X, etc.
        if symbol.endswith("=X"):
            pair = symbol[:-2]
            if len(pair) != 6:
                return None

            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": pair[:3],
                "to_currency": pair[3:],
                "apikey": api_key,
            }
            data = requests.get(base_url, params=params, timeout=10).json()
            quote = data.get("Realtime Currency Exchange Rate", {})
            price = quote.get("5. Exchange Rate")
            if not price:
                return None

            return {
                "symbol": symbol,
                "price": float(price),
                "name": f"{pair[:3]}/{pair[3:]}",
                "currency": pair[3:],
                "change_pct": 0.0,
                "asset_type": "Forex",
            }

        # Crypto symbols used by the original app are BTC-USD, ETH-USD, etc.
        if symbol.endswith("-USD"):
            crypto = symbol[:-4]
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": crypto,
                "to_currency": "USD",
                "apikey": api_key,
            }
            data = requests.get(base_url, params=params, timeout=10).json()
            quote = data.get("Realtime Currency Exchange Rate", {})
            price = quote.get("5. Exchange Rate")
            if not price:
                return None

            return {
                "symbol": symbol,
                "price": float(price),
                "name": crypto,
                "currency": "USD",
                "change_pct": 0.0,
                "asset_type": "Crypto",
            }

        # Stocks/ETFs: use Alpha Vantage's Global Quote endpoint.
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": api_key,
        }
        data = requests.get(base_url, params=params, timeout=10).json()
        quote = data.get("Global Quote", {})
        price = quote.get("05. price")
        if not price:
            return None

        change_pct_raw = quote.get("10. change percent", "0").replace("%", "").strip()

        return {
            "symbol": symbol,
            "price": float(price),
            "name": symbol,
            "currency": "USD",
            "change_pct": float(change_pct_raw or 0),
            "asset_type": "Equity",
        }

    except Exception:
        return None

def portfolio_value(state):
    total = state["cash"]
    for pos in state["positions"].values():
        q = get_quote(pos["symbol"])
        if q and q["price"]:
            total += pos["shares"] * q["price"]
    return total

def update_equity_curve(state):
    eq = portfolio_value(state)
    state["equity_curve"].append({"date": datetime.now().isoformat(), "equity": eq})
    state["equity_curve"] = state["equity_curve"][-2000:]

def pos_key(symbol, pos_type):
    return f"{normalize_symbol(symbol)}_{pos_type.upper()}"

def total_margin_used(state):
    return sum(pos.get("margin", 0) for pos in state["positions"].values() if pos.get("type") == "CFD")

# ====================== FINANCING + MARGIN CALL ======================
def apply_cfd_financing_and_margin_call(state):
    today = date.today()
    long_rate = settings.get("cfd_long_rate", 0.085)
    short_rate = settings.get("cfd_short_rate", -0.015)
    total_financing = 0.0
    updated = False

    for key, pos in list(state["positions"].items()):
        if pos.get("type") != "CFD":
            continue

        last_date_str = pos.get("last_financing_date") or pos.get("open_date")
        if not last_date_str:
            pos["last_financing_date"] = today.isoformat()
            pos["open_date"] = today.isoformat()
            updated = True
            continue

        last_date = date.fromisoformat(last_date_str)
        days = (today - last_date).days
        if days <= 0:
            continue

        q = get_quote(pos["symbol"])
        if not q or not q["price"]:
            continue

        notional = abs(pos["shares"] * q["price"])
        rate = long_rate if pos["shares"] > 0 else short_rate
        financing_cost = notional * (rate / 365) * days

        state["cash"] -= financing_cost
        state["financing_paid"] = state.get("financing_paid", 0.0) + financing_cost
        total_financing += financing_cost

        event = {
            "date": today.isoformat(),
            "symbol": pos["symbol"],
            "side": "LONG" if pos["shares"] > 0 else "SHORT",
            "days": days,
            "notional": round(notional, 2),
            "rate_pct": round(rate * 100, 2),
            "cost": round(financing_cost, 2)
        }
        state.setdefault("financing_history", []).append(event)

        pos["last_financing_date"] = today.isoformat()
        updated = True

    # Margin Call Protection
    margin_used = total_margin_used(state)
    free_cash = state["cash"]
    threshold = settings.get("margin_call_threshold", 0.15)

    if margin_used > 0 and free_cash < margin_used * threshold:
        st.session_state.margin_call_triggered = True

        cfd_positions = [(k, p) for k, p in state["positions"].items() if p.get("type") == "CFD"]
        cfd_positions.sort(
            key=lambda x: abs(x[1]["shares"] * (get_quote(x[1]["symbol"])["price"] if get_quote(x[1]["symbol"]) else 0)),
            reverse=True
        )

        for key, pos in cfd_positions:
            if state["cash"] >= margin_used * threshold:
                break

            q = get_quote(pos["symbol"])
            if not q:
                continue

            reduce_qty = abs(pos["shares"]) * 0.5
            if reduce_qty < 0.0001:
                continue

            price = q["price"]
            direction = 1 if pos["shares"] > 0 else -1
            signed_reduce = reduce_qty * direction

            margin_release = pos["margin"] * 0.5
            state["cash"] += margin_release
            pos["margin"] *= 0.5
            pos["shares"] -= signed_reduce

            state["trade_history"].append({
                "time": datetime.now().isoformat(),
                "symbol": pos["symbol"],
                "side": "SELL" if direction > 0 else "BUY",
                "qty": reduce_qty,
                "price": price,
                "type": "CFD",
                "leverage": pos.get("leverage", 1),
                "commission": 0,
                "note": "MARGIN CALL REDUCTION"
            })

            if abs(pos["shares"]) < 0.0001:
                del state["positions"][key]

            margin_used = total_margin_used(state)
            updated = True

    if updated:
        state["financing_history"] = state.get("financing_history", [])[-300:]
        update_equity_curve(state)
        save_state(state)

    return total_financing

financing_today = apply_cfd_financing_and_margin_call(state)

# ====================== ORDER EXECUTION ======================
def execute_order(state, symbol, side, qty, price, pos_type="SPOT", leverage=1.0):
    symbol = normalize_symbol(symbol)
    key = pos_key(symbol, pos_type)
    commission = abs(qty * price * settings["commission_pct"])
    notional = qty * price
    today_str = date.today().isoformat()

    if pos_type == "SPOT":
        if side == "BUY":
            cost = notional + commission
            if cost > state["cash"]:
                return False, "Insufficient cash for Spot"
            state["cash"] -= cost
            if key in state["positions"]:
                pos = state["positions"][key]
                new_qty = pos["shares"] + qty
                new_avg = (pos["shares"] * pos["avg_cost"] + notional) / new_qty
                state["positions"][key].update({"shares": new_qty, "avg_cost": new_avg})
            else:
                state["positions"][key] = {
                    "symbol": symbol, "type": "SPOT", "shares": qty,
                    "avg_cost": price, "leverage": 1.0, "margin": 0,
                    "open_date": today_str
                }
        else:
            if key not in state["positions"] or state["positions"][key]["shares"] < qty - 1e-9:
                return False, "Not enough shares"
            proceeds = notional - commission
            avg = state["positions"][key]["avg_cost"]
            realized = (price - avg) * qty - commission
            state["positions"][key]["shares"] -= qty
            if state["positions"][key]["shares"] <= 1e-9:
                del state["positions"][key]
            state["cash"] += proceeds
            state["realized_pnl"] = state.get("realized_pnl", 0) + realized
    else:
        margin_required = notional / leverage
        if margin_required + commission > state["cash"]:
            return False, "Insufficient margin"

        state["cash"] -= (margin_required + commission)
        signed_qty = qty if side == "BUY" else -qty

        if key in state["positions"]:
            old_margin = state["positions"][key].get("margin", 0)
            state["cash"] += old_margin
            del state["positions"][key]

        state["positions"][key] = {
            "symbol": symbol,
            "type": "CFD",
            "shares": signed_qty,
            "avg_cost": price,
            "leverage": leverage,
            "margin": margin_required,
            "open_date": today_str,
            "last_financing_date": today_str
        }

    state["trade_history"].append({
        "time": datetime.now().isoformat(),
        "symbol": symbol,
        "side": side,
        "qty": abs(qty),
        "price": price,
        "type": pos_type,
        "leverage": leverage if pos_type == "CFD" else 1.0,
        "commission": commission
    })
    update_equity_curve(state)
    return True, "Order executed"

# ====================== SIDEBAR ======================
st.sidebar.title("🏦 HF Terminal Pro")
st.sidebar.caption("Spot + CFD • Asymmetric Financing • Margin Protection")

if st.sidebar.button("☀️ / 🌙 Theme", use_container_width=True):
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
    st.rerun()

current_equity = portfolio_value(state)
pnl = current_equity - STARTING_CAPITAL
pnl_pct = pnl / STARTING_CAPITAL * 100

st.sidebar.metric("Total Equity", f"${current_equity:,.0f}", f"{pnl:+,.0f} ({pnl_pct:+.2f}%)")
st.sidebar.metric("Available Cash", f"${state['cash']:,.0f}")
st.sidebar.metric("Financing Paid", f"${state.get('financing_paid', 0):,.2f}")
st.sidebar.metric("Margin Used", f"${total_margin_used(state):,.0f}")

if financing_today != 0:
    st.sidebar.metric("Today's Financing", f"${financing_today:+,.2f}")

if st.session_state.get("margin_call_triggered"):
    st.sidebar.error("⚠️ MARGIN CALL – Positions reduced")

st.sidebar.markdown("---")
st.sidebar.subheader("Place Order")

trade_symbol = st.sidebar.text_input("Symbol", "AAPL").upper()
trade_side = st.sidebar.radio("Side", ["BUY", "SELL"], horizontal=True)
trade_qty = st.sidebar.number_input("Quantity", min_value=0.0001, value=10.0, format="%.4f")

pos_type = st.sidebar.selectbox("Position Type", ["SPOT (Cash / Physical)", "CFD (Leveraged)"])
leverage = 1.0
if "CFD" in pos_type:
    leverage = st.sidebar.slider("Leverage", 1.0, 20.0, 5.0, 0.5)
    st.sidebar.caption(f"Long rate: {settings['cfd_long_rate']*100:.1f}% | Short rate: {settings['cfd_short_rate']*100:.1f}%")

if st.sidebar.button("Submit Order", type="primary", use_container_width=True):
    q = get_quote(trade_symbol)
    if not q:
        st.sidebar.error("Could not fetch price")
    else:
        ptype = "CFD" if "CFD" in pos_type else "SPOT"
        success, msg = execute_order(state, trade_symbol, trade_side, trade_qty, q["price"], ptype, leverage)
        if success:
            save_state(state)
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)

st.sidebar.markdown("---")
if st.sidebar.button("Reset Portfolio"):
    st.session_state.state = default_state()
    save_state(st.session_state.state)
    st.rerun()

# ====================== MAIN ======================
st.title("🏦 Hedge Fund Terminal – Spot + CFD Pro")
st.caption("Multi-asset paper trading • Long/Short financing • Financing log • Automatic margin call protection")

tabs = st.tabs([
    "📊 Dashboard",
    "💼 Positions",
    "📜 Financing History",
    "📈 Performance",
    "🧮 Position Sizer",
    "📚 Lessons",
    "⚙️ Settings & Export"
])

# ---------- DASHBOARD ----------
with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Equity", f"${current_equity:,.0f}")
    c2.metric("Cash", f"${state['cash']:,.0f}")
    c3.metric("Financing Paid", f"${state.get('financing_paid',0):,.2f}")
    c4.metric("Margin Used", f"${total_margin_used(state):,.0f}")

    if financing_today != 0:
        st.info(f"Overnight financing applied: **${financing_today:+,.2f}**")

    if st.session_state.get("margin_call_triggered"):
        st.error("Margin call triggered — some CFD positions were automatically reduced.")

    # Better Equity Curve
    if len(state["equity_curve"]) > 2:
        eq_df = pd.DataFrame(state["equity_curve"])
        eq_df["date"] = pd.to_datetime(eq_df["date"])
        eq_df = eq_df.sort_values("date")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq_df["date"], y=eq_df["equity"],
            mode="lines", name="Equity",
            line=dict(color="#00d4aa", width=2.8),
            fill="tozeroy", fillcolor="rgba(0,212,170,0.12)"
        ))
        fig.add_hline(y=STARTING_CAPITAL, line_dash="dot", line_color="gray",
                      annotation_text="Starting Capital", annotation_position="bottom right")
        fig.update_layout(
            title="Fund Equity Curve",
            height=420,
            template="plotly_dark" if st.session_state.theme == "dark" else "plotly_white",
            margin=dict(l=20, r=20, t=50, b=20),
            hovermode="x unified",
            yaxis_title="Equity ($)"
        )
        st.plotly_chart(fig, use_container_width=True)

    # Allocation Pie (if positions exist)
    if state["positions"]:
        alloc_data = []
        for pos in state["positions"].values():
            q = get_quote(pos["symbol"])
            if q:
                value = abs(pos["shares"] * q["price"])
                alloc_data.append({"Symbol": f"{pos['symbol']} ({pos['type']})", "Value": value})
        if alloc_data:
            alloc_df = pd.DataFrame(alloc_data)
            fig_pie = px.pie(alloc_df, values="Value", names="Symbol", title="Current Allocation",
                             hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(template="plotly_dark" if st.session_state.theme == "dark" else "plotly_white",
                                  height=380, margin=dict(t=40, b=20, l=20, r=20))
            st.plotly_chart(fig_pie, use_container_width=True)

# ---------- POSITIONS ----------
with tabs[1]:
    st.subheader("Open Positions – Spot & CFD")
    if not state["positions"]:
        st.info("No open positions. Place trades from the sidebar.")
    else:
        rows = []
        for key, pos in state["positions"].items():
            q = get_quote(pos["symbol"])
            price = q["price"] if q else 0
            mv = pos["shares"] * price
            upnl = mv - (pos["shares"] * pos["avg_cost"])
            rows.append({
                "Symbol": pos["symbol"],
                "Type": pos["type"],
                "Side": "LONG" if pos["shares"] > 0 else "SHORT",
                "Qty": abs(round(pos["shares"], 4)),
                "Leverage": f"{pos.get('leverage',1):.1f}x",
                "Avg Cost": f"{pos['avg_cost']:.4f}",
                "Last": f"{price:.4f}",
                "Value": f"${abs(mv):,.0f}",
                "Unrealized P&L": f"${upnl:+,.0f}",
                "Margin": f"${pos.get('margin',0):,.0f}"
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------- FINANCING HISTORY ----------
with tabs[2]:
    st.subheader("Detailed Financing History")
    history = state.get("financing_history", [])
    if not history:
        st.info("No financing events yet. Open CFD positions and return tomorrow (or change system date to test).")
    else:
        df = pd.DataFrame(history[::-1])
        st.dataframe(df, use_container_width=True, hide_index=True)

        paid = sum(e["cost"] for e in history if e["cost"] > 0)
        received = sum(-e["cost"] for e in history if e["cost"] < 0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Paid (Longs)", f"${paid:,.2f}")
        c2.metric("Total Received (Shorts)", f"${received:,.2f}")
        c3.metric("Net Financing Cost", f"${state.get('financing_paid',0):+,.2f}")

# ---------- PERFORMANCE ----------
with tabs[3]:
    st.subheader("Performance Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", f"{pnl_pct:+.2f}%")
    c2.metric("Realized P&L", f"${state.get('realized_pnl',0):+,.2f}")
    c3.metric("Net Financing", f"${state.get('financing_paid',0):+,.2f}")
    c4.metric("Current Equity", f"${current_equity:,.0f}")

    closed = [t for t in state["trade_history"] if "note" not in t or t.get("note") != "MARGIN CALL REDUCTION"]
    st.write(f"Total trades recorded: **{len(state['trade_history'])}**")

# ---------- POSITION SIZER ----------
with tabs[4]:
    st.subheader("Professional Position Size Calculator")
    st.caption("Classic hedge fund rule: risk only 0.5–2% of equity per idea")

    col1, col2 = st.columns(2)
    with col1:
        eq = st.number_input("Fund Equity ($)", value=float(current_equity), step=10000.0)
        risk_pct = st.number_input("Risk per Trade (%)", value=1.0, step=0.25) / 100
    with col2:
        entry = st.number_input("Entry Price", value=100.0, format="%.4f")
        stop = st.number_input("Stop-Loss Price", value=95.0, format="%.4f")

    risk_amount = eq * risk_pct
    risk_per_unit = abs(entry - stop)
    size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
    pos_value = size * entry

    m1, m2, m3 = st.columns(3)
    m1.metric("Recommended Size", f"{size:.4f}")
    m2.metric("Position Value", f"${pos_value:,.0f}")
    m3.metric("Capital at Risk", f"${risk_amount:,.0f}")

    if pos_value / eq > settings["max_position_pct"]:
        st.warning(f"This size exceeds your max position limit ({settings['max_position_pct']*100:.0f}% of equity)")

# ---------- LESSONS ----------
with tabs[5]:
    st.header("📚 Hedge Fund Knowledge Base")

    with st.expander("What this terminal simulates", expanded=True):
        st.markdown(""" This is a **multi-strategy hedge fund style simulator**: - **Spot / Physical book** → Real ownership of stocks & crypto (full capital used) - **CFD book** → Leveraged, long & short, margin-based synthetic exposure - Automated overnight financing with **different rates for Long vs Short** - Automatic margin call protection - Full trade & financing history """)

    with st.expander("Long vs Short CFD Financing Rates"):
        st.markdown(f""" **Current settings:** - Long CFD rate: **{settings['cfd_long_rate']*100:.2f}%** (you pay) - Short CFD rate: **{settings['cfd_short_rate']*100:.2f}%** ({'you pay' if settings['cfd_short_rate'] > 0 else 'you receive credit'}) In real markets: - Longs almost always cost money to hold overnight - Shorts frequently earn a small credit (or cost much less) - This creates a natural bias: structurally long CFD books bleed financing every day """)

    with st.expander("Margin Calls & Risk Management"):
        st.markdown(""" When financing or losses reduce free cash too far relative to margin used, a **margin call** is triggered. This simulator automatically reduces the largest CFD positions by 50% until free cash is restored above the safety threshold. Professional rules practiced here: - Risk only 0.5–2% of equity per trade - Keep meaningful free cash buffer - Monitor financing drag on leveraged positions - Diversify across uncorrelated ideas """)

# ---------- SETTINGS & EXPORT ----------
with tabs[6]:
    st.subheader("Settings")

    settings["max_position_pct"] = st.slider("Max Position Size (% of equity)", 5, 50, int(settings["max_position_pct"]*100)) / 100
    settings["default_risk_pct"] = st.slider("Default Risk per Trade (%)", 0.25, 3.0, float(settings["default_risk_pct"]*100), 0.25) / 100
    settings["margin_call_threshold"] = st.slider("Margin Call Free-Cash Threshold", 0.05, 0.40, float(settings.get("margin_call_threshold", 0.15)), 0.05)

    st.markdown("### CFD Financing Rates (Annualized)")
    c1, c2 = st.columns(2)
    with c1:
        settings["cfd_long_rate"] = st.number_input("Long CFD Rate (%)", value=float(settings.get("cfd_long_rate", 0.085)*100), step=0.25) / 100
    with c2:
        settings["cfd_short_rate"] = st.number_input("Short CFD Rate (%)", value=float(settings.get("cfd_short_rate", -0.015)*100), step=0.25) / 100

    if st.button("💾 Save Settings", type="primary"):
        state["settings"] = settings
        save_state(state)
        st.success("Settings saved successfully")

    st.markdown("---")
    st.subheader("Export Data")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if state["trade_history"]:
            trade_df = pd.DataFrame(state["trade_history"])
            st.download_button(
                "📥 Download Trade Journal",
                trade_df.to_csv(index=False),
                "trade_journal.csv",
                "text/csv",
                use_container_width=True
            )

    with col_b:
        if state.get("financing_history"):
            fin_df = pd.DataFrame(state["financing_history"])
            st.download_button(
                "📥 Download Financing Log",
                fin_df.to_csv(index=False),
                "financing_history.csv",
                "text/csv",
                use_container_width=True
            )

    with col_c:
        # Performance summary
        summary = {
            "Starting Capital": STARTING_CAPITAL,
            "Current Equity": current_equity,
            "Total Return %": round(pnl_pct, 2),
            "Realized P&L": state.get("realized_pnl", 0),
            "Financing Paid": state.get("financing_paid", 0),
            "Open Positions": len(state["positions"]),
            "Total Trades": len(state["trade_history"])
        }
        summary_df = pd.DataFrame([summary])
        st.download_button(
            "📥 Download Performance Summary",
            summary_df.to_csv(index=False),
            "performance_summary.csv",
            "text/csv",
            use_container_width=True
        )

st.markdown("---")
st.caption("Educational multi-asset hedge fund simulator (Spot + CFD) with asymmetric financing, full history log and automatic margin-call protection. Not financial advice.")
```