from datetime import datetime
import uuid

def generate_uuid_with_timestamp():
    uid = str(uuid.uuid4())
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{uid}_{timestamp}"