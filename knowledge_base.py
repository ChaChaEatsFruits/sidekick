"""Knowledge base: load the documents in kb/, chunk them, embed them, store them in Chroma, search them."""

from functools import cache
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

HERE = Path(__file__).parent
KB_DIR = HERE / "kb"
DB_DIR = HERE / "chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # local, free, 384 dims; truncates input past 256 word pieces
CHUNK_SIZE = 800  # characters, roughly 200 tokens
CHUNK_OVERLAP = 120


def load_documents(folder: Path = KB_DIR) -> list[tuple[str, str]]:
    """Return (file name, full text) for every PDF, Markdown and text file in the folder."""
    docs = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() == ".pdf":
            text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        elif path.suffix.lower() in (".md", ".txt"):
            text = path.read_text(encoding="utf-8")
        else:
            continue
        docs.append((path.name, text))
    return docs


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split on paragraphs, then lines, then words, so chunks break at natural boundaries."""
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap).split_text(text)


@cache
def _client():
    return chromadb.PersistentClient(path=str(DB_DIR))


@cache
def _embedder():
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)


def _collection(name: str):
    return _client().get_or_create_collection(
        name, embedding_function=_embedder(), metadata={"hnsw:space": "cosine"}
    )


def build_index(name: str = "knowledge_base", chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP,
                folder: Path = KB_DIR) -> int:
    """Rebuild the collection from scratch and return the number of chunks stored."""
    collection = _collection(name)
    # empty it rather than delete_collection: re-creating a deleted collection in the same process fails
    if old_ids := collection.get(include=[])["ids"]:
        collection.delete(ids=old_ids)
    ids, texts, metadatas = [], [], []
    for source, text in load_documents(folder):
        for i, chunk in enumerate(chunk_text(text, chunk_size, overlap)):
            ids.append(f"{source}#{i}")
            texts.append(chunk)
            metadatas.append({"source": source, "chunk": i})
    if ids:
        collection.add(ids=ids, documents=texts, metadatas=metadatas)
    return len(ids)


def search(query: str, k: int = 5, name: str = "knowledge_base") -> list[dict]:
    """Return the k chunks closest to the query, best first, with their source and cosine similarity."""
    result = _collection(name).query(query_texts=[query], n_results=k)
    return [
        {"source": meta["source"], "chunk": meta["chunk"], "text": text, "score": round(1 - distance, 3)}
        for meta, text, distance in zip(result["metadatas"][0], result["documents"][0], result["distances"][0])
    ]


def get_chunks(ids: list[str], name: str = "knowledge_base") -> dict[str, str]:
    """Look up chunks by their [file#chunk] id; ids that do not exist are left out."""
    result = _collection(name).get(ids=ids)
    return dict(zip(result["ids"], result["documents"]))


def warm_up(name: str = "knowledge_base") -> None:
    """Load the embedding model now (the first load takes ~30s) and build the index on a fresh clone."""
    if _collection(name).count() == 0:
        build_index(name)
    search("warm up", k=1, name=name)


if __name__ == "__main__":
    print(f"Indexed {build_index()} chunks from {KB_DIR}")
    for hit in search("What is the maximum line length?", k=3):
        print(hit["score"], f"{hit['source']}#{hit['chunk']}", hit["text"][:80].replace("\n", " "))
