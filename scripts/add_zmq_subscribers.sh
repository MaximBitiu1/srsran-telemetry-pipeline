#!/bin/bash

# ============================================================
# Open5GS - Add ZMQ UE Subscribers
# Adds UE1 and UE2 required for jrtc-apps ZMQ mode
# ============================================================

OPEN5GS_HOST="${OPEN5GS_HOST:-http://localhost:9999}"
USERNAME="${OPEN5GS_USERNAME:-admin}"
PASSWORD="${OPEN5GS_PASSWORD:-1423}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}============================================${NC}"
echo -e "${YELLOW}  Open5GS - Adding jrtc-apps ZMQ UEs${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
echo "Target: $OPEN5GS_HOST"
echo ""

# ---- Step 1: Login and get token ----
echo -e "${YELLOW}[1/3] Logging in...${NC}"

LOGIN_RESPONSE=$(curl -s -X POST "$OPEN5GS_HOST/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$USERNAME\", \"password\": \"$PASSWORD\"}" \
  -c /tmp/open5gs_cookies.txt \
  -w "\n%{http_code}")

HTTP_CODE=$(echo "$LOGIN_RESPONSE" | tail -1)
BODY=$(echo "$LOGIN_RESPONSE" | head -1)

if [ "$HTTP_CODE" != "200" ]; then
  echo -e "${RED}[ERROR] Login failed (HTTP $HTTP_CODE). Check OPEN5GS_HOST, username, and password.${NC}"
  echo "Response: $BODY"
  exit 1
fi

echo -e "${GREEN}[OK] Login successful.${NC}"
echo ""

# ---- Helper function to add a subscriber ----
add_subscriber() {
  local LABEL=$1
  local IMSI=$2
  local IMEI=$3
  local APN=$4

  echo -e "${YELLOW}[2/3] Adding $LABEL (IMSI: $IMSI)...${NC}"

  PAYLOAD=$(cat <<EOF
{
  "imsi": "$IMSI",
  "msisdn": [],
  "imeisv": "$IMEI",
  "mme_host": [],
  "mme_realm": [],
  "purge_flag": [],
  "security": {
    "k": "465B5CE8B199B49FAA5F0A2EE238A6BC",
    "op": null,
    "opc": "E8ED289DEBA952E4283B54E88E6183CA",
    "amf": "8000",
    "sqn": "000000000000"
  },
  "ambr": {
    "downlink": { "value": 1, "unit": 3 },
    "uplink":   { "value": 1, "unit": 3 }
  },
  "slice": [
    {
      "sst": 1,
      "default_indicator": true,
      "session": [
        {
          "name": "$APN",
          "type": 3,
          "qos": {
            "index": 9,
            "arp": {
              "priority_level": 8,
              "pre_emption_capability": 1,
              "pre_emption_vulnerability": 1
            }
          },
          "ambr": {
            "downlink": { "value": 1, "unit": 3 },
            "uplink":   { "value": 1, "unit": 3 }
          },
          "ue": {
            "addr": "",
            "addr6": ""
          },
          "pcc_rule": []
        }
      ]
    }
  ],
  "access_restriction_data": 32,
  "subscriber_status": 0,
  "network_access_mode": 0,
  "subscribed_rau_tau_timer": 12,
  "devices": []
}
EOF
)

  RESPONSE=$(curl -s -X POST "$OPEN5GS_HOST/api/subscriber" \
    -H "Content-Type: application/json" \
    -b /tmp/open5gs_cookies.txt \
    -d "$PAYLOAD" \
    -w "\n%{http_code}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -1)

  if [ "$HTTP_CODE" == "201" ] || [ "$HTTP_CODE" == "200" ]; then
    echo -e "${GREEN}[OK] $LABEL added successfully.${NC}"
  elif [ "$HTTP_CODE" == "409" ]; then
    echo -e "${YELLOW}[SKIP] $LABEL (IMSI: $IMSI) already exists — skipping.${NC}"
  else
    echo -e "${RED}[ERROR] Failed to add $LABEL (HTTP $HTTP_CODE).${NC}"
    echo "Response: $BODY"
  fi
  echo ""
}

# ---- Add both UEs ----
add_subscriber "UE1" "001010123456780" "353490069873310" "internet"
add_subscriber "UE2" "001010123456781" "353490069873311" "internet"

# ---- Cleanup ----
rm -f /tmp/open5gs_cookies.txt

echo -e "${YELLOW}[3/3] Done.${NC}"
echo ""
echo -e "${GREEN}Both subscribers are now provisioned in Open5GS.${NC}"
echo "You can verify at: $OPEN5GS_HOST"
echo ""
echo -e "${YELLOW}Subscriber credentials used:${NC}"
echo "  K:   465B5CE8B199B49FAA5F0A2EE238A6BC"
echo "  OPc: E8ED289DEBA952E4283B54E88E6183CA"
echo ""
echo -e "${YELLOW}Override defaults with environment variables if needed:${NC}"
echo "  OPEN5GS_HOST=http://<ip>:9999 OPEN5GS_USERNAME=admin OPEN5GS_PASSWORD=1423 ./add_zmq_subscribers.sh"
