import snap7
import time

client = snap7.client.Client()
client.connect(
    address="172.20.1.148",
    rack=0,
    slot=1
)

if client.get_connected():
    print(f"Connected to PLC was sucessfull")
i = 0
while True:
    print("Program state")# Read memory byte 2 (M2.6 is bit 6)
    data = client.read_area(area=snap7.type.Areas.MK,db_number=0,start=2,size=1)
    value = snap7.util.get_bool(data, 0, 6)
    print(f"This is the program state: {value}")
    i += 1
    print(f"Iteration: {i}")
    time.sleep(2)