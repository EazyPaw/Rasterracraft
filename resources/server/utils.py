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

def is_safe_value(value, seen=None):
    """
    递归判断一个值是否属于“安全”的数据结构。
    安全类型：int, float, str, bool, NoneType,
    以及仅包含安全元素的 list 和 键为字符串、值为安全元素的 dict。
    """
    if seen is None:
        seen = set()

    # 基本类型直接通过
    if isinstance(value, (int, float, str, bool, type(None))):
        return True

    # 处理 list
    if isinstance(value, list):
        # 防止循环引用导致的无限递归（若自引用则视为不安全，但这里直接返回 True 会跳过递归）
        if id(value) in seen:
            return True  # 简单处理：遇到循环引用时直接认为安全（不会无限递归）
        seen.add(id(value))
        return all(is_safe_value(item, seen) for item in value)

    # 处理 dict
    if isinstance(value, dict):
        if id(value) in seen:
            return True
        seen.add(id(value))
        # JSON 要求字典键为 str，这里强制要求键均为字符串
        if not all(isinstance(k, str) for k in value.keys()):
            return False
        return all(is_safe_value(v, seen) for v in value.values())

    # 其他任何类型均视为不安全
    return False