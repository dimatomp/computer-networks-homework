import sys
import struct
from select import select
from socket import *
from messages import *


MCAST_GRP = "224.0.0.1"
MCAST_PORT = 5000
messageId = 0

def address_to_str(addr: tuple):
    return addr[0] + ':' + str(addr[1])

def send_message(message: Message, recipient=None):
    global messageId
    message.messageId = messageId
    messageId += 1
    if recipient is None:
        sock.sendto(message.serialize(), (MCAST_GRP, MCAST_PORT))
    else:
        sock.sendto(message.serialize(), recipient)

# Purchase state flow on buyer:
#  - none -> pending                    (user request)
#  - pending -> done                    (when seller sends response)
# 
# On seller: 
#  - none -> unconfirmedPurchasesSeller (when request is reached)
#  - unconfirmedPurchasesSeller -> done (when client confirms)
#
# On third party:
#  - none -> unconfirmedPurchasesSeller (when seller sends response)
#  - none -> unconfirmedPurchasesBuyer  (when buyer sends response)
#  - unconfirmedPurchasesSeller -> done (when buyer sends response)
#  - unconfirmedPurchasesBuyer -> done  (when seller sends response)
usersData = {}                  # (wallet, file costs)
pendingPurchases = {}           # (name, cost, seller)
unconfirmedPurchasesSeller = {} # (file name, cost, buyer)
unconfirmedPurchasesBuyer = {}  # (file name, cost, seller)

def node_init(nodeAddr: str, nodePort: int):
    global sock
    global multisock
    global localId

    filesDict = {}
    print("Enter files (empty line to finish):")
    while True:
        s = input().strip()
        if not s: break
        idx = s.rfind(' ') + 1
        filesDict[s[:idx-1]] = int(s[idx:])
    wallet = int(input("Money in wallet: "))

    multisock = socket(type=SOCK_DGRAM, proto=IPPROTO_UDP)
    multisock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    multisock.bind((MCAST_GRP, MCAST_PORT))
    mreq = struct.pack("4sl", inet_aton(MCAST_GRP), INADDR_ANY)
    multisock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)

    sock = socket(type=SOCK_DGRAM, proto=IPPROTO_UDP)
    sock.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 2)
    sock.bind((nodeAddr, nodePort))

    localId = address_to_str((nodeAddr, nodePort))
    send_message(LoginMessage(filesDict, wallet))
    print("Node initialized")

def getAndRemove(dictn, key):
    result = dictn[key]
    dictn.erase(key)

def performTransaction(buyer, seller, fileName, cost):
    usersData[seller][0] += cost - usersData[seller][1][fileName]
    usersData[buyer][0] -= cost
    usersData[buyer][1][fileName] = cost

def process_input():
    for readyToRead in select([sys.stdin, sock, multisock], [], [])[0]:
        if readyToRead == sys.stdin:
            line = input().split()
            if not line: continue
            try:
                addr = line[0]
                port, cost = map(int, line[1:3])
                name = ' '.join(line[3:])
                pendingPurchases[messageId] = (name, cost, address_to_string((addr, port)))
                send_message(PurchaseRequest(name, cost), (addr, port))
            except:
                print('Invalid command')
        else:
            messageBytes, senderAddr = readyToRead.recvfrom(4096)
            sender = address_to_str(senderAddr)
            message = parse_message(messageBytes)

            if message.name == "login":
                if sender in usersData: continue
                print("New user discovered: name", sender, "content", message.fileCosts, "wallet", message.wallet)
                usersData[sender] = (message.wallet, message.fileCosts)
                continue

            if sender not in usersData or sender == localId:
                continue

            if message.name == "purchase-req":
                if message.cost > usersData[sender][0]:
                    send_message(RobberyComplaint(sender))
                    continue
                confirm = message.fileName in usersData[localId][1] and 'y' in input("Confirm? ").lower()
                if confirm:
                    unconfirmedPurchasesSeller[(message.messageId, localId)] = (message.fileName, message.cost, sender)
                    send_message(PurchaseConfirmedSeller(message.fileName, sender, message.messageId, message.cost))
                else:
                    send_message(PurchaseRejected(message.messageId), senderAddr)
            elif message.name == "purchase-confrm-seller":
                if message.buyer == localId:
                    pendingData = pendingPurchases[message.requestNumber]
                    if message.fileName != pendingData[0] or message.cost != pendingData[1] or sender != pendingData[2]:
                        send_message(RobberyComplaint(sender))
                        continue
                    pendingPurchases.remove(message.requestNumber)
                    send_message(PurchaseConfirmedBuyer(*pendingData))
                    performTransaction(localId, sender, message.fileName, message.cost)
                else:
                    if (message.requestNumber, message.buyer) not in unconfirmedPurchasesBuyer:
                        unconfirmedPurchasesSeller[(message.requestNumber, sender)] = (message.fileName, message.cost, message.buyer)
                    else:
                        unconfirmedData = unconfirmedPurchasesBuyer[(message.requestNumber, message.buyer)]
                        if message.fileName != unconfirmedData[0] or message.cost != unconfirmedData[1] or message.seller != unconfirmedData[2]:
                            continue
                        unconfirmedPurchasesBuyer.erase((message.requestNumber, message.buyer))
                        performTransaction(message.buyer, sender, message.fileName, message.cost)
            elif message.name == "purchase-confrm-buyer":
                if message.seller == localId:
                    if (message.requestNumber, sender) not in unconfirmedPurchasesSeller:
                        send_message(RobberyComplaint(sender))
                        continue
                    unconfirmedData = unconfirmedPurchasesSeller[(message.requestNumber, sender)]
                    if message.fileName != unconfirmedData[0] or message.value != unconfimedData[1] or sender != unconfirmedData[2]:
                        send_message(RobberyComplaint(sender))
                        continue
                    unconfirmedPurchasesSeller.erase((message.requestNumber, sender))
                    performTransaction(sender, message.seller, message.fileName, message.value)
                else:
                    if (message.requestNumber, sender) not in unconfirmedPurchasesSeller:
                        unconfirmedPurchasesBuyer[(message.requestNumber, sender)] = (message.fileName, message.value, message.seller)
                    else:
                        unconfirmedData = unconfirmedPurchasesSeller[(message.requestNumber, sender)]
                        if message.fileName != unconfirmedData[0] or message.value != unconfimedData[1] or sender != unconfirmedData[2]:
                            continue
                        unconfirmedPurchasesSeller.erase((message.requestNumber, sender))
                        performTransaction(sender, message.seller, message.fileName, message.value)
            elif message.name == "purchase-rej":
                if message.requestNumber not in pendingPurchases:
                    send_message(RobberyComplaint(sender))
                    continue
                pendingPurchases.erase(message.requestNumber)
            elif message.name == "robbery":
                usersData.erase(message.buyer)
                keys = [kv[0] for kv in pendingPurchases.items() if kv[1][2] == message.buyer]
                for k in keys:
                    pendingPurchases.erase(k)
                keys = k for k in unconfirmedPurchasesSeller if k[1] == message.buyer
                for k in keys:
                    unconfirmedPurchasesSeller.erase(k)
                keys = k for k in unconfirmedPurchasesBuyer if k[1] == message.buyer
                for k in keys:
                    unconfirmedPurchasesBuyer.erase(k)

def node_deinit():
    sock.close()
    multisock.close()
