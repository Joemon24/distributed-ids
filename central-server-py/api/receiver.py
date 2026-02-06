from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

@app.post("/ingest")
async def ingest_logs(request: Request):
    data = await request.json()
    print("Received event:", data)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)