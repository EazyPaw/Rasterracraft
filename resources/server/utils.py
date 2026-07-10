# some practical utils
# maybe from web or GitHub or AI assistant or written by myself :)

import functools
import inspect

# ---- client_only 装饰器基础设施 ----

_client_instance = None


def set_client(client):
    """
    设置当前客户端实例，供 @client_only 装饰的方法使用。
    在 Server.__init__() 中当 integrated=True 且传入了 client 时自动调用。
    """
    global _client_instance
    _client_instance = client


def get_client():
    """获取当前客户端实例。"""
    return _client_instance


def client_method(func):
    """
    装饰器：标记一个方法仅供客户端使用，并自动注入 client 实例作为关键字参数。

    用途：写在服务端文件中、但实际只被客户端调用的方法（如纹理渲染相关方法），
          使用此装饰器后，调用方无需显式传入 client 参数，装饰器会自动注入。

    要求：
        1. 被装饰方法的参数列表中必须包含名为 'client' 的参数。
        2. 调用 set_client() 设置客户端实例后方可使用。

    用法：
        # ---- 定义 ----
        class Block:
            @classmethod
            @client_only
            def get_texture(cls, size, client):
                # client 由装饰器自动注入
                return client.resources_manager.get_texture_img(cls._texture_path)

        # ---- 调用（无需传 client）----
        texture = Block.get_texture(16)

        # ---- 也可以显式覆盖（用于测试/特殊场景）----
        texture = Block.get_texture(16, client=some_other_client)
    """
    sig = inspect.signature(func)
    client_param = sig.parameters.get('client')

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if client_param is not None and 'client' not in kwargs:
            # 检查 client 是否已通过位置参数传入
            try:
                bound = sig.bind_partial(*args, **kwargs)
            except TypeError:
                bound = None
            if bound is None or 'client' not in bound.arguments:
                client = get_client()
                if client is not None:
                    kwargs['client'] = client
                elif client_param.default is inspect.Parameter.empty:
                    raise RuntimeError(
                        f"@client_method 方法 '{func.__name__}' 需要客户端实例，"
                        f"但当前无可用客户端。请确保已调用 set_client()。"
                    )
                # 参数有默认值时，client 为 None 也不注入，让默认值生效
        return func(*args, **kwargs)

    return wrapper


# ---- server_method 装饰器基础设施 ----

_server_instance = None


def set_server(server):
    """
    设置当前服务端实例，供 @server_method 装饰的方法使用。
    在服务端启动时自动调用。
    """
    global _server_instance
    _server_instance = server


def get_server():
    """获取当前服务端实例。"""
    return _server_instance


def server_method(func):
    """
    装饰器：标记一个方法仅供服务端使用，并自动注入 server 实例作为关键字参数。

    用途：写在客户端文件中、但实际只被服务端调用的方法，
          使用此装饰器后，调用方无需显式传入 server 参数，装饰器会自动注入。

    要求：
        1. 被装饰方法的参数列表中必须包含名为 'server' 的参数。
        2. 调用 set_server() 设置服务端实例后方可使用。

    用法：
        # ---- 定义 ----
        class SomeClass:
            @server_method
            def do_something(self, server):
                # server 由装饰器自动注入
                server.broadcast(...)

        # ---- 调用（无需传 server）----
        obj.do_something()

        # ---- 也可以显式覆盖（用于测试/特殊场景）----
        obj.do_something(server=some_other_server)
    """
    sig = inspect.signature(func)
    server_param = sig.parameters.get('server')

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if server_param is not None and 'server' not in kwargs:
            # 检查 server 是否已通过位置参数传入
            try:
                bound = sig.bind_partial(*args, **kwargs)
            except TypeError:
                bound = None
            if bound is None or 'server' not in bound.arguments:
                server = get_server()
                if server is not None:
                    kwargs['server'] = server
                elif server_param.default is inspect.Parameter.empty:
                    raise RuntimeError(
                        f"@server_method 方法 '{func.__name__}' 需要服务端实例，"
                        f"但当前无可用服务端。请确保已调用 set_server()。"
                    )
                # 参数有默认值时，server 为 None 也不注入，让默认值生效
        return func(*args, **kwargs)

    return wrapper


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

def hex_to_rgb(hex_color):
    """
    将十六进制颜色转换为RGB格式
    """
    hex_color = hex_color.lstrip('#')  # 去除#号
    b = int(hex_color[4:6], 16)
    g = int(hex_color[2:4], 16)
    r = int(hex_color[0:2], 16)
    return r, g, b