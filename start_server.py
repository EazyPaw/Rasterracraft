import logging
import msgpack_numpy as m

from resources.server.server_main import Server

if __name__ == "__main__":
    m.patch()
    logging.basicConfig(level=logging.DEBUG)
    server = Server()
    server.init()