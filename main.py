import logging
import colorlog
import os

os.environ["PYCRAFT_CLIENT"] = "1"

from resources.client import client_main

if __name__ == "__main__":
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s] [%(threadName)s/%(levelname)s] - %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "light_black",
                "INFO": "white",
                "WARNING": "yellow",
                "ERROR": "light_red",
                "CRITICAL": "red,bg_white",
            },
        )
    )

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    client = client_main.Client()
    logging.info("Client started")
    client.start()
