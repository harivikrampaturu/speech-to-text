from gevent import monkey
monkey.patch_all()

from local_server import app, socketio

if __name__ == "__main__":
    socketio.run(app) 