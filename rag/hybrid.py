import hashlib
from typing import List, Tuple
from langchain_core.documents import Document
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

class SparseRetriever:
    """
    A TF-IDF sparse retriever built on top of scikit-learn.
    Used alongside dense FAISS search for hybrid retrieval.
    """
    def __init__(self, documents: List[Document]):
        self.documents = documents
        self.texts = [doc.page_content for doc in documents]
        self.vectorizer = TfidfVectorizer(stop_words='english')
        if self.texts:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.texts)
        else:
            self.tfidf_matrix = None

    def retrieve(self, query: str, k: int = 5) -> List[Tuple[Document, float]]:
        """
        Retrieve top K documents matching the keyword query.
        """
        if self.tfidf_matrix is None or not self.texts:
            return []

        query_vec = self.vectorizer.transform([query])
        # Calculate cosine similarities
        scores = (self.tfidf_matrix * query_vec.T).toarray().flatten()
        top_indices = np.argsort(scores)[::-1][:k]
        
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score > 0.0:  # Only return documents with some keyword overlap
                results.append((self.documents[idx], score))
        return results

def reciprocal_rank_fusion(
    dense_results: List[Tuple[Document, float]],
    sparse_results: List[Tuple[Document, float]],
    k_rrf: int = 60
) -> List[Tuple[Document, float]]:
    """
    Combines dense and sparse search results using Reciprocal Rank Fusion (RRF).
    Returns list of (Document, normalized_confidence_score).
    """
    rrf_scores = {}
    doc_map = {}

    def get_doc_key(doc: Document) -> str:
        # Generate a unique key based on chunk content hash
        return hashlib.sha256(doc.page_content.encode('utf-8')).hexdigest()

    # Apply RRF formula to dense results
    for rank, (doc, _) in enumerate(dense_results, start=1):
        key = get_doc_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k_rrf + rank))

    # Apply RRF formula to sparse results
    for rank, (doc, _) in enumerate(sparse_results, start=1):
        key = get_doc_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k_rrf + rank))

    # Sort documents by total RRF score
    sorted_keys = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Normalize RRF scores to 0-1 scale for UI readability
    # Max theoretical RRF score = 1/(k_rrf + 1) + 1/(k_rrf + 1) = 2/(k_rrf + 1)
    max_possible_rrf = 2.0 / (k_rrf + 1)

    results = []
    for key, score in sorted_keys:
        normalized_score = min(score / max_possible_rrf, 1.0)
        # Round for nice UI representation
        results.append((doc_map[key], round(normalized_score, 4)))

    return results
