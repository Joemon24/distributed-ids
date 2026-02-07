import json
from datetime import datetime, timedelta
from collections import deque, defaultdict

from kafka import KafkaConsumer
from elasticsearch import Elasticsearch

# =========================================================
# CONFIG
# =========================================================

KAFKA_BROKERS = ["localhost:19092"]
TOPIC = "ids.events.v1"
GROUP_ID = "central-server"

ES_HOST = "http://localhost:9200"
ES_INDEX = "ids-events"

# =========================================================
# ELASTICSEARCH CLIENT (ES 8.x SAFE)
# =========================================================

es = Elasticsearch(
    ES_HOST,
    verify_certs=False,        # dev only
    request_timeout=10,
)

try:
    info = es.info()
    print("🟢 Connected to Elasticsearch")
    print(f"   Cluster: {info['cluster_name']}")
except Exception as e:
    raise RuntimeError(f"❌ Elasticsearch not reachable: {e}")

# =========================================================
# FEATURE STATE (IN-MEMORY)
# =========================================================

WINDOW_5M = timedelta(minutes=5)
WINDOW_1M = timedelta(minutes=1)

event_history = deque()                 # (timestamp, event)
last_heartbeat_time = {}                # agent_id -> datetime

# =========================================================
# FEATURE COMPUTATION
# =========================================================

def compute_features(event: dict, now: datetime) -> dict:
    agent_id = event["agent"]["agent_id"]

    # ---- Maintain sliding window ----
    event_history.append((now, event))

    while event_history and event_history[0][0] < now - WINDOW_5M:
        event_history.popleft()

    # ---- Feature 1: failed auth count (5 min) ----
    failed_auth_count_5m = sum(
        1 for ts, e in event_history
        if e["event"]["category"] == "auth"
        and e["event"]["outcome"] == "failure"
        and ts >= now - WINDOW_5M
    )

    # ---- Feature 2: event rate (1 min) ----
    event_rate_1m = sum(
        1 for ts, _ in event_history
        if ts >= now - WINDOW_1M
    )

    # ---- Feature 3: heartbeat gap ----
    heartbeat_gap_seconds = None
    if event["event"]["type"] == "heartbeat":
        prev = last_heartbeat_time.get(agent_id)
        if prev:
            heartbeat_gap_seconds = (now - prev).total_seconds()
        last_heartbeat_time[agent_id] = now

    return {
        "failed_auth_count_5m": failed_auth_count_5m,
        "event_rate_1m": event_rate_1m,
        "heartbeat_gap_seconds": heartbeat_gap_seconds,
    }

# =========================================================
# KAFKA CONSUMER
# =========================================================

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BROKERS,
    group_id=GROUP_ID,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
)

print("🟢 Central Server Kafka Consumer started")
print(f"🔗 Brokers: {KAFKA_BROKERS}")
print(f"📥 Topic: {TOPIC}")
print(f"📦 Index: {ES_INDEX}")

# =========================================================
# CONSUME LOOP
# =========================================================

for msg in consumer:
    payload = msg.value

    # Agent sends batches
    if not isinstance(payload, list):
        payload = [payload]

    indexed = 0

    for event in payload:
        try:
            now = datetime.utcnow()

            # ---------- FEATURE MATERIALIZATION ----------
            features = compute_features(event, now)
            event["features"] = features

            es.index(
                index=ES_INDEX,
                document=event,
            )

            indexed += 1

        except Exception as e:
            print("❌ Elasticsearch index failed:", e)

    print(
        f"✅ Indexed {indexed} events | "
        f"partition={msg.partition} offset={msg.offset}"
    )