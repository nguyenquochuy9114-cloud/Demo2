from flask import Flask, render_template, request
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

app = Flask(__name__)

# Lấy danh sách top 300 coin theo vốn hoá từ CoinGecko
def get_top_coins(limit=300):
    url = f"https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": limit, "page": 1}
    response = requests.get(url)
    return response.json()

# Phân tích chi tiết coin
def analyze_coin(coin_id, days=30):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days}
    response = requests.get(url).json()

    if "prices" not in response:
        return None, None

    df = pd.DataFrame(response["prices"], columns=["time", "price"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df = df.merge(pd.DataFrame(response["total_volumes"], columns=["time", "volume"]), on="time")
    df = df.merge(pd.DataFrame(response["market_caps"], columns=["time", "market_cap"]), on="time")

    # RSI
    delta = df["price"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    exp1 = df["price"].ewm(span=12).mean()
    exp2 = df["price"].ewm(span=26).mean()
    df["MACD"] = exp1 - exp2
    df["MACD_signal"] = df["MACD"].ewm(span=9).mean()

    # Tín hiệu
    df["signal"] = np.where(
        (df["RSI"] < 30) & (df["MACD"] > df["MACD_signal"]), "Buy",
        np.where((df["RSI"] > 70) & (df["MACD"] < df["MACD_signal"]), "Sell", "Hold")
    )

    # Volume ratio
    vol_7d = df["volume"].tail(7).mean()
    vol_30d = df["volume"].mean()
    vol_ratio = vol_7d / vol_30d if vol_30d else 0

    # Vẽ chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["time"], y=df["price"], name="Price"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["RSI"], name="RSI"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["MACD"], name="MACD"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["MACD_signal"], name="MACD Signal"))
    fig.update_layout(title=f"{coin_id.upper()} Analysis", template="plotly_dark")
    chart_html = fig.to_html(full_html=False)

    latest = df.iloc[-1]
    return {
        "price": f"${latest['price']:,.2f}",
        "market_cap": f"${latest['market_cap']:,.0f}",
        "volume_percent": f"{(latest['volume']/latest['market_cap']*100):.2f}%",
        "vol_ratio": f"{vol_ratio:.2f}",
        "signal": latest["signal"],
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }, chart_html


@app.route("/", methods=["GET", "POST"])
def index():
    coins = get_top_coins(300)
    selected = request.form.get("coin", "bitcoin")
    data, chart = analyze_coin(selected)

    if not data:
        return "Error loading data"

    return render_template("index.html", coins=coins, selected=selected, data=data, chart=chart)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
