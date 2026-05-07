# brute_force_test.py

from kafka import KafkaProducer
import json
import time
import random

# =========================================================
# KAFKA
# =========================================================

producer = KafkaProducer(
    bootstrap_servers='localhost:19092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# =========================================================
# TARGET
# =========================================================

TARGET_USER = "admin"

ATTACKER_IP = "45.133.193.22"

TOTAL_ATTEMPTS = 30

print("🚨 Starting brute force simulation...\n")

# =========================================================
# MAIN LOOP
# =========================================================

for i in range(TOTAL_ATTEMPTS):

    event = {

        "raw":
            f"failed login "
            f"user={TARGET_USER} "
            f"ip={ATTACKER_IP}",

        "agent": {
            "agent_id": "server-1"
        }
    }

    producer.send(
        "ids.events.v1",
        event
    )

    print(
        f"[{i+1}/{TOTAL_ATTEMPTS}] "
        f"failed login | "
        f"user={TARGET_USER} | "
        f"ip={ATTACKER_IP}"
    )

    # =====================================================
    # FAST ATTACK RATE
    # =====================================================

    time.sleep(
        random.uniform(0.08, 0.25)
    )

# =========================================================
# FLUSH
# =========================================================

producer.flush()

print("\n✅ Brute force attack simulation completed")