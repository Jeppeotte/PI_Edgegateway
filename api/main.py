from fastapi import FastAPI
import uvicorn

# Initialize FastAPI
app = FastAPI()

# Import API routers
from api.configure_node import router as configure_node_router
from api.add_devices import router as add_devices_router
from api.add_applications import router as add_applications_router


app.include_router(configure_node_router)
app.include_router(add_devices_router)
app.include_router(add_applications_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)