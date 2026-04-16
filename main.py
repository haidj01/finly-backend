import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.claude   import router as claude_router
from routes.alpaca   import router as alpaca_router
from routes.news     import router as news_router
from routes.trending import router as trending_router

app = FastAPI(title="Finly Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(claude_router)
app.include_router(alpaca_router)
app.include_router(news_router)
app.include_router(trending_router)



@app.get("/health")
def health():
    return {"status": "ok"}
