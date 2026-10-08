from pathlib import Path

p = Path("zitar_runtime_v1.py")
text = p.read_text(encoding="utf-8-sig")

start_marker = """    if looks_learning(question) and learning_hits:
"""
end_marker = """    # -------------------------------------------------
    # PROJECT MEMORY
"""

start = text.find(start_marker)
end = text.find(end_marker, start)

if start == -1:
    raise SystemExit("STOP: Learning branch baslangici bulunamadi")

if end == -1:
    raise SystemExit("STOP: Project Memory siniri bulunamadi")

new_branch = '''    if looks_learning(question) and learning_hits:

        # Verified Learning Journal evidence only.
        # No LLM generation is allowed in grounded recall.
        top_hit = learning_hits[0]

        text = learning_hit_to_text(
            top_hit
        ).strip()

        if text:

            result.update({
                "route": "LEARNING_RECALL",
                "source": "LEARNING_JOURNAL_DETERMINISTIC",
                "grounded": True,
                "answer": text,
            })

            session["history"].append(result)
            return result

'''

patched = (
    text[:start]
    + new_branch
    + text[end:]
)

p.write_text(
    patched,
    encoding="utf-8"
)

print("LEARNING DETERMINISTIC PATCH PASS")
