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

usersData = {}
pendingPurchases = {}
unconfirmedPurchasesSeller = {}
unconfirmedPurchasesBuyer = {}

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

            if sender not in usersData:
                continue

            if message.name == "purchase-req":
                print("User", sender, "requests a file", message.fileName, "for cost", message.cost)
                if message.fileName in filesDict and message.cost > usersData[sender][0]:
                    sendMessage(RobberyComplaint(sender))
                    continue
                yn = message.fileName in filesDict and 'y' in input("Confirm? ").lower()
                if yn:
                    send_message(PurchaseConfirmedSeller(message.fileName, sender, message.messageId))
                else:
                    send_message(PurchaseRejected(message.messageId, sender), senderAddr)

            elif message.name == "purchase-rej":
                if message.requestNumber not in pendingPurchases:
                    send_message(RobberyComplaint(sender))
                    continue
                pendingPurchase = getAndRemove(pendingPurchases, message.requestNumber)
                print("User", sender, "rejected your proposal to sell file", pendingPurchase[0], "for", pendingPurchase[1])

            elif message.name == "purchase-confrm-seller":
                if message.buyer == localId:
                    if message.requestNumber not in pendingPurchases:
                        send_message(RobberyComplaint(sender))
                        continue
                    pendingPurchase = getAndRemove(pendingPurchases, message.requestNumber)
                    if pendingPurchase[0] != message.fileName or pendingPurchase[2] != sender:
                        send_message(RobberyComplaint(sender))
                        continue
                unconfirmedPurchasesSeller[(sender, message.requestNumber)] = (message.buyer, message.fileName, message.cost)
                if message.buyer == localId:
                    print("User", sender, "confirmed your purchase of file", message.fileName)
                    send_message(PurchaseConfirmedBuyer(message.fileName, pendingPurchase[1], sender, message.requestNumber))
                else:
                    print("User", sender, "confirmed purchase of file", message.fileName, "by", message.buyer)

            elif message.name == "purchase-confrm-buyer":
                key = (message.seller, message.requestNumber)
                if key in unconfirmedPurchasesSeller:
                    purchaseData = unconfirmedPurchasesSeller[key]
                    if sender != purchaseData[0]:
                        send_message(RobberyComplaint(sender))
                        continue
                    unconfirmedPurchasesSeller.erase(key)
                    usersData[sender][0] -= message.value
                    usersData[message.seller][0] += message.value - usersData[message.seller][1][purchaseData[1]]
                    usersData[sender][1][purchaseData[1]] = message.value
                else:
                    unconfirmedPurchasesBuyer[(sender, message.requestNumber)] = (message.seller, message.fileName, message.value)

                if message.seller == localId:
                    print("User", sender, "confirmed that you have sold a file", message.fileName)
                else:
                    print("User", sender, "confirmed that a file", message.fileName, "was sold to him by", message.seller)

            elif message.name == "robbery":
                print("Erroneous behaviour observed from user", message.buyer, "by", sender)

def node_deinit():
    sock.close()
    multisock.close()
