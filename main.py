import asyncio
import os

import uvicorn


def main() -> None:
    target = os.getenv('RUN_TARGET', 'api').strip().lower()
    if target == 'api':
        uvicorn.run('backend:app', host='0.0.0.0', port=int(os.getenv('PORT', '3000')))
        return
    if target == 'bot':
        from bot import main as bot_main

        asyncio.run(bot_main())
        return
    raise RuntimeError("RUN_TARGET must be either 'api' or 'bot'")


if __name__ == '__main__':
    main()
