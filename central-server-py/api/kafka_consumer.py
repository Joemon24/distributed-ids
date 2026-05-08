# =========================================================
# IMPORTS
# =========================================================

import json
import random
import re
import os
import joblib
import numpy as np

from datetime import datetime, timedelta, timezone
from collections import deque, defaultdict, Counter

from kafka import KafkaConsumer
from elasticsearch import Elasticsearch, helpers

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# =========================================================
# SOAR IMPORTS
# =========================================================

from api.soar.alert_manager import create_alert

from api.soar.incident_manager import (
    create_incident
)

from api.soar.response_engine import (
    block_ip,
    is_blocked
)

from api.soar.notifier import (
    send_notification
)
# =========================================================
# SOAR
# =========================================================

def trigger_soar(event):

    try:

        create_alert(event)

        create_incident(event)

        block_ip(
            event.get("src_ip")
        )

        send_notification(event)

    except Exception as e:

        print(
            f"[SOAR ERROR] {e}"
        )

# =========================================================
# CONFIG
# =========================================================

KAFKA_BROKERS = ["localhost:19092"]

TOPIC = "ids.events.v1"

GROUP_ID = "central-server-final-v31"

ES_HOST = "http://localhost:9200"

ES_INDEX = "ids-events"

MODEL_PATH = "models/isolation_forest.pkl"

SCALER_PATH = "models/scaler.pkl"

TRAINING_DATA_PATH = "models/training_data.pkl"

# =========================================================
# ELASTICSEARCH
# =========================================================

es = Elasticsearch(
    ES_HOST,
    verify_certs=False,
    request_timeout=30
)

bulk_buffer = []

BULK_SIZE = 100

# =========================================================
# MODEL
# =========================================================

scaler = StandardScaler()

model = IsolationForest(
    n_estimators=300,
    contamination=0.02,
    random_state=42
)

training_data = []

model_trained = False

TRAINING_LIMIT = 500

# =========================================================
# WINDOWS
# =========================================================

WINDOW_5M = timedelta(minutes=5)

WINDOW_1M = timedelta(minutes=1)

# =========================================================
# STATE
# =========================================================

user_history = {}

ip_history = {}

fail_streak = defaultdict(int)

trust_scores = defaultdict(lambda: 1.0)

MAX_HISTORY_KEYS = 10000

# =========================================================
# MODEL DIRECTORY
# =========================================================

os.makedirs("models", exist_ok=True)

# =========================================================
# LOAD TRAINING DATA
# =========================================================

if os.path.exists(TRAINING_DATA_PATH):

    try:

        training_data = joblib.load(
            TRAINING_DATA_PATH
        )

        print(
            f"✅ Loaded training data: "
            f"{len(training_data)} samples"
        )

    except Exception as e:

        print(
            f"❌ Failed loading training data: {e}"
        )

# =========================================================
# LOAD MODEL
# =========================================================

if (
    os.path.exists(MODEL_PATH)
    and os.path.exists(SCALER_PATH)
):

    try:

        model = joblib.load(MODEL_PATH)

        scaler = joblib.load(SCALER_PATH)

        model_trained = True

        print("✅ Loaded trained model")

    except Exception as e:

        print(
            f"❌ Failed loading model: {e}"
        )

# =========================================================
# HELPERS
# =========================================================

def safe_div(a, b):

    return round(a / max(b, 1), 2)

# =========================================================
# PARSERS
# =========================================================

def extract_ip(event):

    raw = event.get("raw", "")

    match = re.search(r'ip=([\d\.]+)', raw)

    if match:
        return match.group(1)

    return f"10.0.0.{random.randint(10,20)}"


def extract_user(event):

    raw = event.get("raw", "")

    match = re.search(r'user=([\w\-]+)', raw)

    if match:
        return match.group(1)

    return f"user{random.randint(1,10)}"


def extract_outcome(event):

    raw = event.get("raw", "").lower()

    if "failed" in raw or "failure" in raw:
        return "failure"

    if "success" in raw or "accepted" in raw:
        return "success"

    return "success"

