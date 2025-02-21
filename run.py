import os
from app import create_app

app = create_app()

# Add health check endpoint
@app.route('/')
def health_check():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)