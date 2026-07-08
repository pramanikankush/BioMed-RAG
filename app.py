import os
import json
import time
from uuid import uuid4
from contextlib import asynccontextmanager
from typing import Dict, Any, List

from fastapi import FastAPI, Request, Form, Response, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psutil

import config
from rag.engine import get_db, get_embeddings, get_llm, execute_rag_stream
from rag.document_processor import add_document_to_faiss, delete_document_from_faiss, get_document_statistics
from utils.cache import InMemoryCache
from utils.rate_limiter import SlidingWindowRateLimiter
from utils.logger import get_logger, request_id_var

# Initialize structured logger
logger = get_logger("app")

# Initialize utilities
response_cache = InMemoryCache(limit=config.CACHE_SIZE_LIMIT, ttl_seconds=config.CACHE_TTL_SECONDS)
query_rate_limiter = SlidingWindowRateLimiter(limit=config.RATE_LIMIT_QUERIES_PER_IP_HOUR)
upload_rate_limiter = SlidingWindowRateLimiter(limit=config.RATE_LIMIT_UPLOADS_PER_IP_HOUR)

# Context / Startup Lifecycle Manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup resources preloading (FAISS embeddings, Vector database, LLM client)
    """
    logger.info("Initializing medical RAG server assets...")
    try:
        # Preload embeddings and vector database
        get_embeddings()
        get_db()
        get_llm()
        logger.info("RAG components preloaded successfully.")
    except Exception as e:
        logger.error(f"Error preloading RAG assets during server startup: {str(e)}", exc_info=True)
    yield
    logger.info("Shutting down RAG server components...")

app = FastAPI(
    title="Medical RAG SaaS API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for Request ID injection and logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Set request ID context variable
    req_id = request.headers.get("X-Request-ID", str(uuid4()))
    request_id_var.set(req_id)
    
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    duration = time.time() - start_time
    try:
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time"] = f"{duration:.4f}s"
    except Exception:
        pass  # Some streaming responses have immutable headers
    
    extra = {
        "extra_fields": {
            "method": request.method,
            "url": str(request.url),
            "client_ip": request.client.host if request.client else "unknown",
            "status_code": response.status_code,
            "latency_seconds": round(duration, 4)
        }
    }
    logger.info(f"HTTP Request processed: {request.method} {request.url.path} -> {response.status_code}", extra=extra)
    return response

# Setup directories & mount static files (use absolute paths for Docker reliability)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")

# Rate limiting checking dependencies
def check_query_rate_limit(request: Request):
    ip = request.client.host if request.client else "127.0.0.1"
    if not query_rate_limiter.is_allowed(ip):
        logger.warning(f"Query rate limit exceeded for IP: {ip}")
        raise HTTPException(status_code=429, detail="Too many queries. Please wait an hour before checking again.")

def check_upload_rate_limit(request: Request):
    ip = request.client.host if request.client else "127.0.0.1"
    if not upload_rate_limiter.is_allowed(ip):
        logger.warning(f"Upload rate limit exceeded for IP: {ip}")
        raise HTTPException(status_code=429, detail="File upload rate limit reached. Limit is 5 uploads per hour.")

# Input Validation / Injection check helper
def sanitize_query(query: str) -> str:
    """
    Basic prompt injection check. Cleans the query string.
    """
    if not query:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")
    
    normalized = query.lower()
    injection_signatures = [
        "ignore previous instructions",
        "system override",
        "you are now a",
        "ignore the context",
        "bypass safeguards"
    ]
    for sig in injection_signatures:
        if sig in normalized:
            logger.warning(f"Potential injection signature blocked: '{sig}' in query.")
            raise HTTPException(status_code=400, detail="Input contains disallowed prompt instruction phrases.")
            
    return query

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Failed to render index.html: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Template render error: {str(e)}")

# Chat Session History management
class ChatSessionRename(BaseModel):
    name: str = Field(..., max_length=100)

@app.get("/chats")
async def list_chats() -> Dict[str, Dict[str, Any]]:
    """
    Returns all recent chat sessions loaded from disk
    """
    chats = {}
    if os.path.exists(config.CONVERSATIONS_DIR):
        for filename in os.listdir(config.CONVERSATIONS_DIR):
            if filename.endswith(".json"):
                chat_id = filename[:-5]
                filepath = os.path.join(config.CONVERSATIONS_DIR, filename)
                try:
                    with open(filepath, "r", encoding='utf-8') as f:
                        chats[chat_id] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading chat {chat_id}: {str(e)}")
    return chats

@app.put("/chats/{chat_id}")
async def rename_chat(chat_id: str, payload: ChatSessionRename):
    """
    Renames a chat session on disk
    """
    filepath = os.path.join(config.CONVERSATIONS_DIR, f"{chat_id}.json")
    if not os.path.exists(filepath):
        # Create it if it doesn't exist
        chat_data = {"name": payload.name, "messages": []}
    else:
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                chat_data = json.load(f)
            chat_data["name"] = payload.name
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read chat: {str(e)}")
            
    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save chat: {str(e)}")

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """
    Deletes a chat session file
    """
    filepath = os.path.join(config.CONVERSATIONS_DIR, f"{chat_id}.json")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return {"status": "deleted"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")
    raise HTTPException(status_code=404, detail="Chat session not found")

# Core streaming endpoint
@app.post("/get_response")
async def get_response(
    query: str = Form(...),
    chat_id: str = Form(...),
    use_web: bool = Form(False),
    dependencies = Depends(check_query_rate_limit)
):
    """
    Core RAG assistant stream. Evaluates the hybrid pipeline + web search.
    Streams result back using Server-Sent Events (SSE).
    """
    # 1. Input sanitization
    sanitized_query = sanitize_query(query)
    
    # 2. Check Cache
    cache_key = f"{chat_id}:{sanitized_query}:{use_web}"
    cached_response = response_cache.get(cache_key)
    if cached_response:
        logger.info("Serving query response from Cache.")
        
        async def cached_generator():
            # Send cached metadata first
            yield f"data: {json.dumps({'metadata': cached_response['metadata']})}\n\n"
            # Send cached response tokens
            for token in cached_response['tokens']:
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
            
        return StreamingResponse(cached_generator(), media_type="text/event-stream")

    # Load chat history from disk for session context
    chat_history = []
    filepath = os.path.join(config.CONVERSATIONS_DIR, f"{chat_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                chat_data = json.load(f)
                chat_history = chat_data.get("messages", [])
        except Exception as e:
            logger.error(f"Error loading conversation file for {chat_id}: {str(e)}")

    # 3. Expose execution stream & update cache dynamically
    async def event_generator():
        collected_tokens = []
        metadata = {}
        
        try:
            async for sse_item in execute_rag_stream(sanitized_query, chat_history, use_web):
                # We extract the content to cache
                if sse_item.startswith("data: "):
                    raw_data = sse_item[6:].strip()
                    if raw_data != "[DONE]" and raw_data:
                        parsed = json.loads(raw_data)
                        if "metadata" in parsed:
                            metadata = parsed["metadata"]
                        elif "token" in parsed:
                            collected_tokens.append(parsed["token"])
                yield sse_item
                
            # If successful, cache the complete output
            if collected_tokens:
                response_cache.set(cache_key, {
                    "metadata": metadata,
                    "tokens": collected_tokens
                })
                
                # Append assistant message to chat history on disk
                filepath = os.path.join(config.CONVERSATIONS_DIR, f"{chat_id}.json")
                chat_data = {"name": "New Chat", "messages": []}
                if os.path.exists(filepath):
                    try:
                        with open(filepath, "r", encoding='utf-8') as f:
                            chat_data = json.load(f)
                    except Exception:
                        pass
                
                # Add user message if not already present
                if not chat_data["messages"] or chat_data["messages"][-1]["role"] != "user":
                    chat_data["messages"].append({"role": "user", "content": query})
                    
                chat_data["messages"].append({
                    "role": "assistant",
                    "content": "".join(collected_tokens),
                    "metadata": metadata
                })
                
                with open(filepath, "w", encoding='utf-8') as f:
                    json.dump(chat_data, f, ensure_ascii=False, indent=2)
                    
        except Exception as e:
            logger.error(f"Error in RAG generation: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'error': f'Generation Error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Document Ingestion upload
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    dependencies = Depends(check_upload_rate_limit)
):
    """
    Uploads a PDF, DOCX, or TXT file, chunks it, and merges vectors into FAISS index.
    """
    filename = file.filename
    _, ext = os.path.splitext(filename.lower())
    
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: '{ext}'. Allowed: PDF, DOCX, TXT."
        )
        
    save_path = os.path.join(config.DATA_DIR, filename)
    
    # Save the file locally
    try:
        content = await file.read()
        if len(content) > config.MAX_CONTENT_LENGTH:
            raise HTTPException(status_code=400, detail="File size exceeds limit of 10MB.")
            
        with open(save_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving uploaded file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # Ingest document chunks into FAISS vector index
    try:
        db = get_db()
        chunks_added = add_document_to_faiss(db, save_path)
        # Clear cache since index has updated
        response_cache.clear()
        logger.info(f"Ingested {filename}: {chunks_added} chunks added to vector store.")
        return {"status": "success", "chunks": chunks_added, "filename": filename}
    except Exception as e:
        # Cleanup uploaded file if index update failed
        if os.path.exists(save_path):
            os.remove(save_path)
        logger.error(f"Error updating vector index for uploaded file {filename}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process and index document: {str(e)}")

# Get indexed documents list & stats
@app.get("/documents")
async def list_documents():
    """
    Returns list of indexed documents and overall diagnostics
    """
    try:
        db = get_db()
        stats = get_document_statistics(db)
        return stats
    except Exception as e:
        logger.error(f"Error fetching document statistics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve document statistics.")

# Delete indexed document
@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    """
    Deletes the document file and purges associated vectors from FAISS index.
    """
    # Delete from local data folder
    file_path = os.path.join(config.DATA_DIR, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.error(f"Failed to remove local file {filename}: {str(e)}")
            
    # Purge vectors from FAISS
    try:
        db = get_db()
        chunks_deleted = delete_document_from_faiss(db, filename)
        # Clear cache since index has updated
        response_cache.clear()
        logger.info(f"Purged {filename} from vector store: {chunks_deleted} chunks removed.")
        return {"status": "success", "chunks_deleted": chunks_deleted}
    except Exception as e:
        logger.error(f"Error deleting {filename} vectors: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete document from index: {str(e)}")

# Admin diagnostics/health check
@app.get("/admin/health")
async def health_check():
    """
    System diagnostic metrics
    """
    try:
        db = get_db()
        vector_stats = get_document_statistics(db)
    except Exception as e:
        vector_stats = {"error": str(e), "total_chunks": 0, "total_files": 0}

    # Gather system usage metrics
    diagnostics = {
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_free_gb": round(psutil.disk_usage(config.BASE_DIR).free / (1024**3), 2)
    }

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "vector_db": {
            "total_chunks": vector_stats.get("total_chunks", 0),
            "total_files": vector_stats.get("total_files", 0)
        },
        "cache": response_cache.get_stats(),
        "diagnostics": diagnostics
    }
