import requests
import json
import sseclient  # pip install sseclient-py

BASE_URL = "http://localhost:8000"


def listen_to_stream(thread_id):
    """
    Listens to SSE stream.
    Returns: 'plan_updated' if a new plan comes in, 'finished' if report runs.
    """
    url = f"{BASE_URL}/stream/{thread_id}"
    headers = {"Accept": "text/event-stream"}
    response = requests.get(url, stream=True, headers=headers)
    client = sseclient.SSEClient(response)

    print("\n--- INCOMING STREAM ---\n")

    status = "running"


    for event in client.events():
        try:
            payload = json.loads(event.data)
            msg_type = payload.get("type")

            if msg_type == "status":
                print(f"   [STATUS] {payload['content']}")

            elif msg_type == "token":
                print(payload["content"], end="", flush=True)

            elif msg_type == "plan":
                print("\n\n📋 **UPDATED PLAN GENERATED**:")
                # Handle both full plan dict or list of tasks
                content = payload.get("content", {})
                tasks = content.get("tasks", []) if isinstance(content, dict) else []

                for t in tasks:
                    name = t.get("name", "Unknown Task")
                    print(f"   - {name}")
                status = "plan_updated"

            elif msg_type == "approved":
                print("\n✅ Plan approved. Proceeding to execution...")
                # Continue listening for executor/reporter events - don't break yet
                status = "approved"

            elif msg_type == "report":
                print("\n\n" + "=" * 30)
                print(" FINAL REPORT ")
                print("=" * 30 + "\n")
                print(payload["content"])
                print("\n" + "=" * 30 + "\n")
                status = "finished"
                # Continue to wait for "complete" event

            elif msg_type == "complete":
                print("\n✅ Stream Finished.")
                # If we were in "approved" state, execution completed successfully
                if status == "approved":
                    status = "finished"
                break

            elif msg_type == "error":
                print(f"\n❌ Error: {payload['content']}")
                status = "error"
                break

        except Exception as e:
            # print(f"Error parsing event: {e}")
            pass

    return status


def test_investigator():
    topic = "Real Asset Tokenization"
    print(f"1. 🚀 Starting research on: {topic}")

    # 1. Start
    res = requests.post(
        f"{BASE_URL}/start", json={"topic": topic, "model": "gpt-4.1-mini"}
    )
    data = res.json()
    thread_id = data["thread_id"]
    plan = data["plan"]

    print(f"   🆔 Thread ID: {thread_id}")
    print("\n📋 INITIAL PLAN:")
    for t in plan.get("tasks", []):
        print(f"   - {t.get('name', 'Task')}")

    # 2. Feedback Loop
    while True:
        print("\n👇 Action:")
        print("   [Enter] to Approve & Execute")
        print("   [Type text] to Modify Plan (e.g. 'Add competitor X')")
        feedback = input("   > ").strip()

        if not feedback:
            feedback = "Approved"

        # Send Feedback/Approval
        print(f"   📡 Sending: '{feedback}'...")
        requests.post(
            f"{BASE_URL}/approve", json={"thread_id": thread_id, "feedback": feedback}
        )

        # Listen to stream
        result_status = listen_to_stream(thread_id)

        if result_status == "plan_updated":
            # If we got a new plan, loop back to ask user again
            print("\n🔄 Plan was updated based on your feedback. Please Review.")
            continue
        elif result_status in ["approved", "finished"]:
            # Plan was approved and execution completed, or we got the final report
            print("\n👋 Research Session Ended.")
            break
        else:
            # If we got an error or unknown status, exit
            print("\n👋 Research Session Ended.")
            break


if __name__ == "__main__":
    test_investigator()
