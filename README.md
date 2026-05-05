TEST
---

````markdown id="readme_short"
# ⛑️ Casque Sécurité IoT (MQTT + Python)

Projet de simulation d’un casque intelligent utilisant :
- MQTT (Mosquitto)
- Python (paho-mqtt)
- Dashboard temps réel (Dash)

---

# ⚙️ Installation

## Installer les dépendances
```bash
pip install paho-mqtt dash plotly
````

## Installer Mosquitto

[https://mosquitto.org/download/](https://mosquitto.org/download/)

---

# 🚀 Lancement du projet

## 1. Lancer le broker MQTT

```bash
mosquitto -v
```

ou :

```bash
.\mosquitto.exe -v
```

---

## 2. Lancer le dashboard

```bash
python dashboard_casque.py
```

Ouvrir :
[http://localhost:8050](http://localhost:8050)

---

## 3. Lancer le simulateur

```bash
python simulateur.py
```

---

# 📡 Topics MQTT

* casque/data → données capteurs
* casque/alert → alertes
* casque/cmd → commandes

---

# ⚠️ Problème courant

Si erreur de connexion MQTT :
👉 utiliser `localhost` au lieu de `test.mosquitto.org`

---

# 🧠 Fonctionnalités

* Surveillance santé (HR, SpO2)
* Détection gaz (CO, MQ2, MQ135)
* Détection chute
* Alertes temps réel
* Dashboard web

---

# 🚀 Auteur

Projet IoT — MQTT + Python

```
Dis-moi 👍
```
