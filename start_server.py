import logging
import colorlog

from resources.server.server_main import Server

if __name__ == "__main__":
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s[%(asctime)s %(levelname)s] - %(message)s',
        datefmt='%H:%M:%S',
        log_colors={
            'DEBUG': 'light_black',
            'INFO': 'white',
            'WARNING': 'yellow',
            'ERROR': 'light_red',
            'CRITICAL': 'red,bg_white',
        }
    ))

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)
    server = Server()
    server.init()