from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    # Optional Fulfil API checks
    fulfil_tenant: str = os.getenv("FULFIL_TENANT", "")  # e.g. "acme" from https://acme.fulfil.io
    fulfil_api_key: str = os.getenv("FULFIL_API_KEY", "")

    # Semantic search config
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # Scoring weights (tune anytime)
    weight_error: float = 5.0
    weight_warning: float = 2.0
    weight_suggestion: float = 0.5

settings = Settings()
