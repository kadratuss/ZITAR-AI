from pathlib import Path

p = Path("zitar_runtime_v1.py")
text = p.read_text(encoding="utf-8-sig")

start_marker = """    if project_hits:
"""
end_marker = """    # -------------------------------------------------
    # NO GROUNDED ANSWER
"""

start = text.find(start_marker)
end = text.find(end_marker, start)

if start == -1:
    raise SystemExit("STOP: Project branch baslangici bulunamadi")

if end == -1:
    raise SystemExit("STOP: Knowledge Gap siniri bulunamadi")

new_branch = '''    if project_hits:

        # Verified Project Memory evidence only.
        # No LLM generation is allowed in grounded recall.
        top_hit = project_hits[0]

        text = project_hit_to_text(
            top_hit
        ).strip()

        if text:

            result.update({
                "route": "PROJECT_RECALL",
                "source": "PROJECT_MEMORY_DETERMINISTIC",
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

print("PROJECT DETERMINISTIC PATCH PASS")
