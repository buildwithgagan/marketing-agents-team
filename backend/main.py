import uvicorn
import os
from dotenv import load_dotenv

# Load env variables
load_dotenv()

PORT = int(os.getenv("PORT", 8000))

if __name__ == "__main__":
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
        access_log=True,
    )
