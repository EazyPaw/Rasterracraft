# some practical utils
# maybe from web or GitHub or AI assistant or written by myself :)

def recv_exact(sock, n):
    """从 socket 中精确接收 n 个字节"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:  # 连接关闭
            raise ConnectionError("Disconnected")
        data += chunk
    return data

def reverse_search_dict(dict_obj: dict, value):
    """
    在字典中使用值来查找键，返回可能包含多个值的 list
    :param dict_obj:
    :param value:
    :return:
    """
    result = []
    for key, val in dict_obj.items():
        if val == value:
            result.append(key)
    return result