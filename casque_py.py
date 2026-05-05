"""
╔══════════════════════════════════════════════════════╗
║   DASHBOARD CASQUE SÉCURITÉ — Python + Dash + MQTT  ║
║   ESP32 → MQTT Broker → Dashboard Python             ║
╚══════════════════════════════════════════════════════╝

Installation:
    pip install dash plotly paho-mqtt

Lancement:
    python dashboard_casque.py
    → Ouvre http://localhost:8050
"""

import json
import threading
import time
from collections import deque
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
import paho.mqtt.client as mqtt

# ─────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────
MQTT_BROKER = "127.0.0.1"      # ← IP de ton PC / Raspberry Pi
MQTT_PORT    = 1883
TOPIC_DATA   = "casque/data"    # ESP32 publie ici
TOPIC_ALERT  = "casque/alert"   # Alertes critiques
TOPIC_CMD    = "casque/cmd"     # Dashboard envoie commandes ici

MAX_HISTORY  = 60               # Nombre de points dans les graphiques

# ─────────────────────────────────────────
#  STOCKAGE DES DONNÉES EN MÉMOIRE
# ─────────────────────────────────────────
class CasqueData:
    def __init__(self):
        self.lock = threading.Lock()

        # Dernières valeurs reçues
        self.current = {
            "id":          "---",
            "temp":        0.0,
            "humid":       0.0,
            "pressure":    0.0,
            "altitude":    0.0,
            "co_ppm":      0.0,
            "mq2":         0,
            "mq135":       0,
            "heart_rate":  0,
            "spo2":        0,
            "fall":        False,
            "sos":         False,
            "alert_level": 0,
            "last_update": "---",
        }

        # Historique pour graphiques (deque = file circulaire)
        self.history = {
            "time":        deque(maxlen=MAX_HISTORY),
            "co_ppm":      deque(maxlen=MAX_HISTORY),
            "temp":        deque(maxlen=MAX_HISTORY),
            "heart_rate":  deque(maxlen=MAX_HISTORY),
            "spo2":        deque(maxlen=MAX_HISTORY),
            "mq2":         deque(maxlen=MAX_HISTORY),
        }

        # Journal des alertes
        self.alerts_log = deque(maxlen=20)

        # Statut connexion MQTT
        self.mqtt_connected = False

    def update(self, payload: dict):
        with self.lock:
            self.current.update(payload)
            self.current["last_update"] = datetime.now().strftime("%H:%M:%S")
            now = datetime.now().strftime("%H:%M:%S")
            self.history["time"].append(now)
            self.history["co_ppm"].append(payload.get("co_ppm", 0))
            self.history["temp"].append(payload.get("temp", 0))
            self.history["heart_rate"].append(payload.get("heart_rate", 0))
            self.history["spo2"].append(payload.get("spo2", 0))
            self.history["mq2"].append(payload.get("mq2", 0))

    def add_alert(self, msg: str, level: str):
        with self.lock:
            self.alerts_log.appendleft({
                "time":  datetime.now().strftime("%H:%M:%S"),
                "msg":   msg,
                "level": level,
            })

    def get_current(self):
        with self.lock:
            return dict(self.current)

    def get_history(self):
        with self.lock:
            return {k: list(v) for k, v in self.history.items()}

    def get_alerts(self):
        with self.lock:
            return list(self.alerts_log)

# ─────────────────────────────────────────
#  CLIENT MQTT (tourne dans un thread séparé)
# ─────────────────────────────────────────
casque = CasqueData()
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connecté au broker {MQTT_BROKER}:{MQTT_PORT}")
        casque.mqtt_connected = True
        client.subscribe(TOPIC_DATA)
        client.subscribe(TOPIC_ALERT)
        casque.add_alert("Connexion MQTT établie", "ok")
    else:
        codes = {1:"Mauvais protocole", 2:"ID refusé", 3:"Broker indisponible",
                 4:"Identifiants incorrects", 5:"Non autorisé"}
        print(f"[MQTT] Erreur connexion: {codes.get(rc, f'Code {rc}')}")
        casque.mqtt_connected = False