# =========================================================
# FEATURE ENGINE
# =========================================================

def compute_features(event, now):

    agent_id = event["agent"]["agent_id"]

    ip = extract_ip(event)

    user = extract_user(event)

    outcome = extract_outcome(event)

    # =====================================================
    # USER HISTORY
    # =====================================================

    user_key = f"{agent_id}:{user}"

    if user_key not in user_history:
        user_history[user_key] = deque()

    u_history = user_history[user_key]

    u_history.append((now, ip, outcome))

    while (
        u_history
        and u_history[0][0] < now - WINDOW_5M
    ):
        u_history.popleft()

    # =====================================================
    # IP HISTORY
    # =====================================================

    ip_key = f"{agent_id}:{ip}"

    if ip_key not in ip_history:
        ip_history[ip_key] = deque()

    i_history = ip_history[ip_key]

    i_history.append((now, user, outcome))

    while (
        i_history
        and i_history[0][0] < now - WINDOW_5M
    ):
        i_history.popleft()

    # =====================================================
    # FAIL STREAK
    # =====================================================

    if outcome == "failure":
        fail_streak[user_key] += 1
    else:
        fail_streak[user_key] = 0

    # =====================================================
    # USER FEATURES
    # =====================================================

    failed_auth_count_5m = sum(
        1 for _, _, o in u_history
        if o == "failure"
    )

    event_rate_1m = sum(
        1 for ts, _, _ in u_history
        if ts >= now - WINDOW_1M
    )

    failed_ratio = safe_div(
        failed_auth_count_5m,
        len(u_history)
    )

    ips = [ip for _, ip, _ in u_history]

    ip_counts = Counter(ips)

    top_ip_count = (
        ip_counts.most_common(1)[0][1]
        if ip_counts else 0
    )

    dominance_ratio = safe_div(
        top_ip_count,
        len(u_history)
    )

    unique_ips = len(set(ips))

    # =====================================================
    # IP FEATURES
    # =====================================================

    unique_users = len(set(
        user for _, user, _ in i_history
    ))

    ip_failures = sum(
        1 for _, _, o in i_history
        if o == "failure"
    )

    ip_failed_ratio = safe_div(
        ip_failures,
        len(i_history)
    )

    ip_rate_1m = sum(
        1 for ts, _, _ in i_history
        if ts >= now - WINDOW_1M
    )

    hour_of_day = now.hour

    return {

        "failed_auth_count_5m":
            failed_auth_count_5m,

        "event_rate_1m":
            event_rate_1m,

        "failed_ratio":
            failed_ratio,

        "fail_streak":
            fail_streak[user_key],

        "dominance_ratio":
            dominance_ratio,

        "unique_ips":
            unique_ips,

        "unique_users":
            unique_users,

        "ip_failed_ratio":
            ip_failed_ratio,

        "ip_rate_1m":
            ip_rate_1m,

        "hour_of_day":
            hour_of_day,
    }

# =========================================================
# VECTOR
# =========================================================

def extract_vector(f):

    return [

        f["failed_ratio"],

        min(f["fail_streak"] / 20, 1),

        min(f["event_rate_1m"] / 200, 1),

        f["dominance_ratio"],

        min(f["unique_ips"] / 20, 1),

        min(f["unique_users"] / 20, 1),

        f["ip_failed_ratio"],

        min(f["ip_rate_1m"] / 200, 1),

        min(f["hour_of_day"] / 24, 1),
    ]

# =========================================================
# TRUST ENGINE
# =========================================================

