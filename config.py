import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")

# Model Configuration
LLM_MODEL = "llama-3.3-70b-versatile"
EMBEDDING_MODEL = "NeuML/pubmedbert-base-embeddings"

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")
INDEX_DIR = os.path.join(BASE_DIR, "faiss_index")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# Create directories if they don't exist
for directory in [DATA_DIR, CONVERSATIONS_DIR, INDEX_DIR, UPLOAD_DIR]:
    os.makedirs(directory, exist_ok=True)

# Security & Upload Configuration
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

# Rate Limiting Configuration
RATE_LIMIT_QUERIES_PER_IP_HOUR = 60
RATE_LIMIT_UPLOADS_PER_IP_HOUR = 5

# Cache Config
CACHE_SIZE_LIMIT = 500  # max items in in-memory cache
CACHE_TTL_SECONDS = 3600  # 1 hour
