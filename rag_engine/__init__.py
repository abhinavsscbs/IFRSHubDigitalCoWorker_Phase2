"""Lazy public surface: importing configuration never initializes models or indexes."""
from importlib import import_module

_MODULES = {
    "answer": ["answer_with_refine_chain", "build_confidence_result", "classify_confidence",
               "generate_unified_reference_list", "retrieve_and_generate_exceptions"],
    "retrieval": ["DBConfig", "DBS", "build_retriever", "fetch_docs", "load_index", "retrieve_docs_with_score"],
    "translate": ["translate_to_arabic"],
    "exports": ["FPDF_AVAILABLE", "REPORTLAB_AVAILABLE", "_build_html_export", "_build_pdf_fpdf", "_build_pdf_reportlab"],
    "formatting": ["_format_duration", "_make_excerpt", "_unify_metadata", "bold_standards", "emphasize_headers",
                   "fix_citation_format", "format_visible_answer", "remove_citations", "sanitize_text"],
}
__all__ = [name for names in _MODULES.values() for name in names]


def __getattr__(name):
    for module, names in _MODULES.items():
        if name in names:
            value = getattr(import_module(f".{module}", __name__), name)
            globals()[name] = value
            return value
    raise AttributeError(name)
