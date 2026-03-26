from pydantic import BaseModel
from datetime import datetime
from typing import Any

class ProcessedPacket(BaseModel):
    id: str
    timestamp: datetime
    text: str
    metadata: dict[str. Any]

class ReadyPacket(ProcessedPacket):
    pass