def on_disconnect(client, userdata, rc):
    casque.mqtt_connected = False
    casque.add_alert("MQTT déconnecté — tentative reconnexion...", "warn")
    print("[MQTT] Déconnecté, reconnexion...")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))

        if msg.topic == TOPIC_DATA:
            casque.update(payload)
            lvl = payload.get("alert_level", 0)
            if lvl == 2:
                casque.add_alert(
                    f"DANGER — CO: {payload.get('co_ppm',0):.1f}ppm | "
                    f"Temp: {payload.get('temp',0):.1f}°C | "
                    f"SpO2: {payload.get('spo2',0)}%", "danger")
            elif lvl == 3:
                casque.add_alert(
                    f"SOS — Chute détectée! ID: {payload.get('id','?')}", "sos")
            elif lvl == 1:
                casque.add_alert(
                    f"Attention — CO: {payload.get('co_ppm',0):.1f}ppm", "warn")

        elif msg.topic == TOPIC_ALERT:
            casque.add_alert(
                f"ALERTE [{payload.get('level','?')}] — {msg.payload.decode()[:80]}", "danger")

    except json.JSONDecodeError as e:
        print(f"[MQTT] JSON invalide: {e}")
    except Exception as e:
        print(f"[MQTT] Erreur message: {e}")

def mqtt_thread():
    mqtt_client.on_connect    = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message    = on_message
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            mqtt_client.loop_forever()
        except Exception as e:
            print(f"[MQTT] Impossible de se connecter: {e}")
            casque.mqtt_connected = False
            time.sleep(5)  # Réessayer dans 5 secondes

threading.Thread(target=mqtt_thread, daemon=True).start()

# ─────────────────────────────────────────
#  COULEURS
# ─────────────────────────────────────────
COLORS = {
    "bg":      "#0d1117",
    "card":    "#161b22",
    "border":  "#30363d",
    "text":    "#e6edf3",
    "muted":   "#8b949e",
    "green":   "#39d353",
    "yellow":  "#e3b341",
    "red":     "#f85149",
    "blue":    "#58a6ff",
    "teal":    "#39c5bb",
}

def card_style(extra=None):
    s = {
        "backgroundColor": COLORS["card"],
        "border":          f"1px solid {COLORS['border']}",
        "borderRadius":    "8px",
        "padding":         "16px",
    }
    if extra:
        s.update(extra)
    return s

def title_style():
    return {
        "fontSize":     "10px",
        "fontWeight":   "600",
        "letterSpacing":"1.5px",
        "textTransform":"uppercase",
        "color":        COLORS["muted"],
        "marginBottom": "12px",
    }

def big_val(val, unit="", color=None):
    return html.Div([
        html.Span(str(val), style={
            "fontSize":   "32px",
            "fontWeight": "700",
            "fontFamily": "monospace",
            "color":      color or COLORS["text"],
        }),
        html.Span(f" {unit}", style={
            "fontSize": "14px",
            "color":    COLORS["muted"],
        }),
    ])

# ─────────────────────────────────────────
#  LAYOUT DASH
# ─────────────────────────────────────────
app = dash.Dash(
    __name__,
    title="Casque Sécurité — Dashboard",
    update_title=None,
)

