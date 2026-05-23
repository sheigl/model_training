# logger.py
import logging
from rich.console import Console
from rich.logging import RichHandler
echo = print
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(console=console),
        logging.FileHandler("/home/sheigl/.log/generate_synthetic_data.log")
    ]
)

logger = logging.getLogger("mtg")

def print(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    echo(msg)
    #logger.info(msg)