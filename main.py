import logging
import msgpack_numpy as m

from resources.client import client_main

if __name__ == '__main__':
    m.patch()
    logging.basicConfig(level=logging.DEBUG)
    client = client_main.Client()
    logging.info("Client started")
    client.start()