"""
Entry point for CAU Notice Bot.
Checks university notices and sends them to Discord.
"""

import asyncio
import logging
import sys

from dotenv import load_dotenv

from src.config import load_config
from src.services import NoticeRunService


async def main() -> int:
    """Check notices and send to Discord.

    Returns:
        0 if successful, 1 if failed
    """
    load_dotenv()  # Load .env for local development (no-op in CI)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        config = load_config()
        result = await NoticeRunService(config).run()
        logging.info(f"Found {result.notices_sent} total notices")
        return 0 if result.success else 1

    except KeyError as e:
        logging.error(f"Missing required environment variable: {e}")
        return 1
    except Exception as e:
        logging.error(f"Error during execution: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
