import uuid

from elasticsearch import Elasticsearch
from datetime import datetime, timezone

es = Elasticsearch(
    "http://localhost:9200",
    verify_certs=False,
    request_timeout=30
)

INCIDENT_INDEX = "ids-incidents"


def create_incident(event):

    incident_id = str(uuid.uuid4())[:8]

    incident = {

        "incident_id": incident_id,

        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "status": "open",

        "attack_type": event.get(
            "alert_type"
        ),

        "severity": event.get(
            "severity"
        ),

        "source_ip": event.get(
            "src_ip"
        ),

        "username": event.get(
            "username"
        ),

        "mitre": event.get(
            "mitre_technique"
        ),
    }

    es.index(
        index=INCIDENT_INDEX,
        document=incident
    )

    print(
        f"[SOAR] Incident created: "
        f"{incident_id}"
    )