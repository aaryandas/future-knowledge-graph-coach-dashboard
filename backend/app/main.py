from fastapi import FastAPI

app = FastAPI(title="KG Coach Dashboard API")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
