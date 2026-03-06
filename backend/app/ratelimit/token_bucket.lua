-- Atomic token bucket.
-- Keys:
--   KEYS[1] = bucket key
-- Args:
--   ARGV[1] = now_ms
--   ARGV[2] = capacity
--   ARGV[3] = refill_per_ms
--   ARGV[4] = cost

local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_per_ms = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

-- Stored as two fields in a hash:
-- tokens: current tokens
-- ts: last refill timestamp ms
local data = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(data[1])
local ts = tonumber(data[2])

if tokens == nil then tokens = capacity end
if ts == nil then ts = now end

-- Refill
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end

tokens = math.min(capacity, tokens + (elapsed * refill_per_ms))
ts = now

local allowed = 0
local remaining = tokens
local retry_after_ms = 0

if tokens >= cost then
  allowed = 1
  tokens = tokens - cost
  remaining = tokens
else
  allowed = 0
  remaining = tokens
  local missing = cost - tokens
  if refill_per_ms > 0 then
    retry_after_ms = math.ceil(missing / refill_per_ms)
  else
    retry_after_ms = 0
  end
end

-- Persist + set TTL so keys expire when idle.
-- TTL: enough for bucket to refill fully (2x for safety)
local ttl_ms = math.ceil((capacity / refill_per_ms) * 2)
if ttl_ms < 1000 then ttl_ms = 1000 end

redis.call("HSET", key, "tokens", tokens, "ts", ts)
redis.call("PEXPIRE", key, ttl_ms)

return {allowed, remaining, retry_after_ms}