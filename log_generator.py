import time
import random

LOG_FILE = "/tmp/auth.log"

USERS = ["admin", "root", "user1", "dev", "guest"]

NORMAL_IPS = [f"192.168.1.{i}" for i in range(2, 50)]

# Attack IP pools
BRUTE_IP = "10.0.0.99"
SPRAY_IPS = [f"10.0.1.{i}" for i in range(10, 40)]

# =========================
# WRITE
# =========================

def write(line):
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# =========================
# NORMAL
# =========================

def normal_event(success_rate=0.95):
    user = random.choice(USERS)
    ip = random.choice(NORMAL_IPS)

    if random.random() < success_rate:
        return f"auth success user={user} ip={ip}"
    else:
        return f"auth failure user={user} ip={ip}"

# =========================
# ATTACK TYPES
# =========================

# 1. brute force (same IP)
def brute_force():
    user = random.choice(["admin", "root"])
    return f"auth failure user={user} ip={BRUTE_IP}"

# 2. password spray (many IPs)
def password_spray():
    user = random.choice(["admin", "root"])
    ip = random.choice(SPRAY_IPS)
    return f"auth failure user={user} ip={ip}"

# 3. stealth attack (low rate)
def stealth_attack():
    user = random.choice(["admin", "root"])
    ip = random.choice(SPRAY_IPS)

    # mostly normal, occasional fail
    if random.random() < 0.8:
        return f"auth success user={user} ip={ip}"
    else:
        return f"auth failure user={user} ip={ip}"

# =========================
# START
# =========================

print("Starting controlled log generator...")

# =========================
# PHASE 1 — CLEAN NORMAL (TRAIN)
# =========================
print("Phase 1: NORMAL")

for _ in range(120):
    write(normal_event(success_rate=0.97))
    time.sleep(0.15)

# =========================
# PHASE 2 — NOISY NORMAL
# =========================
print("Phase 2: NOISY")

for _ in range(80):
    write(normal_event(success_rate=0.8))
    time.sleep(0.15)

# =========================
# PHASE 3 — ATTACK WAVE 1 (BRUTE FORCE)
# =========================
print("Phase 3: BRUTE FORCE")

for _ in range(60):
    if random.random() < 0.85:
        write(brute_force())
    else:
        write(normal_event(0.7))
    time.sleep(0.1)

# =========================
# PHASE 4 — ATTACK WAVE 2 (SPRAY)
# =========================
print("Phase 4: PASSWORD SPRAY")

for _ in range(60):
    if random.random() < 0.85:
        write(password_spray())
    else:
        write(normal_event(0.7))
    time.sleep(0.1)

# =========================
# PHASE 5 — STEALTH ATTACK
# =========================
print("Phase 5: STEALTH")

for _ in range(80):
    write(stealth_attack())
    time.sleep(0.2)

print("Done")