"""Re-embed trusted LangChain FAISS docstores into separate OpenAI indexes."""
import argparse
import json
import sys
from tempfile import TemporaryFile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def rebuild(source: Path, destination: Path, trusted: bool):
    if not trusted:
        raise ValueError("Pass --trust-source only for indexes you own; index.pkl uses pickle.")
    if destination.exists():
        raise ValueError(f"Refusing to overwrite {destination}. Choose a new output directory.")
    if not all((source / name).is_file() for name in ("index.faiss", "index.pkl")):
        raise ValueError(f"{source}: index.faiss and index.pkl are required")
    # Fail before incurring embedding charges when the output location cannot
    # be written (for example, /EYKnowledgeBase on a read-only macOS root).
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryFile(dir=destination.parent) as probe:
        probe.write(b"write check")
        probe.flush()
    print(f"Loading FAISS dependencies and source: {source.resolve()}", flush=True)
    from langchain_community.vectorstores import FAISS
    from rag_engine.retrieval import get_embeddings
    from rag_engine.config import EMBEDDINGS_MODEL, EMBEDDINGS_DIMENSIONS

    embeddings = get_embeddings()
    # Loading the old docstore does not embed a query, so its legacy dimensions
    # do not need to match the new OpenAI model.
    old = FAISS.load_local(str(source), embeddings, allow_dangerous_deserialization=True)
    documents = [old.docstore.search(old.index_to_docstore_id[i]) for i in sorted(old.index_to_docstore_id)]
    if not documents or any(not hasattr(doc, "page_content") for doc in documents):
        raise ValueError("Source docstore is empty or contains missing documents")
    print(f"Embedding {len(documents)} chunks with {EMBEDDINGS_MODEL}. "
          "Large corpora may take several minutes; waiting for OpenAI embedding requests...", flush=True)
    new = FAISS.from_documents(documents, embeddings)
    print(f"Saving rebuilt index to {destination.resolve()}", flush=True)
    new.save_local(str(destination))
    (destination / "embedding_manifest.json").write_text(json.dumps({
        "provider": "openai", "model": EMBEDDINGS_MODEL, "dimensions": EMBEDDINGS_DIMENSIONS,
        "document_count": len(documents), "source": str(source.resolve()),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Rebuilt {len(documents)} chunks -> {destination.resolve()}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trust-source", action="store_true")
    args = parser.parse_args()
    try:
        rebuild(args.source, args.output, args.trust_source)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
