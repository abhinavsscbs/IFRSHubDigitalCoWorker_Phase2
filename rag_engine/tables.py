import json
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")
_SEP_CELL_RE = re.compile(r"^:?-{1,}:?$")
MIN_DASHES = 1
_NUM_NULLS = {"", "na", "n/a", "none", "null", "nil", "-", "—", "–"}


def _is_sep_line(s: str) -> bool:
    if not s or "|" not in s:
        return False
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells = [c.strip().replace("\t", " ") for c in s.split("|")]
    if len(cells) < 2:
        return False
    sep_cell_re = re.compile(rf"^:?-{{{MIN_DASHES},}}:?$")
    matches = sum(1 for c in cells if sep_cell_re.fullmatch(c))
    return matches >= max(2, len(cells) - 1)


def _split_pipe_row(row: str) -> List[str]:
    raw = row.rstrip("\n")
    s = raw.strip()
    has_leading = s.startswith("|")
    has_trailing = s.endswith("|")
    parts = _PIPE_SPLIT_RE.split(s)
    if not has_leading and parts and parts[0] == "":
        parts = parts[1:]
    if not has_trailing and parts and parts[-1] == "":
        parts = parts[:-1]
    return [p.replace(r"\|", "|").strip() for p in parts]


def _find_markdown_tables(md: str) -> List[Tuple[int, int, str]]:
    lines = md.splitlines()
    i, n = 0, len(lines)
    blocks: List[Tuple[int, int, str]] = []
    while i < n - 1:
        line = lines[i]
        next_line = lines[i + 1]
        if ("|" in line) and ("|" in next_line) and _is_sep_line(next_line):
            start = i
            i += 2
            while i < n and ("|" in lines[i]) and (lines[i].strip() != ""):
                i += 1
            end = i
            block_text = "\n".join(lines[start:end])
            block_lines = [ln for ln in block_text.splitlines() if ln.strip()]
            if len(block_lines) >= 3:
                blocks.append((start, end, block_text))
        else:
            i += 1
    return blocks


def _infer_col_count(header_line: str, sep_line: str, data_lines: List[str]) -> int:
    counts = []
    counts.append(len(_split_pipe_row(header_line)))
    if sep_line:
        counts.append(len(_split_pipe_row(sep_line)))
    for ln in data_lines:
        counts.append(len(_split_pipe_row(ln)))
    from collections import Counter

    c = Counter(counts)
    most_common = c.most_common(1)[0][0] if counts else 0
    return most_common or (max(counts) if counts else 0)


def _normalize_table_cell(val: Any) -> str:
    if val is None:
        return "—"
    if isinstance(val, float) and np.isnan(val):
        return "—"
    s = str(val).replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()
    if s == "" or s.lower() in _NUM_NULLS:
        return "—"
    return s


def _mk_pipe_row(cells: List[str]) -> str:
    return "| " + " | ".join(_normalize_table_cell(c) for c in cells) + " |"


def _mk_pipe_sep(ncols: int) -> str:
    return "| " + " | ".join(["---"] * max(1, ncols)) + " |"


def _looks_like_sep_row(s: str) -> bool:
    if "|" not in s:
        return False
    parts = _split_pipe_row(s)
    if len(parts) < 2:
        return False
    matches = sum(1 for c in parts if _SEP_CELL_RE.fullmatch((c or "").strip()))
    return matches >= max(2, len(parts) - 1)


