from flask import Flask

app=Flask(__name__)

@app.route("/")
def home():
 return "welcome to home page"

@app.route("/payment")
def payment():
 return "payment done"


if __name__=="__main__":
 app.run(host="0.0.0.0",port=5000)