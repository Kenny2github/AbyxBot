import asyncio
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parent.parent)
from AbyxBot import done, run

async def main():
    try:
        await run()
    except KeyboardInterrupt:
        pass
    finally:
        await done()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