def _expand_inline_pipe_table(line: str) -> Optional[str]:
    if "|" not in line:
        return None

    def _parse_tokens(tokens: List[str]) -> Optional[Tuple[List[str], int, int, List[str]]]:
        if len(tokens) < 6:
            return None
        sep_idx = None
        for i, t in enumerate(tokens):
            if _SEP_CELL_RE.fullmatch(t):
                sep_idx = i
                break
        if sep_idx is None or sep_idx < 1:
            return None
        j = sep_idx
        while j < len(tokens) and _SEP_CELL_RE.fullmatch(tokens[j]):
            j += 1
        header = tokens[:sep_idx]
        ncols = len(header)
        sep_len = j - sep_idx
        data = tokens[j:]
        if ncols < 2 or len(data) < ncols:
            return None
        return header, ncols, sep_len, data

    toks = [t.strip() for t in _PIPE_SPLIT_RE.split(line)]
    if toks and toks[0] == "":
        toks = toks[1:]
    if toks and toks[-1] == "":
        toks = toks[:-1]

    parsed = _parse_tokens(toks)
    if parsed is None:
        toks_compact = [t for t in toks if t != ""]
        parsed = _parse_tokens(toks_compact)
        if parsed is None:
            return None
    header, ncols, sep_len, data = parsed

    prefix = ""
    if sep_len != ncols and len(toks) > 1:
        parsed2 = _parse_tokens(toks[1:])
        if parsed2 is None:
            return None
        header2, ncols2, sep_len2, data2 = parsed2
        if sep_len2 == ncols2:
            prefix = toks[0]
            header, ncols, sep_len, data = header2, ncols2, sep_len2, data2
        else:
            toks_compact = [t for t in toks if t != ""]
            if len(toks_compact) > 1:
                parsed3 = _parse_tokens(toks_compact[1:])
                if parsed3 is None:
                    return None
                header, ncols, sep_len, data = parsed3
                prefix = toks_compact[0]
            else:
                return None

    if header and header[-1] == "" and (ncols - 1) == sep_len:
        header = header[:-1]
        ncols = len(header)

    if (len(data) % ncols) != 0 and any(t == "" for t in data):
        data = [t for t in data if t != ""]
        if len(data) < ncols or (len(data) % ncols) != 0:
            return None

    out_lines = []
    if prefix:
        out_lines.append(prefix)
    out_lines.append("| " + " | ".join(header) + " |")
    out_lines.append("| " + " | ".join(["---"] * ncols) + " |")

    for k in range(0, len(data), ncols):
        row = data[k : k + ncols]
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < ncols:
            row += [""] * (ncols - len(row))
        out_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(out_lines)


def _normalize_markdown_tables(md: str) -> str:
    if not md:
        return md

    text = md.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ").replace("\u200b", "")

    def _is_tsv_row(s: str) -> bool:
        if "\t" not in s:
            return False
        parts = [p.strip() for p in s.split("\t")]
        return sum(1 for p in parts if p) >= 2

    expanded = []
    for ln in text.split("\n"):
        maybe = _expand_inline_pipe_table(ln)
        if maybe:
            expanded.extend(maybe.split("\n"))
            continue
        if "|" in ln and not ln.lstrip().startswith("|"):
            first_pipe = ln.find("|")
            prefix = ln[:first_pipe].rstrip()
            table_part = ln[first_pipe:].lstrip()
            if table_part.startswith("|"):
                maybe2 = _expand_inline_pipe_table(table_part)
                if maybe2:
                    if prefix:
                        expanded.append(prefix)
                    expanded.extend(maybe2.split("\n"))
                    continue
        expanded.append(ln)
    text = "\n".join(expanded)

    lines = text.split("\n")
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 2 < len(lines):
            next_line = lines[i + 1]
            next2 = lines[i + 2]
            if ("|" in line) and ("|" in next_line) and (not next_line.lstrip().startswith("|")):
                if _looks_like_sep_row(next2) and not _looks_like_sep_row(next_line):
                    merged.append(line.rstrip() + " " + next_line.strip())
                    i += 2
                    continue
        merged.append(line)
        i += 1
    text = "\n".join(merged)

    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if _is_tsv_row(lines[i]):
            block = []
            while i < len(lines) and _is_tsv_row(lines[i]):
                block.append(lines[i])
                i += 1
            if block:
                header = [c.strip() for c in block[0].split("\t")]
                out.append(_mk_pipe_row(header))
                out.append(_mk_pipe_sep(len(header)))
                for row in block[1:]:
                    out.append(_mk_pipe_row([c.strip() for c in row.split("\t")]))
            continue
        out.append(lines[i])
        i += 1
    text = "\n".join(out)

    text = re.sub(r"(\|[^\n]*?\|)\s+(\|?\s*(?:\:?-{1,}\:?\s*\|)+\s*\:?-{1,}\:?\s*\|?)", r"\1\n\2", text)
    text = re.sub(r"(\|(?:\s*:?-{1,}\s*\|)+\s*:?-{1,}\s*\|)\s*\|\s*", r"\1\n| ", text)
    text = re.sub(r"\s\|\s*\|\s*(?=\S)", r"\n| ", text)

    def _canonicalize_block(block_md: str) -> str:
        try:
            df = _md_table_to_df(block_md)
            df = df.fillna("")
            cols = [str(c).strip() or f"col_{i+1}" for i, c in enumerate(df.columns)]
            canon = [_mk_pipe_row(cols), _mk_pipe_sep(len(cols))]
            for _, row in df.iterrows():
                cells = [str(row[c]).strip() for c in df.columns]
                canon.append(_mk_pipe_row(cells))
            return "\n".join(canon)
        except Exception:
            lines = [ln for ln in block_md.splitlines() if ln.strip()]
            if len(lines) >= 2:
                header = _split_pipe_row(lines[0])
                ncols = max(1, len(header))
                body = []
                for ln in lines[1:]:
                    if _looks_like_sep_row(ln):
                        continue
                    body.append(_mk_pipe_row(_split_pipe_row(ln)))
                return "\n".join([_mk_pipe_row(header), _mk_pipe_sep(ncols)] + body)
            return block_md

    canon_lines = text.split("\n")
    blocks = _find_markdown_tables(text)
    if not blocks:
        return text

    rebuilt = []
    cursor = 0
    for (start, end, block_txt) in blocks:
        rebuilt.append("\n".join(canon_lines[cursor:start]))
        rebuilt.append(_canonicalize_block(block_txt))
        cursor = end
    rebuilt.append("\n".join(canon_lines[cursor:]))

    final = "\n".join(rebuilt)
    final = re.sub(r"\n{3,}", "\n\n", final).strip("\n")
    return final


