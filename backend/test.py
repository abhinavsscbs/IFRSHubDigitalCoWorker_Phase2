import redis

def test_redis_connection():
    try:
        # Connect to Redis (default: localhost:6379)
        r = redis.Redis(
            host='localhost',
            port=50058,
            db=0,
            decode_responses=True  # ensures strings instead of bytes
        )

        # Ping test
        if r.ping():
            print("✅ Connected to Redis successfully")

        # Set a test key
        r.set("test_key", "Hello Redis")

        # Get the value
        value = r.get("test_key")
        print(f"🔹 Retrieved value: {value}")

        # Delete key (cleanup)
        r.delete("test_key")
        print("🧹 Cleanup done")

    except redis.ConnectionError as e:
        print("❌ Could not connect to Redis")
        print(f"Error: {e}")

if __name__ == "__main__":
    test_redis_connection()