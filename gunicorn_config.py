bind = "0.0.0.0:10000"
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
workers = 1
loglevel = "debug"
keepalive = 65
timeout = 120 