import message_pb2 as pb

class Message:
    def __init__(self, messageId: int):
        self.messageId = messageId

    def serialize(self):
        result = pb.Message()
        result.name = self.name
        result.messageId = self.messageId
        result.content = self.serializeContent().SerializeToString()
        return result.SerializeToString()

class LoginMessage(Message):
    name = "login"

    def __init__(self, fileCosts: dict, wallet: int, messageId: int = 0):
        Message.__init__(self, messageId)
        self.fileCosts = fileCosts
        self.wallet = wallet

    def serializeContent(self):
        result = pb.LoginMessage()
        for name, cost in self.fileCosts.items():
            result.files[name] = cost
        result.wallet = self.wallet
        return result

class PurchaseRequest(Message):
    name = "purchase-req"

    def __init__(self, fileName: str, cost: int, messageId: int = 0):
        Message.__init__(self, messageId)
        self.fileName = fileName
        self.cost = cost

    def serializeContent(self):
        result = pb.PurchaseRequest()
        result.fileName = self.fileName
        result.cost = self.cost
        return result

class PurchaseConfirmedSeller(Message):
    name = "purchase-confrm-seller"

    def __init__(self, fileName: str, buyer: str, requestNumber: int, cost: int, messageId: int = 0):
        Message.__init__(self, messageId)
        self.fileName = fileName
        self.buyer = buyer
        self.requestNumber = requestNumber
        self.cost = cost

    def serializeContent(self):
        result = pb.PurchaseConfirmedSeller()
        result.fileName = self.fileName
        result.buyer = self.buyer
        result.requestNumber = self.requestNumber
        result.cost = cost
        return result

class PurchaseConfirmedBuyer(Message):
    name = "purchase-confrm-buyer"

    def __init__(self, fileName: str, value: int, seller: str, messageId: int = 0):
        Message.__init__(self, messageId)
        self.fileName = fileName
        self.value = value
        self.seller = seller

    def serializeContent(self):
        result = pb.PurchaseConfirmedBuyer()
        result.fileName = self.fileName
        result.value = self.value
        result.seller = self.seller
        return result

class PurchaseRejected(Message):
    name = "purchase-rej"

    def __init__(self, requestNumber: int, messageId: int = 0):
        Message.__init__(self, messageId)
        self.requestNumber = requestNumber

    def serializeContent(self):
        result = pb.PurchaseRejected()
        result.requestNumber = self.requestNumber
        return result

class RobberyComplaint(Message):
    name = "robbery"

    def __init__(self, buyer: str, messageId: int = 0):
        Message.__init__(self, messageId)
        self.buyer = buyer

    def serializeContent(self):
        result = pb.RobberyComplaint()
        result.buyer = self.buyer
        return result

def parse_message(messageBytes: bytes):
    message = pb.Message()
    message.ParseFromString(messageBytes)
    if message.name == "login":
        content = pb.LoginMessage()
        content.ParseFromString(message.content)
        return LoginMessage(dict(content.files.items()), content.wallet, message.messageId)
    if message.name == "purchase-req":
        content = pb.PurchaseRequest()
        content.ParseFromString(message.content)
        return PurchaseRequest(content.fileName, content.cost, message.messageId)
    if message.name == "purchase-confrm-seller":
        content = pb.PurchaseConfirmedSeller()
        content.ParseFromString(message.content)
        return PurchaseConfirmedSeller(content.fileName, content.buyer, message.messageId)
    if message.name == "purchase-confrm-buyer":
        content = pb.PurchaseConfirmedBuyer()
        content.ParseFromString(message.content)
        return PurchaseConfirmedBuyer(content.fileName, content.value, content.seller, message.messageId)
    if message.name == "purchase-rej":
        content = pb.PurchaseRejected()
        content.ParseFromString(message.content)
        return PurchaseRejected(content.requestNumber, message.messageId)
    if message.name == "robbery":
        content = pb.RobberyComplaint()
        conetnt.ParseFromString(message.content)
        return RobberyComplaint(content.buyer, message.messageId)
    raise NotImplementedError("Unknown message name: " + message.name)
