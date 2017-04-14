import sys
from node import *

node_init("127.0.0.1", int(input("Port: ")))
try:
    while True:
        process_input()
except KeyboardInterrupt:
    node_deinit()
except EOFError:
    node_deinit()
except:
    node_deinit()
    raise
