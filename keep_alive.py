from flask import Flask
from threading import Thread
import os

app = Flask('')


# Endpoint główny
@app.route('/')
def home():
    return "I'm alive!"


# Funkcja uruchamiająca serwer w osobnym wątku
def run():
    app.run(host='0.0.0.0', port=5000)


def keep_alive():
    t = Thread(target=run)
    t.start()