app.layout = html.Div([

    # ── Interval pour auto-refresh ──────────────────
    dcc.Interval(id="interval", interval=1000, n_intervals=0),  # 1 sec

    # ── Header ──────────────────────────────────────
    html.Div([
        html.Div([
            html.Span("⬛ CASQUE SÉCURITÉ — SUPERVISION", style={
                "fontSize": "14px", "fontWeight": "700",
                "letterSpacing": "1px", "color": COLORS["blue"],
            }),
        ]),
        html.Div([
            html.Span(id="mqtt-status", style={"fontSize": "12px", "color": COLORS["muted"]}),
            html.Span(id="clock",       style={"fontSize": "12px", "color": COLORS["muted"], "marginLeft": "20px", "fontFamily": "monospace"}),
        ]),
    ], style={
        "display":         "flex",
        "justifyContent":  "space-between",
        "alignItems":      "center",
        "padding":         "10px 16px",
        "backgroundColor": COLORS["card"],
        "border":          f"1px solid {COLORS['border']}",
        "borderRadius":    "8px",
        "marginBottom":    "12px",
    }),

    # ── Niveau d'alerte ─────────────────────────────
    html.Div(id="alert-banner", style={"marginBottom": "12px"}),

    # ── Ligne 1 : CO | Température | Gaz ───────────
    html.Div([

        # CO
        html.Div([
            html.Div("CO — Monoxyde de carbone", style=title_style()),
            html.Div(id="val-co"),
            html.Div(style={
                "height": "6px", "borderRadius": "3px",
                "backgroundColor": COLORS["border"],
                "marginTop": "10px", "overflow": "hidden",
            }, children=[
                html.Div(id="bar-co", style={"height": "100%", "borderRadius": "3px", "transition": "width .5s"}),
            ]),
            html.Div("Danger: > 50 ppm", style={"fontSize": "11px", "color": COLORS["muted"], "marginTop": "6px"}),
        ], style=card_style({"flex": "1"})),

        # Température
        html.Div([
            html.Div("Température & Humidité", style=title_style()),
            html.Div(id="val-temp"),
            html.Div(id="val-hum", style={"marginTop": "4px", "fontSize": "14px", "color": COLORS["muted"]}),
            html.Div("Danger: > 42°C", style={"fontSize": "11px", "color": COLORS["muted"], "marginTop": "6px"}),
        ], style=card_style({"flex": "1"})),

        # Gaz MQ2 + MQ135
        html.Div([
            html.Div("Gaz & Qualité de l'air", style=title_style()),
            html.Div([
                html.Div([
                    html.Span("MQ-2  (CH4)", style={"fontSize": "11px", "color": COLORS["muted"], "minWidth": "80px", "display": "inline-block"}),
                    html.Div(style={"display": "inline-block", "width": "100px", "height": "5px",
                                    "backgroundColor": COLORS["border"], "borderRadius": "3px",
                                    "verticalAlign": "middle", "overflow": "hidden"}, children=[
                        html.Div(id="bar-mq2", style={"height": "100%", "borderRadius": "3px",
                                                      "backgroundColor": "#fb8f44", "transition": "width .5s"}),
                    ]),
                    html.Span(id="txt-mq2", style={"fontSize": "11px", "fontFamily": "monospace", "marginLeft": "6px", "color": COLORS["text"]}),
                ], style={"marginBottom": "8px"}),
                html.Div([
                    html.Span("MQ-135 (Air)", style={"fontSize": "11px", "color": COLORS["muted"], "minWidth": "80px", "display": "inline-block"}),
                    html.Div(style={"display": "inline-block", "width": "100px", "height": "5px",
                                    "backgroundColor": COLORS["border"], "borderRadius": "3px",
                                    "verticalAlign": "middle", "overflow": "hidden"}, children=[
                        html.Div(id="bar-mq135", style={"height": "100%", "borderRadius": "3px",
                                                        "backgroundColor": COLORS["teal"], "transition": "width .5s"}),
                    ]),
                    html.Span(id="txt-mq135", style={"fontSize": "11px", "fontFamily": "monospace", "marginLeft": "6px", "color": COLORS["text"]}),
                ]),
            ]),
            html.Div(id="txt-pressure", style={"fontSize": "11px", "color": COLORS["muted"], "marginTop": "8px"}),
        ], style=card_style({"flex": "1"})),

    ], style={"display": "flex", "gap": "10px", "marginBottom": "10px"}),

    # ── Ligne 2 : Signes vitaux | Graphiques ───────
    html.Div([

        # Signes vitaux
        html.Div([
            html.Div("Signes vitaux — Porteur", style=title_style()),
            html.Div([
                html.Div([
                    html.Div("♥", style={"fontSize": "20px", "color": COLORS["red"], "textAlign": "center"}),
                    html.Div(id="val-hr"),
                    html.Div("bpm", style={"fontSize": "11px", "color": COLORS["muted"], "textAlign": "center"}),
                    html.Div("50–130 normal", style={"fontSize": "9px", "color": COLORS["muted"], "textAlign": "center"}),
                ], style={"flex": "1"}),
                html.Div(style={"width": "1px", "backgroundColor": COLORS["border"]}),
                html.Div([
                    html.Div("○", style={"fontSize": "20px", "color": COLORS["blue"], "textAlign": "center"}),
                    html.Div(id="val-spo2"),
                    html.Div("% SpO2", style={"fontSize": "11px", "color": COLORS["muted"], "textAlign": "center"}),
                    html.Div("> 92% normal", style={"fontSize": "9px", "color": COLORS["muted"], "textAlign": "center"}),
                ], style={"flex": "1"}),
                html.Div(style={"width": "1px", "backgroundColor": COLORS["border"]}),
                html.Div([
                    html.Div("↓", style={"fontSize": "20px", "color": COLORS["teal"], "textAlign": "center"}),
                    html.Div(id="val-alt"),
                    html.Div("m altitude", style={"fontSize": "11px", "color": COLORS["muted"], "textAlign": "center"}),
                ], style={"flex": "1"}),
            ], style={"display": "flex", "gap": "12px", "marginBottom": "12px"}),

            # Indicateur chute
            html.Div(id="fall-indicator", style={"padding": "8px", "borderRadius": "6px"}),

            # Boutons commandes
            html.Div("Commandes →  ", style={"fontSize": "11px", "color": COLORS["muted"], "marginTop": "12px", "marginBottom": "6px"}),
            html.Div([
                html.Button("↺ Reset alarme",  id="btn-reset",  n_clicks=0,
                            style={"backgroundColor": COLORS["card"], "color": COLORS["text"],
                                   "border": f"1px solid {COLORS['border']}",
                                   "borderRadius": "5px", "padding": "6px 12px",
                                   "cursor": "pointer", "fontSize": "11px", "marginRight": "6px"}),
                html.Button("▶ Test buzzer",   id="btn-test",   n_clicks=0,
                            style={"backgroundColor": COLORS["card"], "color": COLORS["text"],
                                   "border": f"1px solid {COLORS['border']}",
                                   "borderRadius": "5px", "padding": "6px 12px",
                                   "cursor": "pointer", "fontSize": "11px"}),
            ]),
            html.Div(id="cmd-feedback", style={"fontSize": "11px", "color": COLORS["teal"], "marginTop": "6px"}),

        ], style=card_style({"flex": "1"})),

        # Graphiques temps réel
        html.Div([
            html.Div("Graphiques temps réel", style=title_style()),
            dcc.Graph(id="graph-hr-spo2",  config={"displayModeBar": False}, style={"height": "130px"}),
            dcc.Graph(id="graph-co-temp",  config={"displayModeBar": False}, style={"height": "130px"}),
        ], style=card_style({"flex": "2"})),

    ], style={"display": "flex", "gap": "10px", "marginBottom": "10px"}),

    # ── Journal des alertes ─────────────────────────
    html.Div([
        html.Div("Journal des alertes", style=title_style()),
        html.Div(id="alerts-log"),
    ], style=card_style()),

], style={
    "backgroundColor": COLORS["bg"],
    "minHeight":       "100vh",
    "padding":         "12px",
    "fontFamily":      "Arial, sans-serif",
    "color":           COLORS["text"],
})

