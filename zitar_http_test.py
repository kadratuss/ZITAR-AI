import json
import urllib.request

payload = {
    "message": "Model tren projesinde en son ne yapmıştık?",
    "session_id": "python-utf8-test"
}

data = json.dumps(
    payload,
    ensure_ascii=False
).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/zitar/chat",
    data=data,
    headers={
        "Content-Type": "application/json; charset=utf-8"
    },
    method="POST"
)

with urllib.request.urlopen(req, timeout=60) as response:
    result = json.loads(
        response.read().decode("utf-8")
    )

print("QUESTION:", result["question"])
print("ROUTE:", result["route"])
print("SOURCE:", result["source"])
print("GROUNDED:", result["grounded"])
print("ANSWER:", result["answer"])

with open(
    "zitar_python_http_test.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        result,
        f,
        ensure_ascii=False,
        indent=2
    )
