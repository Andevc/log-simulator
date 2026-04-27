pip uninstall cassandra-driver -y
pip install "cassandra-driver==3.30.0" --no-cache-dir --only-binary :all:


pip install gevent

from gevent import monkey
monkey.patch_all()


