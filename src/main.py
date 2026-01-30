"""
Entry point for CAU Notice Bot.
Checks university notices and sends them to Discord.
"""

import asyncio
import logging
import sys

from dotenv import load_dotenv

from src.bot_service import load_config, send_message_to_discord
from src.notice_check import check_notices


async def main() -> int:
    """Check notices and send to Discord.

    Returns:
        0 if successful, 1 if failed
    """
    load_dotenv()  # Load .env for local development (no-op in CI)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        config = load_config()
        cau_notices, library_notices = check_notices(config)
        all_notices = cau_notices + library_notices

        logging.info(f"Found {len(cau_notices)} CAU notices, {len(library_notices)} library notices")

        success = await send_message_to_discord(config, all_notices)
        return 0 if success else 1

    except KeyError as e:
        logging.error(f"Missing required environment variable: {e}")
        return 1
    except Exception as e:
        logging.error(f"Error during execution: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