# ─────────────────────────────────────────
#  CALLBACKS — Mise à jour interface
# ─────────────────────────────────────────
@app.callback(
    Output("clock",          "children"),
    Output("mqtt-status",    "children"),
    Output("alert-banner",   "children"),
    Output("val-co",         "children"),
    Output("bar-co",         "style"),
    Output("val-temp",       "children"),
    Output("val-hum",        "children"),
    Output("bar-mq2",        "style"),
    Output("txt-mq2",        "children"),
    Output("bar-mq135",      "style"),
    Output("txt-mq135",      "children"),
    Output("txt-pressure",   "children"),
    Output("val-hr",         "children"),
    Output("val-spo2",       "children"),
    Output("val-alt",        "children"),
    Output("fall-indicator", "children"),
    Output("fall-indicator", "style"),
    Output("graph-hr-spo2",  "figure"),
    Output("graph-co-temp",  "figure"),
    Output("alerts-log",     "children"),
    Input("interval",        "n_intervals"),
)
def update_dashboard(n):
    d  = casque.get_current()
    h  = casque.get_history()
    al = casque.get_alerts()

    # ── Horloge ──────────────────────────────────
    clock_str = datetime.now().strftime("%H:%M:%S")

    # ── Statut MQTT ───────────────────────────────
    if casque.mqtt_connected:
        mqtt_str = "● MQTT connecté — " + d["id"]
        mqtt_color = COLORS["green"]
    else:
        mqtt_str = "● MQTT déconnecté..."
        mqtt_color = COLORS["red"]
    mqtt_el = html.Span(mqtt_str, style={"color": mqtt_color})

    # ── Banner d'alerte ───────────────────────────
    lvl = d["alert_level"]
    banner_configs = {
        0: ("OK — Tout dans les limites normales",              COLORS["green"],  "#0d2217", "#39d35333"),
        1: ("⚠ ATTENTION — Seuil d'alerte approché",           COLORS["yellow"], "#221a08", "#e3b34133"),
        2: ("⬛ DANGER — Paramètre hors limites critiques!",   COLORS["red"],    "#220d0d", "#f8514933"),
        3: ("🆘 SOS — CHUTE + IMMOBILITÉ DÉTECTÉE!",           COLORS["red"],    "#220d0d", "#f8514966"),
    }
    msg, col, bg, border_col = banner_configs.get(lvl, banner_configs[0])
    banner = html.Div(msg, style={
        "padding":         "12px 16px",
        "borderRadius":    "8px",
        "backgroundColor": bg,
        "border":          f"1px solid {border_col}",
        "fontWeight":      "700",
        "letterSpacing":   "1px",
        "color":           col,
        "fontSize":        "14px",
    })

    # ── CO ────────────────────────────────────────
    co = d["co_ppm"]
    co_color = COLORS["green"] if co < 30 else (COLORS["yellow"] if co < 50 else COLORS["red"])
    co_el = big_val(f"{co:.1f}", "ppm", co_color)
    co_bar = {"height": "100%", "borderRadius": "3px",
              "width":  f"{min(co/80*100, 100):.0f}%",
              "backgroundColor": co_color, "transition": "width .5s"}

    # ── Température ───────────────────────────────
    temp = d["temp"]
    t_color = COLORS["blue"] if temp < 38 else (COLORS["yellow"] if temp < 42 else COLORS["red"])
    temp_el = big_val(f"{temp:.1f}", "°C", t_color)
    hum_el  = html.Span(f"Humidité: {d['humid']:.0f}%")

    # ── MQ2 ───────────────────────────────────────
    mq2_pct = min(d["mq2"] / 800 * 100, 100)
    mq2_bar = {"height": "100%", "borderRadius": "3px", "backgroundColor": "#fb8f44",
               "width": f"{mq2_pct:.0f}%", "transition": "width .5s"}

    # ── MQ135 ─────────────────────────────────────
    mq135_pct = min(d["mq135"] / 600 * 100, 100)
    mq135_bar = {"height": "100%", "borderRadius": "3px", "backgroundColor": COLORS["teal"],
                 "width": f"{mq135_pct:.0f}%", "transition": "width .5s"}

    pressure_el = f"Pression: {d['pressure']:.1f} hPa  |  Altitude: {d['altitude']:.0f} m"

    # ── Signes vitaux ─────────────────────────────
    hr    = d["heart_rate"]
    spo2  = d["spo2"]
    hr_color   = COLORS["red"]  if (hr < 50 or hr > 130) else COLORS["text"]
    spo2_color = COLORS["red"]  if spo2 < 92 else COLORS["blue"]
    hr_el   = big_val(hr,   "", hr_color)
    spo2_el = big_val(spo2, "", spo2_color)
    alt_el  = big_val(f"{d['altitude']:.0f}", "", COLORS["teal"])

    # ── Chute ─────────────────────────────────────
    if d["fall"] or d["sos"]:
        fall_children = "⚠ CHUTE DÉTECTÉE — vérification état porteur..."
        fall_style = {"padding": "8px", "borderRadius": "6px",
                      "backgroundColor": "#220d0d", "border": f"1px solid {COLORS['red']}",
                      "color": COLORS["red"], "fontSize": "12px"}
    else:
        fall_children = "✓ Aucune chute — porteur stable"
        fall_style = {"padding": "8px", "borderRadius": "6px",
                      "backgroundColor": "#0d221a", "color": COLORS["green"], "fontSize": "12px"}

    # ── Graphique HR + SpO2 ───────────────────────
    times = h["time"]
    fig_hr = go.Figure()
    fig_hr.add_trace(go.Scatter(
        x=list(times), y=list(h["heart_rate"]),
        name="HR (bpm)", line=dict(color=COLORS["red"], width=1.5),
        fill="tozeroy", fillcolor="rgba(248,81,73,0.1)"
    ))
    fig_hr.add_trace(go.Scatter(
        x=list(times), y=list(h["spo2"]),
        name="SpO2 (%)", line=dict(color=COLORS["blue"], width=1.5),
        yaxis="y2"
    ))
    fig_hr.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["muted"], size=9),
        margin=dict(l=30, r=30, t=10, b=20),
        legend=dict(x=0, y=1, font=dict(size=9)),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=True, gridcolor=COLORS["border"], title="bpm"),
        yaxis2=dict(overlaying="y", side="right", title="%", range=[80, 105]),
    )

    # ── Graphique CO + Temp ───────────────────────
    fig_co = go.Figure()
    fig_co.add_trace(go.Scatter(
        x=list(times), y=list(h["co_ppm"]),
        name="CO (ppm)", line=dict(color=COLORS["yellow"], width=1.5),
        fill="tozeroy", fillcolor="rgba(227,179,65,0.1)"
    ))
    fig_co.add_trace(go.Scatter(
        x=list(times), y=list(h["temp"]),
        name="Temp (°C)", line=dict(color=COLORS["teal"], width=1.5),
        yaxis="y2"
    ))
    fig_co.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["muted"], size=9),
        margin=dict(l=30, r=30, t=10, b=20),
        legend=dict(x=0, y=1, font=dict(size=9)),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=True, gridcolor=COLORS["border"], title="ppm"),
        yaxis2=dict(overlaying="y", side="right", title="°C"),
    )

    # ── Journal alertes ───────────────────────────
    level_colors = {
        "ok":     COLORS["green"],
        "warn":   COLORS["yellow"],
        "danger": COLORS["red"],
        "sos":    COLORS["red"],
    }
    alerts_el = html.Div([
        html.Div([
            html.Span(f"[{a['time']}]", style={
                "fontFamily": "monospace", "fontSize": "11px",
                "color": COLORS["muted"], "marginRight": "8px"
            }),
            html.Span(
                a["level"].upper(),
                style={
                    "fontSize":        "9px",
                    "fontWeight":      "600",
                    "padding":         "1px 5px",
                    "borderRadius":    "3px",
                    "backgroundColor": level_colors.get(a["level"], COLORS["muted"]) + "22",
                    "color":           level_colors.get(a["level"], COLORS["muted"]),
                    "marginRight":     "6px",
                }
            ),
            html.Span(a["msg"], style={"fontSize": "12px"}),
        ], style={
            "padding":       "5px 0",
            "borderBottom":  f"1px solid {COLORS['border']}",
        })
        for a in al[:8]
    ]) if al else html.Div("Aucune alerte", style={"fontSize": "12px", "color": COLORS["muted"]})

    return (
        clock_str, mqtt_el, banner,
        co_el, co_bar,
        temp_el, hum_el,
        mq2_bar, str(d["mq2"]),
        mq135_bar, str(d["mq135"]),
        pressure_el,
        hr_el, spo2_el, alt_el,
        fall_children, fall_style,
        fig_hr, fig_co,
        alerts_el,
    )

