import logging
from fastapi import FastAPI
from main import router  # Import the router from main.py

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Include the router from main.py
app.include_router(router)

@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "Hello World"}