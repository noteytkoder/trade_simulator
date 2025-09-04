import os
import re
import io
import pandas as pd
import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.graph_objs as go

# === Настройки ===
DATA_DIR = "simulations"  # папка с CSV-файлами (поменяй на свою)
PORT = 8050

# === Вспомогательные функции ===
def load_csv_with_meta(filepath: str):
    """Считывает CSV вместе с мета-информацией из комментариев."""
    meta = {}
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                match = re.match(r"#\s*(.+?):\s*(.+)", line.strip())
                if match:
                    key, val = match.groups()
                    meta[key.strip()] = val.strip()
            else:
                rows.append(line)
    # Загружаем CSV через io.StringIO
    df = pd.read_csv(io.StringIO("".join(rows)))
    return df, meta

def list_csv_files():
    return [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]

# === Dash App ===
app = dash.Dash(__name__)
app.title = "Анализ симуляций"

app.layout = html.Div([
    html.H2("📊 Анализ симуляций трейдера"),

    html.Div([
        html.Label("Выбери CSV-файл:"),
        dcc.Dropdown(
            id="file-dropdown",
            options=[{"label": f, "value": f} for f in list_csv_files()],
            value=list_csv_files()[0] if list_csv_files() else None,
            style={"width": "60%"}
        ),
        html.Button("Обновить список", id="refresh-btn", n_clicks=0)
    ], style={"marginBottom": "20px"}),

    html.Div(id="meta-info", style={"marginBottom": "20px"}),

    dcc.Tabs([
        dcc.Tab(label="График цены и сделок", children=[
            dcc.Graph(id="price-chart")
        ]),
        dcc.Tab(label="График баланса", children=[
            dcc.Graph(id="balance-chart")
        ]),
        dcc.Tab(label="Таблица сделок", children=[
            dash_table.DataTable(
                id="trades-table",
                columns=[],
                data=[],
                page_size=15,
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "center"}
            )
        ])
    ])
])

# === Callbacks ===
@app.callback(
    Output("file-dropdown", "options"),
    Input("refresh-btn", "n_clicks")
)
def refresh_file_list(n):
    return [{"label": f, "value": f} for f in list_csv_files()]

@app.callback(
    [Output("meta-info", "children"),
     Output("trades-table", "columns"),
     Output("trades-table", "data"),
     Output("price-chart", "figure"),
     Output("balance-chart", "figure")],
    Input("file-dropdown", "value")
)
def update_dashboard(filename):
    if filename is None:
        return "Нет файла", [], [], go.Figure(), go.Figure()

    filepath = os.path.join(DATA_DIR, filename)
    df, meta = load_csv_with_meta(filepath)

    # --- Мета-инфо
    meta_block = html.Div([
        html.H4("📝 Параметры симуляции"),
        html.Ul([html.Li(f"{k}: {v}") for k, v in meta.items()])
    ])

    # --- Таблица
    columns = [{"name": c, "id": c} for c in df.columns]
    data = df.to_dict("records")

    # --- График цены
    fig_price = go.Figure()
    if "actual_price" in df.columns:
        fig_price.add_trace(go.Scatter(
            x=df["timestamp"], y=df["actual_price"],
            mode="lines", name="Actual Price"
        ))
    if "type" in df.columns:
        buys = df[df["type"] == "BUY"]
        sells = df[df["type"] == "SELL"]
        if not buys.empty:
            fig_price.add_trace(go.Scatter(
                x=buys["timestamp"], y=buys["price"],
                mode="markers", name="BUY",
                marker=dict(color="green", size=10, symbol="triangle-up")
            ))
        if not sells.empty:
            fig_price.add_trace(go.Scatter(
                x=sells["timestamp"], y=sells["price"],
                mode="markers", name="SELL",
                marker=dict(color="red", size=10, symbol="triangle-down")
            ))
    fig_price.update_layout(title="Цена и сделки", xaxis_title="Время", yaxis_title="Цена")

    # --- График баланса
    fig_balance = go.Figure()
    if "balance" in df.columns:
        fig_balance.add_trace(go.Scatter(
            x=df["timestamp"], y=df["balance"],
            mode="lines+markers", name="Balance"
        ))
        fig_balance.update_layout(title="Баланс", xaxis_title="Время", yaxis_title="Баланс")

    return meta_block, columns, data, fig_price, fig_balance

# === Запуск ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
