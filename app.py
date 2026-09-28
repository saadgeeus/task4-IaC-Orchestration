from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello Saad Khan!, welcome to DevOps Flask Mini App)'

@app.route('/health')
def health():
    return 'Server is up and running'
