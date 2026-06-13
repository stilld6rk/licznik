"""
Główna aplikacja bota z rankingami
Uruchomienie na Railway
"""

import logging
import asyncio
from bot import run_bot
from database import init_db
from scraper import run_scraper
from calculator import build_ranking_content

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Punkt wejścia"""
    logger.info("=" * 50)
    logger.info("🚀 Uruchamiam bota rankingów gildii")
    logger.info("=" * 50)
    
    try:
        # Inicjalizuj bazę
        logger.info("📦 Inicjalizuję bazę danych...")
        init_db()
        
        # Pierwsza synchronizacja (poza asyncio, więc sync jest OK)
        logger.info("🔄 Pierwsza synchronizacja danych...")
        run_scraper()
        
        # Uruchom bota
        logger.info("🤖 Uruchamiam Discord bota...")
        run_bot()
        
    except Exception as e:
        logger.error(f"❌ Krytyczny błąd: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