def _md_table_to_df(table_md: str) -> pd.DataFrame:
    raw_lines = [l for l in table_md.splitlines() if l.strip()]
    if len(raw_lines) < 2:
        raise ValueError("Not enough lines for a markdown table block.")

    sep_idx = None
    for i in range(1, len(raw_lines)):
        if _looks_like_sep_row(raw_lines[i]):
            sep_idx = i
            break

    if sep_idx is None or sep_idx == 0:
        header_line = raw_lines[0]
        sep_line = raw_lines[1] if len(raw_lines) > 1 else ""
        data_lines = raw_lines[2:] if len(raw_lines) > 2 else []
    else:
        header_line = raw_lines[sep_idx - 1]
        sep_line = raw_lines[sep_idx]
        data_lines = raw_lines[sep_idx + 1:]

    col_count = _infer_col_count(header_line, sep_line, data_lines)
    if col_count <= 0:
        raise ValueError("Could not infer a positive column count.")

    header = _split_pipe_row(header_line)
    if len(header) < col_count:
        header += [f"col_{i+1}" for i in range(len(header), col_count)]
    elif len(header) > col_count:
        header = header[:col_count]

    rows = []
    for ln in data_lines:
        if _looks_like_sep_row(ln):
            continue
        cells = _split_pipe_row(ln)
        if not cells or all((c or "").strip() == "" for c in cells):
            continue
        if len(cells) < col_count:
            cells += [""] * (col_count - len(cells))
        elif len(cells) > col_count:
            cells = cells[:col_count]
        rows.append(cells)

    df = pd.DataFrame(rows, columns=header)
    df = _drop_leading_empty_column(df)

    def _maybe_num(x):
        s = str(x).strip().replace(",", "")
        if s.endswith("%"):
            try:
                return float(s[:-1]) / 100.0
            except Exception:
                return x
        if s.startswith("(") and s.endswith(")"):
            try:
                return -float(s[1:-1])
            except Exception:
                return x
        try:
            return float(s) if "." in s else int(s)
        except Exception:
            return x

    for c in df.columns:
        ser = df[c].astype(str)
        probe = ser.map(lambda v: _maybe_num(v) if v.strip() != "" else v)
        non_blank = ser.str.strip() != ""
        numericish = sum(isinstance(v, (int, float)) for v in probe[non_blank])
        if non_blank.sum() and numericish / non_blank.sum() >= 0.5:
            df[c] = pd.to_numeric(probe, errors="ignore")

    return df


