# Webhook testing — run these AFTER starting your local server:
#   uvicorn main:app --reload
#
# Replace YOUR_TEST_WHATSAPP_NUMBER below with the exact number stored in
# your test user's whatsapp_number column (digits only, no +, no spaces).

# --- Test 1: webhook verification (GET) ---
# Simulates Meta's one-time handshake when you register the webhook URL.
# Set WHATSAPP_VERIFY_TOKEN in your .env first, e.g. WHATSAPP_VERIFY_TOKEN=nudge123
curl "http://localhost:8000/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=nudge123&hub.challenge=test_challenge_123"
# Expected: returns "test_challenge_123" as plain text, status 200

# --- Test 2: inbound message with a check-in keyword (POST) ---
# Simulates the exact JSON shape Meta sends when a user replies "Done ✅"
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "YOUR_TEST_WHATSAPP_NUMBER",
            "text": { "body": "Done ✅" }
          }]
        }
      }]
    }]
  }'
# Expected: {"status": "ok"}
# Then check Supabase check_ins table — should have a new row with matched=true

# --- Test 3: inbound message that does NOT match a check-in keyword ---
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "YOUR_TEST_WHATSAPP_NUMBER",
            "text": { "body": "hey what time does this come" }
          }]
        }
      }]
    }]
  }'
# Expected: {"status": "ok"}, new row in check_ins with matched=false

# --- Test 4: message from an unknown number (not in your users table) ---
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "911111111111",
            "text": { "body": "done" }
          }]
        }
      }]
    }]
  }'
# Expected: {"status": "ok"}, NO new row in check_ins (unknown number is skipped)

# --- Test 5: status update payload (not a message) ---
# Meta also sends delivery/read receipts to the same webhook — confirm these don't break anything
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "statuses": [{ "status": "delivered" }]
        }
      }]
    }]
  }'
# Expected: {"status": "ignored"}, no error

# --- Test 6: streak endpoint ---
curl "http://localhost:8000/check-ins/YOUR_TEST_EMAIL/streak"
# Expected: {"email": "...", "streak": N}
