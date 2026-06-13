import logging
from bot import run_bot
from database import init_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    logger.info("🚀 Uruchamiam bota rankingów gildii")
    init_db()
    run_bot()  # scraper i ranking uruchamiają się wewnątrz bota (auto_scrape task)


if __name__ == "__main__":
    main()
