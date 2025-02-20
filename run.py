import os
from app import create_app

app = create_app()

@app.route('/')
def healthcheck():
    return 'OK', 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv('PORT', 8080)))