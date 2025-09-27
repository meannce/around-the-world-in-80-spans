# app.py
from flask import Flask
import logging
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

counter = 0

@app.route("/")
def home():
    return """
    <html>
      <head><title>Button</title></head>
      <body bgcolor="black" text="lime" align="center">
        <h1 style="font-family: monospace;">PRESS THE BUTTON</h1>
        <form action="/press" method="post">
          <input type="submit" value="CLICK HERE" style="font-size:40px; background:lime; color:black; border:3px solid white; padding:20px;" />
        </form>
      </body>
    </html>
    """

@app.route("/press", methods=["POST"])
def press():
    global counter
    counter += 1
    timestamp = time.time()
    logging.info(f"Button pressed! Count={counter}, timestamp={timestamp}")
    return f"<h1 style='font-family: monospace;'>Pressed {counter} times!</h1>"

@app.route("/metrics")
def metrics():
    return f"button_presses_total {counter}\n"