# ─────────────────────────────────────────
#  CALLBACK — Boutons commandes
# ─────────────────────────────────────────
@app.callback(
    Output("cmd-feedback", "children"),
    Input("btn-reset", "n_clicks"),
    Input("btn-test",  "n_clicks"),
    prevent_initial_call=True,
)
def send_command(reset_clicks, test_clicks):
    ctx = callback_context
    if not ctx.triggered:
        return ""
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if btn_id == "btn-reset":
        mqtt_client.publish(TOPIC_CMD, "RESET_ALARM")
        casque.add_alert("Commande envoyée: RESET_ALARM", "ok")
        return "✓ Commande RESET envoyée au casque"
    elif btn_id == "btn-test":
        mqtt_client.publish(TOPIC_CMD, "TEST_ALARM")
        casque.add_alert("Commande envoyée: TEST_ALARM", "ok")
        return "✓ Commande TEST envoyée au casque"
    return ""

# ─────────────────────────────────────────
#  LANCEMENT
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║  Dashboard Casque Sécurité — Python  ║")
    print("╠══════════════════════════════════════╣")
    print(f"║  Broker MQTT : {MQTT_BROKER}:{MQTT_PORT}          ║")
    print("║  Dashboard   : http://localhost:8050 ║")
    print("╚══════════════════════════════════════╝")
    app.run(debug=False, host="0.0.0.0", port=8050)
