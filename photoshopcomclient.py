import socket


def sendSome(jsx: str):
    server_address = ("localhost", 34634)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(server_address)
    message = jsx
    client_socket.send(message.encode())
    response = client_socket.recv(1024).decode()
    print(f"Received response: {response}")

    client_socket.close()
