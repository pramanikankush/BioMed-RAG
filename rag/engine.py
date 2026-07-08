import os
from typing import List, Dict, Any, Tuple, AsyncIterator
import json
import numpy as np

import requests
import time
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

import config
from rag.hybrid import SparseRetriever, reciprocal_rank_fusion

# Global variables loaded lazily to speed up FastAPI startup
_embeddings = None
_db = None
_llm = None

class HuggingFaceAPIEmbeddings(Embeddings):
    def __init__(self, model_name: str, api_key: str = None):
        self.model_name = model_name
        self.api_key = api_key
        # Use feature-extraction pipeline explicitly — model is tagged as sentence-similarity
        # on HF Hub which causes the generic /models/ endpoint to misroute to SentenceSimilarityPipeline
        self.api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_name}"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Retry loop for 503 Service Unavailable (loading model)
        for attempt in range(5):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json={"inputs": texts, "options": {"wait_for_model": True}},
                    timeout=30
                )
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list):
                        return result
                    else:
                        raise ValueError(f"Unexpected response format from Hugging Face: {result}")
                elif response.status_code == 503:
                    # Model is loading, wait and retry
                    time.sleep(5)
                    continue
                else:
                    raise Exception(f"HF API Error (Status {response.status_code}): {response.text}")
            except requests.exceptions.RequestException as e:
                if attempt == 4:
                    raise
                time.sleep(2)
        raise Exception("Failed to get embeddings from Hugging Face after multiple attempts.")

    def embed_query(self, text: str) -> List[float]:
        result = self.embed_documents([text])
        return result[0]

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        if config.HF_TOKEN:
            # Use Hugging Face serverless Inference API (saves memory and avoids downloading models)
            _embeddings = HuggingFaceAPIEmbeddings(
                model_name=config.EMBEDDING_MODEL,
                api_key=config.HF_TOKEN
            )
        else:
            try:
                from langchain_community.embeddings import SentenceTransformerEmbeddings
                _embeddings = SentenceTransformerEmbeddings(model_name=config.EMBEDDING_MODEL)
            except ImportError:
                raise ImportError(
                    "To use local embeddings, please install sentence-transformers: 'pip install sentence-transformers'. "
                    "Alternatively, set the 'HF_TOKEN' environment variable to use the serverless Hugging Face API (recommended for Render)."
                )
    return _embeddings

def get_db():
    global _db
    embeddings = get_embeddings()
    if _db is None:
        if os.path.exists(os.path.join(config.INDEX_DIR, "index.faiss")):
            _db = FAISS.load_local(config.INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
        else:
            # Initialize empty database with a placeholder document
            placeholder = Document(
                page_content="Placeholder document for empty vector index.",
                metadata={"source": "system_placeholder", "page": 1}
            )
            _db = FAISS.from_documents([placeholder], embeddings)
            _db.save_local(config.INDEX_DIR)
    return _db

def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=config.LLM_MODEL,
            temperature=0.2,
            max_tokens=2048,
            api_key=config.GROQ_API_KEY
        )
    return _llm

# Grounding / RAG prompt template
RAG_PROMPT_TEMPLATE = """You are a highly professional medical assistant. Answer the user's medical question using ONLY the provided pieces of retrieved information (both local documents and web search results, if applicable).

Strict Guidelines:
1. Grounding: Answer ONLY based on the provided context. If the answer cannot be found in the provided context, state clearly: "I cannot find this information in the uploaded documents. Try enabling Web Search or uploading more documents."
2. Formatting: Provide a structured, detailed, and well-explained answer.
3. Citations: When referencing facts, cite the source name (e.g., [Oncology.pdf]) or web page URL.

Retrieved Context:
{context}

Conversation History:
{chat_history}

Question: {question}

Helpful Medical Answer:
"""

