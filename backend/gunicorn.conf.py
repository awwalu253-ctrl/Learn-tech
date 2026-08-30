# gunicorn.conf.py
import os

# Bind to the port Render provides
port = os.environ.get('PORT', 10000)
bind = f"0.0.0.0:{port}"

# Worker settings
workers = 1
worker_class = 'gthread'
threads = 4
worker_connections = 1000

# Timeout settings
timeout = 120
keepalive = 2

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Preload app for better performance
preload_app = True

# Graceful timeout
graceful_timeout = 30