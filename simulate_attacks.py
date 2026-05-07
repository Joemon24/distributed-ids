import json
import random
import sys
import time
from datetime import datetime, timezone

from kafka import KafkaProducer

# =========================================================
# CONFIG
# =========================================================

KAFKA_BROKERS = ["localhost:19092"]
TOPIC = "ids.events.v1"

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

# =========================================================
# HELPERS
# =========================================================

users = [
    "alice",
    "bob",
    "charlie",
    "david",
    "eve",
    "frank",
    "admin",
    "root",
    "testuser",
    "finance",
    "hr",
    "devops",
]

ips = [
    "192.168.1.10",
    "192.168.1.11",
    "192.168.1.12",
    "192.168.1.13",
    "10.0.0.5",
    "10.0.0.6",
    "172.16.1.5",
    "172.16.1.6",
]

agents = [
    "agent-1",
    "agent-2",
    "agent-3",
]


def send_event(raw):

    event = {
        "agent": {
            "agent_id": random.choice(agents)
        },
        "raw": raw,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    producer.send(TOPIC, event)


# =========================================================
# NORMAL TRAFFIC
# =========================================================


def normal_mode():

    print("🚀 Running NORMAL traffic...")

    while True:

        user = random.choice(users)
        ip = random.choice(ips)

        success = random.random() < 0.92

        if success:
            raw = (
                f"login success "
                f"user={user} "
                f"ip={ip}"
            )
        else:
            raw = (
                f"login failed "
                f"user={user} "
                f"ip={ip}"
            )

        send_event(raw)

        print(raw)

        time.sleep(random.uniform(0.5, 2))


# =========================================================
# BRUTE FORCE
# =========================================================


def brute_force_mode():

    print("🔥 Running BRUTE FORCE attack...")

    target_user = "admin"
    attacker_ip = "203.0.113.10"

    while True:

        raw = (
            f"login failed "
            f"user={target_user} "
            f"ip={attacker_ip}"
        )

        send_event(raw)

        print(raw)

        time.sleep(0.15)


# =========================================================
# PASSWORD SPRAYING
# =========================================================


def spraying_mode():

    print("⚠️ Running PASSWORD SPRAYING attack...")

    attacker_ip = "198.51.100.25"

    while True:

        user = random.choice(users)

        raw = (
            f"login failed "
            f"user={user} "
            f"ip={attacker_ip}"
        )

        send_event(raw)

        print(raw)

        time.sleep(0.25)


# =========================================================
# LATERAL MOVEMENT
# =========================================================


def lateral_mode():

    print("🚨 Running LATERAL MOVEMENT simulation...")

    user = "admin"

    while True:

        ip = f"10.0.0.{random.randint(1,40)}"

        raw = (
            f"login success "
            f"user={user} "
            f"ip={ip}"
        )

        send_event(raw)

        print(raw)

        time.sleep(0.20)


# =========================================================
# MIXED ATTACK MODE
# =========================================================


def mixed_mode():

    print("💀 Running MIXED ATTACK simulation...")

    attacker_ip = "45.67.23.99"

    while True:

        mode = random.choice([
            "normal",
            "brute",
            "spray",
            "lateral"
        ])

        # =====================================================
        # NORMAL
        # =====================================================

        if mode == "normal":

            user = random.choice(users)
            ip = random.choice(ips)

            raw = (
                f"login success "
                f"user={user} "
                f"ip={ip}"
            )

        # =====================================================
        # BRUTE FORCE
        # =====================================================

        elif mode == "brute":

            raw = (
                f"login failed "
                f"user=admin "
                f"ip={attacker_ip}"
            )

        # =====================================================
        # SPRAYING
        # =====================================================

        elif mode == "spray":

            user = random.choice(users)

            raw = (
                f"login failed "
                f"user={user} "
                f"ip={attacker_ip}"
            )

        # =====================================================
        # LATERAL
        # =====================================================

        else:

            ip = f"10.0.0.{random.randint(1,60)}"

            raw = (
                f"login success "
                f"user=admin "
                f"ip={ip}"
            )

        send_event(raw)

        print(raw)

        time.sleep(0.20)


# =========================================================
# MAIN
# =========================================================

if len(sys.argv) < 2:

    print(
        "Usage:\n"
        "python3 simulate_attacks.py normal\n"
        "python3 simulate_attacks.py brute_force\n"
        "python3 simulate_attacks.py spraying\n"
        "python3 simulate_attacks.py lateral\n"
        "python3 simulate_attacks.py mixed"
    )

    sys.exit(1)

mode = sys.argv[1]

if mode == "normal":
    normal_mode()

elif mode == "brute_force":
    brute_force_mode()

elif mode == "spraying":
    spraying_mode()

elif mode == "lateral":
    lateral_mode()

elif mode == "mixed":
    mixed_mode()

else:
    print("❌ Invalid mode")