def update_trust_score(
    current_trust,
    features,
    anomaly_score,
    outcome,
    alert_type
):

    trust = current_trust

    if (
        outcome == "success"
        and anomaly_score < 0.20
        and features["failed_ratio"] < 0.10
    ):
        trust += 0.03
    if (

    outcome == "success"

    and anomaly_score < 0.10

    and features["fail_streak"] == 0

):

        trust += 0.05

    if outcome == "failure":

        if features["failed_auth_count_5m"] <= 2:
            trust -= 0.01
        else:
            trust -= 0.05

    if features["fail_streak"] >= 5:
        trust -= 0.08

    if features["fail_streak"] >= 10:
        trust -= 0.15

    if anomaly_score > 0.50:
        trust -= 0.10

    if anomaly_score > 0.75:
        trust -= 0.15

    if alert_type == "password_spraying":
        trust -= 0.20

    elif alert_type == "brute_force":
        trust -= 0.30

    elif alert_type == "lateral_movement":
        trust -= 0.20

    trust = np.clip(trust, 0.0, 1.0)

    return round(float(trust), 2)

# =========================================================
# KAFKA CONSUMER
# =========================================================

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BROKERS,
    group_id=GROUP_ID,
    auto_offset_reset="latest",
    enable_auto_commit=True,
    value_deserializer=lambda v: json.loads(
        v.decode("utf-8")
    ),
)

print("🚀 Consumer started...")

# =========================================================
# MAIN LOOP
# =========================================================

