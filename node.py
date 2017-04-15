import sys
import struct
import traceback
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

def performTransaction(buyer, seller, fileName, cost):
    usersData[seller] = (usersData[seller][0] + cost - usersData[seller][1][fileName], usersData[seller][1])
    usersData[buyer] = (usersData[buyer][0] - cost, usersData[buyer][1])
    usersData[buyer][1][fileName] = cost

def process_input():
    for readyToRead in select([sys.stdin, sock, multisock], [], [])[0]:
        if readyToRead == sys.stdin:
            line = input().split()
            if not line: 
                print("Users info:")
                print(usersData)
                continue
            try:
                addr = line[0]
                port, cost = map(int, line[1:3])
                name = ' '.join(line[3:])
                pendingPurchases[messageId] = (name, cost, address_to_str((addr, port)))
                send_message(PurchaseRequest(name, cost), (addr, port))
            except:
                traceback.print_exc()
        else:
            messageBytes, senderAddr = readyToRead.recvfrom(4096)
            sender = address_to_str(senderAddr)
            message = parse_message(messageBytes)

            if message.name == "login":
                if sender in usersData and sender != localId: 
                    continue
                print("New user discovered: name", sender, "content", message.fileCosts, "wallet", message.wallet)
                usersData[sender] = (message.wallet, message.fileCosts)
                if sender != localId:
                    send_message(LoginMessage(usersData[localId][1], usersData[localId][0]), senderAddr)
                continue
            elif message.name == "robbery":
                print(sender + ": Erroneous behaviour from user", message.buyer)
                del usersData[message.buyer]
                keys = [kv[0] for kv in pendingPurchases.items() if kv[1][2] == message.buyer]
                for k in keys:
                    del pendingPurchases[k]
                keys = [k for k in unconfirmedPurchasesSeller if k[1] == message.buyer]
                for k in keys:
                    del unconfirmedPurchasesSeller[k]
                keys = [k for k in unconfirmedPurchasesBuyer if k[1] == message.buyer]
                for k in keys:
                    del unconfirmedPurchasesBuyer[k]
                continue

            if sender not in usersData or sender == localId:
                continue

            print(sender, ": ", sep='', end='')
            if message.name == "purchase-req":
                print("Purchase of", message.fileName, "for", message.cost, "was requested by", sender, "request no.", message.messageId)
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
                print("Seller confirmed purchase of", message.fileName, "for", message.cost, "by", message.buyer, "request no.", message.requestNumber)
                buyer, seller = message.buyer, sender
                if message.buyer == localId:
                    pendingData = pendingPurchases[message.requestNumber]
                    if message.fileName != pendingData[0] or message.cost != pendingData[1] or seller != pendingData[2]:
                        send_message(RobberyComplaint(sender))
                        continue
                    del pendingPurchases[message.requestNumber]
                    send_message(PurchaseConfirmedBuyer(pendingData[0], pendingData[1], pendingData[2], message.requestNumber))
                    performTransaction(buyer, seller, message.fileName, message.cost)
                else:
                    buyerKey = (message.requestNumber, buyer)
                    sellerKey = (message.requestNumber, seller)
                    if buyerKey not in unconfirmedPurchasesBuyer:
                        unconfirmedPurchasesSeller[sellerKey] = (message.fileName, message.cost, buyer)
                    else:
                        unconfirmedData = unconfirmedPurchasesBuyer[buyerKey]
                        if message.fileName != unconfirmedData[0] or message.cost != unconfirmedData[1] or seller != unconfirmedData[2]:
                            continue
                        del unconfirmedPurchasesBuyer[buyerKey]
                        performTransaction(buyer, seller, message.fileName, message.cost)
            elif message.name == "purchase-confrm-buyer":
                print("Buyer confirmed purchase of", message.fileName, "for", message.value, "from", message.seller, "request no.", message.requestNumber)
                buyer, seller = sender, message.seller
                buyerKey = (message.requestNumber, buyer)
                sellerKey = (message.requestNumber, seller)
                if seller == localId:
                    if sellerKey not in unconfirmedPurchasesSeller:
                        send_message(RobberyComplaint(sender))
                        continue
                    unconfirmedData = unconfirmedPurchasesSeller[sellerKey]
                    if message.fileName != unconfirmedData[0] or message.value != unconfirmedData[1] or buyer != unconfirmedData[2]:
                        send_message(RobberyComplaint(sender))
                        continue
                    del unconfirmedPurchasesSeller[sellerKey]
                    performTransaction(buyer, seller, message.fileName, message.value)
                else:
                    if sellerKey not in unconfirmedPurchasesSeller:
                        unconfirmedPurchasesBuyer[buyerKey] = (message.fileName, message.value, seller)
                    else:
                        unconfirmedData = unconfirmedPurchasesSeller[sellerKey]
                        if message.fileName != unconfirmedData[0] or message.value != unconfirmedData[1] or buyer != unconfirmedData[2]:
                            continue
                        del unconfirmedPurchasesSeller[sellerKey]
                        performTransaction(buyer, seller, message.fileName, message.value)
            elif message.name == "purchase-rej":
                print("Your purchase", pendingPurchases[message.requestNumber], "with request no.", message.requestNumber, "was rejected")
                if message.requestNumber not in pendingPurchases or pendingPurchases[message.requestNumber][2] != sender:
                    send_message(RobberyComplaint(sender))
                    continue
                del pendingPurchases[message.requestNumber]

def node_deinit():
    sock.close()
    multisock.close()
