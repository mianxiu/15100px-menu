import win32com.client, pythoncom

import socket


# 连接到 Photoshop 的 COM 接口
def runjsx(jsx):
    pythoncom.CoInitialize()

    # 连接到 Photoshop 的 COM 接口
    app = win32com.client.Dispatch("Photoshop.Application")

    # 执行 JavaScript 代码
    # result = app.DoJavaScript("alert('123')")
    app.DoJavaScript(jsx)
    # 输出执行结果
    # print(result)
    app = None

    pythoncom.CoUninitialize()


server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server_socket.bind(("localhost", 34634))
server_socket.listen(1)

print("Server started and listening for connections...")

while True:
    client_socket, client_address = server_socket.accept()
    print(f"Connection from {client_address} has been established!")
    message = client_socket.recv(1024 * 100).decode()
    print(f"Received message: {message}")
    runjsx(message)
    response = "Message received"
    client_socket.send(response.encode())
    # Process the message here
    client_socket.close()
