import logging

from resources.client import client_main

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    client = client_main.Client()
    logging.info("Client started")
    client.start()