try:

    for msg in consumer:

        payload = msg.value

        if not isinstance(payload, list):
            payload = [payload]

        for event in payload:

            try:

                now = datetime.now(timezone.utc)

                if "agent" not in event:

                    event["agent"] = {
                        "agent_id": "default"
                    }

                # =================================================
                # CLEANUP
                # =================================================

                if len(user_history) > MAX_HISTORY_KEYS:

                    oldest_keys = list(
                        user_history.keys()
                    )[:1000]

                    for key in oldest_keys:
                        user_history.pop(key, None)

                if len(ip_history) > MAX_HISTORY_KEYS:

                    oldest_keys = list(
                        ip_history.keys()
                    )[:1000]

                    for key in oldest_keys:
                        ip_history.pop(key, None)

                # =================================================
                # FEATURES
                # =================================================

                features = compute_features(
                    event,
                    now
                )

                event["src_ip"] = extract_ip(event)

                # =================================================
                # BLOCKED IP CHECK
                # =================================================

                if is_blocked(event["src_ip"]):

                    print(
                        f"[SOAR] Ignoring blocked IP "
                        f"{event['src_ip']}"
                    )

                    continue

                event["username"] = extract_user(event)

                event["outcome"] = extract_outcome(event)

                event["features"] = features

                vector = extract_vector(features)

                # =================================================
                # MODEL
                # =================================================

                if not model_trained:

                    anomaly_score = 0.0

                else:

                    X = scaler.transform([vector])

                    score = model.decision_function(
                        X
                    )[0]

                    base_score = float(
                        np.clip(
                            -score * 1.8,
                            0,
                            1
                        )
                    )

                    if (
                        features["fail_streak"] <= 2
                        and features["failed_ratio"] < 0.60
                    ):
                        base_score *= 0.30

                    if (
                        features["event_rate_1m"] <= 3
                        and features["ip_rate_1m"] <= 3
                    ):
                        base_score *= 0.50

                    anomaly_score = round(
                        min(base_score, 1.0),
                        2
                    )

                # =================================================
                # BOOSTS
                # =================================================

                boost = 0

                if features["fail_streak"] >= 5:
                    boost += 0.10

                if features["fail_streak"] >= 10:
                    boost += 0.20

                if (
                    features["failed_ratio"] > 0.30
                    and features["failed_auth_count_5m"] >= 3
                ):
                    boost += 0.10

                if (
                    features["failed_ratio"] > 0.60
                    and features["failed_auth_count_5m"] >= 5
                ):
                    boost += 0.20

                if (
                    features["unique_users"] >= 6
                    and features["ip_failed_ratio"] > 0.50
                    and features["ip_rate_1m"] >= 6
                ):
                    boost += 0.40

                if (
                    features["unique_ips"] >= 6
                    and features["event_rate_1m"] > 12
                ):
                    boost += 0.30

                anomaly_score = round(
                    min(anomaly_score + boost, 1.0),
                    2
                )

                # =================================================
                # ALERT TYPES
                # =================================================

                alert_type = "normal"

                if (
                    features["fail_streak"] >= 5
                    and features["failed_auth_count_5m"] >= 5
                    and features["failed_ratio"] > 0.50
                ):
                    alert_type = "brute_force"

                elif (
                    features["unique_users"] >= 6
                    and features["ip_failed_ratio"] > 0.50
                    and features["ip_rate_1m"] >= 6
                ):
                    alert_type = "password_spraying"

                elif (
                    features["unique_ips"] >= 6
                    and features["event_rate_1m"] > 12
                    and anomaly_score > 0.45
                ):
                    alert_type = "lateral_movement"

                elif (
                    anomaly_score > 0.70
                ):
                    alert_type = "anomaly"

                # =================================================
                # SEVERITY
                # =================================================

                if anomaly_score >= 0.85:
                    severity = "critical"

                elif anomaly_score >= 0.60:
                    severity = "high"

                elif anomaly_score >= 0.35:
                    severity = "medium"

                else:
                    severity = "low"

                # =================================================
                # MITRE
                # =================================================

                mitre_mapping = {

                    "brute_force":
                        "T1110",

                    "password_spraying":
                        "T1110.003",

                    "lateral_movement":
                        "TA0008",

                    "anomaly":
                        "T1078"
                }

                mitre_technique = mitre_mapping.get(
                    alert_type,
                    "none"
                )

                # =================================================
                # TRUST
                # =================================================

                trust_key = (
                    f"{event['agent']['agent_id']}:"
                    f"{event['username']}"
                )

                current_trust = trust_scores[
                    trust_key
                ]

                updated_trust = update_trust_score(
                    current_trust,
                    features,
                    anomaly_score,
                    event["outcome"],
                    alert_type
                )

                trust_scores[
                    trust_key
                ] = updated_trust

                # =================================================
                # RISK
                # =================================================

                event["risk"] = {

                    "anomaly_score":
                        anomaly_score,

                    "trust_score":
                        updated_trust,

                    "alert_type":
                        alert_type,

                    "severity":
                        severity,

                    "mitre_technique":
                        mitre_technique,
                }

                # =================================================
                # SOAR EVENT DATA
                # =================================================

                event["alert_type"] = alert_type

                event["severity"] = severity

                event["mitre_technique"] = (
                    mitre_technique
                )

                event["anomaly_score"] = (
                    anomaly_score
                )

                event["trust_score"] = (
                    updated_trust
                )

                # =================================================
                # SOAR EXECUTION
                # =================================================

                if severity in ["high", "critical"]:

                    trigger_soar(event)

                # =================================================
                # TIMESTAMP
                # =================================================

                event["@timestamp"] = (
                    now.isoformat()
                )

                # =================================================
                # OUTPUT
                # =================================================

                print(
                    f"🚨 "
                    f"A={anomaly_score:.2f} | "
                    f"T={updated_trust:.2f} | "
                    f"S={severity} | "
                    f"Type={alert_type} | "
                    f"MITRE={mitre_technique}"
                )

                # =================================================
                # ELASTICSEARCH
                # =================================================

                bulk_buffer.append({

                    "_index": ES_INDEX,

                    "_source": event
                })

                if len(bulk_buffer) >= BULK_SIZE:

                    helpers.bulk(
                        es,
                        bulk_buffer
                    )

                    print(
                        f"📦 Bulk inserted "
                        f"{len(bulk_buffer)}"
                    )

                    bulk_buffer.clear()

            except Exception as e:

                print("❌ Error:", e)

except KeyboardInterrupt:

    print("\n🛑 Stopping consumer...")

finally:

    if bulk_buffer:

        helpers.bulk(
            es,
            bulk_buffer
        )

        print(
            f"📦 Final flush: "
            f"{len(bulk_buffer)} events"
        )

    consumer.close()

    print("✅ Consumer closed")