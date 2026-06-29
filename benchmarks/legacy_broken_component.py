# Broken Architectural Component
# Issue: The component uses a synchronous, blocking network call inside a performance-critical loop, 
# and it lacks proper error handling for network timeouts. This causes severe latency spikes.
# Task: Refactor this into an asynchronous implementation using 'httpx' or 'aiohttp' and add a retry mechanism.

import time
import requests

def fetch_data(url: str):
    # Performance-critical loop simulating data processing
    for i in range(10):
        print(f"Processing item {i}")
        # The high-level architectural issue: Blocking IO
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        print(f"Got data: {response.json()}")
        time.sleep(0.1)

if __name__ == "__main__":
    fetch_data("https://jsonplaceholder.typicode.com/posts/1")
