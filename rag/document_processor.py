import os
from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
import config

def get_document_loader(file_path: str):
    """
    Returns the appropriate document loader based on file extension.
    """
    _, ext = os.path.splitext(file_path.lower())
    if ext == '.pdf':
        return PyPDFLoader(file_path)
    elif ext == '.docx':
        return Docx2txtLoader(file_path)
    elif ext == '.txt':
        return TextLoader(file_path, encoding='utf-8')
    else:
        raise ValueError(f"Unsupported file format: {ext}")

def process_file_to_chunks(file_path: str) -> List[Document]:
    """
    Loads a file and splits it into text chunks.
    """
    loader = get_document_loader(file_path)
    documents = loader.load()
    
    # Inject source file name and page number into metadata if not present
    for doc in documents:
        # Normalize source path for clean display
        doc.metadata['source'] = os.path.basename(file_path)
        if 'page' not in doc.metadata:
            doc.metadata['page'] = 1
            
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=70)
    return text_splitter.split_documents(documents)

def add_document_to_faiss(db: FAISS, file_path: str) -> int:
    """
    Loads, chunks, and adds a new document to the existing FAISS index.
    Saves the index back to disk. Returns number of chunks added.
    """
    chunks = process_file_to_chunks(file_path)
    if chunks:
        db.add_documents(chunks)
        db.save_local(config.INDEX_DIR)
    return len(chunks)

def delete_document_from_faiss(db: FAISS, filename: str) -> int:
    """
    Deletes all chunks belonging to a document from the FAISS index by searching metadata.
    Saves the index back to disk. Returns number of chunks deleted.
    """
    target_basename = os.path.basename(filename)
    ids_to_delete = []
    
    # Access private docstore dictionary safely
    for doc_id, doc in db.docstore._dict.items():
        doc_source = doc.metadata.get('source', '')
        if os.path.basename(doc_source) == target_basename:
            ids_to_delete.append(doc_id)
            
    if ids_to_delete:
        db.delete(ids_to_delete)
        db.save_local(config.INDEX_DIR)
        
    return len(ids_to_delete)

def get_document_statistics(db: FAISS) -> Dict[str, Any]:
    """
    Returns document store stats (number of files, chunks, list of unique files).
    """
    unique_files = set()
    total_chunks = 0
    
    for doc in db.docstore._dict.values():
        total_chunks += 1
        source = doc.metadata.get('source', 'Unknown')
        unique_files.add(os.path.basename(source))
        
    # Get file stats from the disk folder
    files_list = []
    for filename in unique_files:
        file_path = os.path.join(config.DATA_DIR, filename)
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
        else:
            size = 0
        files_list.append({
            "name": filename,
            "size": size,
            "chunks": sum(1 for doc in db.docstore._dict.values() if os.path.basename(doc.metadata.get('source', '')) == filename)
        })
        
    return {
        "total_chunks": total_chunks,
        "total_files": len(unique_files),
        "files": files_list
    }
