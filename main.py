import logging
import sys
import threading
import traceback

import colorlog
import os

os.environ["PYCRAFT_CLIENT"] = "1"

from src.client import client_main

def thread_excepthook(args):
    print(f"An runtime error occurred in {args.thread.name}.", file=sys.stderr)
    traceback.print_exception(
        args.exc_type,
        args.exc_value,
        args.exc_traceback
    )
    if client is not None:
        logging.info("Force shutdown client")
        client.shutdown()
    os._exit(1)

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

    threading.excepthook = thread_excepthook

    client = client_main.Client()
    logging.info("Client started")
    client.start()
