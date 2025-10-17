import os
from typing import List

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

EMBEDDING_MODEL = "text-embedding-3-small"

def get_vector_store(book_id: str, persist_directory: str) -> Chroma:
    """Loads or creates a persistent Chroma vector store"""
    if os.path.exists(persist_directory):
        print(f"Loading existing vector store for book_id: {book_id}")
        vector_store = Chroma(
            persist_directory=persist_directory,
            embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL),
        )
    else:
        raise FileNotFoundError(
            f"Could not find vector store for book_id: {book_id}"
        )
    return vector_store

def create_vector_store_from_documents(documents: List[Document], persist_directory: str) -> Chroma:
    """Creates a persistent Chroma vector store from a list of documents"""
    print(f"Creating new vector store at: {persist_directory}")
    vector_store = Chroma.from_documents(
        documents=documents,
        embedding=OpenAIEmbeddings(model=EMBEDDING_MODEL),
        persist_directory=persist_directory,
    )
    return vector_store
