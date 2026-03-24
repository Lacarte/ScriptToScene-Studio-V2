from pathlib import Path

# Load .env from project root before anything else
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.is_file():
    from dotenv import load_dotenv
    load_dotenv(env_path)

from .loop import main

main()