def _canonicalize_all_tables(md_text: str) -> str:
    if not md_text:
        return md_text
    md_text = _normalize_markdown_tables(md_text)
    blocks = _find_markdown_tables(md_text)
    if not blocks:
        return md_text

    lines = md_text.splitlines()
    rebuilt, cursor = [], 0
    for (start, end, block) in blocks:
        if start > cursor:
            rebuilt.append("\n".join(lines[cursor:start]))
        try:
            df = _md_table_to_df(block)
            df = df.fillna("")
            df = _drop_leading_empty_column(df)
            cols = [str(c).strip() or f"col_{i+1}" for i, c in enumerate(df.columns)]
            chunk = [_mk_pipe_row(cols), _mk_pipe_sep(len(cols))]
            for _, row in df.iterrows():
                chunk.append(_mk_pipe_row([str(row[c]).strip() for c in df.columns]))
            rebuilt.append("\n".join(chunk))
        except Exception:
            rebuilt.append(block)
        cursor = end
    if cursor < len(lines):
        rebuilt.append("\n".join(lines[cursor:]))
    out = "\n".join(rebuilt)
    return re.sub(r"\n{3,}", "\n\n", out).strip("\n")


def _strip_markdown_tables_from_text(md_text: str) -> str:
    if not md_text:
        return md_text
    md_text = _canonicalize_all_tables(md_text)
    blocks = _find_markdown_tables(md_text)
    if not blocks:
        return md_text
    lines = md_text.splitlines()
    rebuilt, cursor = [], 0
    for (start, end, _block) in blocks:
        if start > cursor:
            rebuilt.append("\n".join(lines[cursor:start]))
        cursor = end
    if cursor < len(lines):
        rebuilt.append("\n".join(lines[cursor:]))
    out = "\n".join(rebuilt)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _split_answer_and_json(output_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    if not output_text:
        return "", None
    s = output_text.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", s)
    if not m:
        return s, None
    json_text = m.group(0)
    try:
        data = json.loads(json_text)
    except Exception:
        return s, None
    if not isinstance(data, dict):
        return s, None
    answer_body = s[: m.start()].rstrip()
    return answer_body, data


def _normalize_tables_payload(tables: Any) -> List[Dict[str, Any]]:
    if not isinstance(tables, list):
        return []
    out: List[Dict[str, Any]] = []
    for t in tables:
        if not isinstance(t, dict):
            continue
        cols = t.get("columns") or []
        rows = t.get("rows") or []
        if not isinstance(cols, list) or not isinstance(rows, list):
            continue
        out.append(
            {
                "table_name": t.get("table_name") or "",
                "columns": cols,
                "rows": rows,
            }
        )
    return out


def _drop_leading_empty_column(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    first_col = df.columns[0]
    bad_name = (str(first_col).strip().lower() in {"", "col_1", "column_1", "unnamed: 0"})
    ser = df[first_col].astype(str)
    is_empty_col = ser.map(lambda v: (v or "").strip() == "").all()
    if bad_name or is_empty_col:
        if len(df.columns) > 1:
            return df.drop(columns=[first_col])
    return df


def extract_markdown_tables_as_dfs(md_text: str) -> List[pd.DataFrame]:
    if not md_text:
        return []
    md_text = _canonicalize_all_tables(md_text)
    blocks = _find_markdown_tables(md_text)
    dfs: List[pd.DataFrame] = []
    for _, _, block in blocks:
        try:
            df = _md_table_to_df(block)
            df = _drop_leading_empty_column(df)
            dfs.append(df)
        except Exception:
            pass
    return dfs


__all__ = [
    "_canonicalize_all_tables",
    "_drop_leading_empty_column",
    "_find_markdown_tables",
    "_md_table_to_df",
    "_mk_pipe_row",
    "_mk_pipe_sep",
    "_normalize_markdown_tables",
    "_split_pipe_row",
    "_split_answer_and_json",
    "_normalize_tables_payload",
    "_strip_markdown_tables_from_text",
    "extract_markdown_tables_as_dfs",
]