def get_hybrid_context(query: str, db: FAISS, top_k: int = 5) -> Tuple[List[Dict[str, Any]], float]:
    """
    Executes hybrid dense-sparse search and returns a list of source dicts and an aggregate confidence score.
    """
    # 1. Dense Semantic Search (FAISS)
    try:
        # FAISS search_with_score returns L2 distance (lower is better) or similarity (higher is better)
        dense_results_raw = db.similarity_search_with_score(query, k=top_k)
        # Normalize FAISS L2 distance scores (commonly 0 to 2) to a similarity range [0, 1]
        dense_results = []
        for doc, score in dense_results_raw:
            # Skip system placeholder documents
            if doc.metadata.get('source') == 'system_placeholder':
                continue
            sim_score = 1.0 / (1.0 + float(score))
            dense_results.append((doc, sim_score))
    except Exception:
        dense_results = []

    # 2. Sparse Keyword Search (TF-IDF)
    all_docs = list(db.docstore._dict.values())
    all_docs = [d for d in all_docs if d.metadata.get('source') != 'system_placeholder']
    
    if all_docs:
        sparse_retriever = SparseRetriever(all_docs)
        sparse_results = sparse_retriever.retrieve(query, k=top_k)
    else:
        sparse_results = []

    # 3. Reciprocal Rank Fusion (RRF)
    hybrid_results = reciprocal_rank_fusion(dense_results, sparse_results, k_rrf=60)
    
    # Take top_k from hybrid results
    top_hybrid = hybrid_results[:top_k]
    
    sources = []
    max_confidence = 0.0
    for doc, conf_score in top_hybrid:
        sources.append({
            "page_content": doc.page_content,
            "source": doc.metadata.get('source', 'Unknown'),
            "page": doc.metadata.get('page', 1),
            "score": conf_score
        })
        if conf_score > max_confidence:
            max_confidence = conf_score
            
    return sources, max_confidence

async def execute_rag_stream(
    query: str,
    chat_history: List[Dict[str, str]],
    use_web: bool,
    tavily_api_key: str = None
) -> AsyncIterator[str]:
    """
    Executes the RAG pipeline and yields streaming tokens alongside context details in SSE format.
    """
    db = get_db()
    llm = get_llm()

    # 1. Retrieve local context using Hybrid Search
    local_sources, local_conf = get_hybrid_context(query, db)
    
    # 2. Optionally fetch Web Context via Tavily
    web_sources = []
    web_error = None
    if use_web and config.TAVILY_API_KEY:
        from search.tavily import execute_web_search
        try:
            web_sources = execute_web_search(query, config.TAVILY_API_KEY)
        except Exception as e:
            web_error = str(e)

    # 3. Merge contexts
    combined_context_parts = []
    
    # Local docs context formatting
    for idx, src in enumerate(local_sources, start=1):
        combined_context_parts.append(
            f"--- Local Source {idx}: [{src['source']}] (Page {src['page']}) ---\n{src['page_content']}"
        )
        
    # Web context formatting
    for idx, src in enumerate(web_sources, start=1):
        combined_context_parts.append(
            f"--- Web Source {idx}: [{src['title']}] ({src['url']}) ---\n{src['content']}"
        )

    context_str = "\n\n".join(combined_context_parts) if combined_context_parts else "No context found."
    
    # 4. Calculate final confidence score
    # RRF score combined with whether web search returned results
    final_confidence = local_conf
    if use_web and web_sources:
        # Boost confidence slightly if web results exist
        final_confidence = min(final_confidence + 0.15, 1.0)
    elif not local_sources:
        final_confidence = 0.0

    # Yield metadata header first in SSE format
    metadata = {
        "local_sources": local_sources,
        "web_sources": web_sources,
        "confidence": round(final_confidence, 2),
        "web_error": web_error
    }
    yield f"data: {json.dumps({'metadata': metadata})}\n\n"

    # Format chat history
    chat_history_str = ""
    for msg in chat_history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        chat_history_str += f"{role}: {msg.get('content')}\n"
    if not chat_history_str:
        chat_history_str = "No previous conversation history."

    # Build prompt
    prompt = PromptTemplate(template=RAG_PROMPT_TEMPLATE, input_variables=['context', 'chat_history', 'question'])
    prompt_text = prompt.format(context=context_str, chat_history=chat_history_str, question=query)

    # 5. Stream response tokens from Groq LLM
    try:
        async for chunk in llm.astream(prompt_text):
            yield f"data: {json.dumps({'token': chunk.content})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'LLM Generation Error: {str(e)}'})}\n\n"
        
    yield "data: [DONE]\n\n"
