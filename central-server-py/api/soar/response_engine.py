from elasticsearch import Elasticsearch
from datetime import datetime, timezone

blocked_ips = set()

es = Elasticsearch(
    "http://localhost:9200",
    verify_certs=False,
    request_timeout=30
)

BLOCK_INDEX = "ids-blocked"


def block_ip(ip):

    if not ip:
        return

    if ip not in blocked_ips:

        blocked_ips.add(ip)

        es.index(
            index=BLOCK_INDEX,
            document={

                "src_ip": ip,

                "blocked_at": datetime.now(
                    timezone.utc
                ).isoformat()
            }
        )

        print(
            f"[SOAR] BLOCKED IP: {ip}"
        )


def is_blocked(ip):

    return ip in blocked_ips