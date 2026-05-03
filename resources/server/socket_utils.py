def recv_exact(sock, n):
    """从 socket 中精确接收 n 个字节"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:  # 连接关闭
            raise ConnectionError("Disconnected")
        data += chunk
    return data