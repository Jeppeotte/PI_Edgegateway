import valkey

valkey_client = valkey.Valkey(host="localhost", port=6379)

pubsub = valkey_client.pubsub()

    # Subscribes to all device data from the different device_ids which the node might have
pubsub.psubscribe("*")

for message in pubsub.listen():
    print(message)
    print(message['channel'].decode('utf-8'))