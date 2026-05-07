# spraying_test.py

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
# ATTACKER INFRA
# =========================================================

attacker_ips = [
    "185.220.101.1",
    "185.220.101.2"
]

# =========================================================
# TARGET USERS
# =========================================================

users = [
    "admin",
    "john",
    "oracle",
    "root",
    "test",
    "guest",
    "david",
    "emma",
    "mike",
    "alice",
    "finance",
    "developer",
    "backup",
    "support",
    "intern"
]

# =========================================================
# CONFIG
# =========================================================

TOTAL_ROUNDS = 3

print("🚨 Starting password spraying simulation...\n")

# =========================================================
# MAIN LOOP
# =========================================================

counter = 0

for round_num in range(TOTAL_ROUNDS):

    print(f"\n===== ROUND {round_num + 1} =====\n")

    for user in users:

        counter += 1

        ip = random.choice(attacker_ips)

        event = {

            "raw":
                f"failed login "
                f"user={user} "
                f"ip={ip}",

            "agent": {
                "agent_id": "server-1"
            }
        }

        producer.send(
            "ids.events.v1",
            event
        )

        print(
            f"[{counter}] "
            f"spray attempt | "
            f"user={user} | "
            f"ip={ip}"
        )

        # =================================================
        # LOW & SLOW SPRAYING
        # =================================================

        time.sleep(
            random.uniform(1.0, 2.5)
        )

# =========================================================
# FLUSH
# =========================================================

producer.flush()

print("\n✅ Password spraying simulation completed")