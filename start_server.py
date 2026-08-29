import argparse
import logging
import os
import sys
import sysconfig

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

try:
    import colorlog

    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False

from src.server.server_main import Server

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyCraft2D Server")
    parser.add_argument(
        "--integrated",
        action="store_true",
        help="Run as integrated server (disable stdin input)",
    )
    parser.add_argument(
        "--save-id",
        default=None,
        help="Save id to load from data/saves",
    )
    args = parser.parse_args()

    # 配置日志：子进程模式下 colorlog 可能未安装，降级为标准 logging
    if HAS_COLORLOG:
        handler = colorlog.StreamHandler()
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s[%(asctime)s %(levelname)s] - %(message)s",
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
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s %(levelname)s] - %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)

    if args.integrated:
        logging.info("Starting integrated server (subprocess mode)...")

    free_threaded_build = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
    gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
    if free_threaded_build and not gil_enabled:
        logging.warning("********")
        logging.warning("Server is running with the GIL disabled (experimental)")
        logging.warning("Parallel chunk generation may be faster")
        logging.warning("Single-threaded tick work may be slower")
        logging.warning("Some native dependencies do not declare free-thread safety")
        logging.warning("********")
    elif free_threaded_build:
        logging.warning(
            "Free-threaded Python detected, but the GIL is enabled by a native module"
        )

    # 子进程模式下传入 integrated=True（禁用 stdin 输入）和 client=None（无耦合对象）
    server = Server(integrated=args.integrated, save_id=args.save_id)
    server.init()
