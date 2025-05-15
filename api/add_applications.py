from fastapi import APIRouter, HTTPException
from pathlib import Path

router = APIRouter(prefix="/api/add_applications")

#Directory for running locally
local_dir = r"C:\Users\jeppe\OneDrive - Aalborg Universitet\Masters\4. Semester\Gateway Configurator"
mounted_dir = Path(local_dir)
#Directory for docker container
#mounted_dir = Path("/mounted_dir")