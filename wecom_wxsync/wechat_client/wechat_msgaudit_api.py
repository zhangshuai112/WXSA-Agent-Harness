# 导入 Base64 编码模块，用于处理 Base64 编码的加密密钥
import base64
# 导入 ctypes 模块，用于调用 C 语言动态链接库（企业微信会话存档 SDK）
import ctypes
# 导入 JSON 处理模块，用于解析和生成 JSON 数据
import json
# 导入操作系统模块，用于环境变量和文件操作
import os
# 导入格式化打印模块，用于美化输出（调试用）
from pprint import pprint
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv
# 导入 RSA 加密模块（PKCS1_v1_5 填充模式），用于解密加密密钥
from Crypto.Cipher import PKCS1_v1_5
# 导入 RSA 公钥处理模块，用于导入私钥
from Crypto.PublicKey import RSA
# 导入系统模块，用于路径操作
import sys
# 将项目根目录添加到 Python 模块搜索路径中，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录企业微信会话存档 API 相关的日志信息
logger = setup_logging("wechat_msgaudit_api")

# 加载环境变量（从 .env 文件读取配置信息）
load_dotenv()

# 同步企业微信消息的函数
# 注意：因为解密库是 C 语言的，只能在独立的进程中运行
def get_msg_list(start_seq=0, limit=1000):
    """
    同步企业微信消息，因为解密库是C语言的，只能在独立的进程中运行。
    
    工作流程：
    1. 加载企业微信会话存档 SDK（C 语言动态库）
    2. 初始化 SDK 并获取加密的消息列表
    3. 使用 RSA 私钥解密加密密钥
    4. 使用解密后的密钥解密消息内容
    5. 返回解密后的消息列表
    
    Args:
        start_seq (int): 指定起始seq（消息序列号），默认 0，用于增量同步
        limit (int): 每次获取的消息数量，默认 1000，最大 1000
        
    Returns:
        List[Dict[str, Any]]: 解密后的消息列表，每个消息是一个字典
    """
    # 参数验证：确保 start_seq 和 limit 都是正数
    if start_seq < 0 or limit <= 0:
        raise Exception("start_seq 和 limit 必须大于 0")

    # 参数验证：limit 不能超过 1000（微信 API 限制）
    if limit > 1000:
        raise Exception("limit 不能大于 1000")

    # 初始化返回值列表（用于存储解密后的消息）
    results = []

    # 记录开始同步的日志
    logger.info("开始同步企业微信消息...")
    
    # 从环境变量中获取企业微信的配置信息
    CORP_ID = os.getenv('CORP_ID')                    # 企业 ID
    APP_SECRET = os.getenv('MSGAUDIT_APP_SECRET')     # 会话存档应用的密钥
    PRI_KEY = open(os.getenv('MSGAUDIT_PRI_KEY'), 'r').read()  # RSA 私钥文件内容（用于解密）
    SDK_PATH = os.getenv('WeWorkFinanceSdk')          # 企业微信会话存档 SDK 的路径（C 语言动态库）

    # 加载企业微信会话存档 SDK（C 语言动态链接库）
    # 这个 SDK 是微信提供的，用于获取加密的会话消息
    dll = ctypes.cdll.LoadLibrary(SDK_PATH)  # 加载 SDK 动态库（真实libWeWorkFinanceSdk_C位置）
    # 创建 SDK 实例
    new_sdk = dll.NewSdk()
    # 初始化 SDK（传入企业 ID 和应用密钥）
    result = dll.Init(new_sdk, CORP_ID.encode(), APP_SECRET.encode())
    # 检查初始化是否成功（返回 0 表示成功）
    if result != 0:
        raise Exception(f"初始化SDK失败，错误码: {result}")
    
    # 记录开始同步的日志（包含起始序列号）
    logger.info(f"从seq {start_seq} 开始同步消息...")

    # 初始化 RSA 解密器（用于解密加密密钥）
    # 导入 RSA 私钥（从 PEM 格式的私钥文件中读取）
    private_key = RSA.import_key(PRI_KEY)
    # 创建 PKCS1_v1_5 填充模式的 RSA 解密器
    cipher = PKCS1_v1_5.new(private_key)
    
    # 循环获取消息（直到没有更多消息）
    while True:
        # 创建一个新的 Slice 对象（用于接收 SDK 返回的数据）
        slice = dll.NewSlice()
        # 记录正在请求的消息日志
        logger.info(f"正在请求消息，seq={start_seq}, limit={limit}")
        # 调用 SDK 的 GetChatData 方法获取加密的消息数据
        # 参数：SDK实例、起始seq、数量限制、其他参数、超时时间、输出Slice
        dll.GetChatData(new_sdk, start_seq, limit, '', '', 5, ctypes.c_long(slice))
        
        # 从 Slice 对象中获取数据指针
        data = dll.GetContentFromSlice(slice)
        # 将 C 字符串转换为 Python 字符串（-1 表示自动计算长度）
        data_str = ctypes.string_at(data, -1).decode("utf-8")
        # 释放 Slice 对象（避免内存泄漏）
        dll.FreeSlice(slice)
        
        # 尝试解析 JSON 数据
        try:
            # 将 JSON 字符串解析为 Python 字典
            data_json = json.loads(data_str)
        except json.JSONDecodeError as e:
            # 如果 JSON 解析失败，记录错误并退出循环
            logger.error(f"JSON解析失败: {e}")
            break
            
        # 从 JSON 数据中提取消息列表、错误码和错误消息
        chatdata = data_json.get('chatdata')  # 加密的消息列表
        errcode = data_json.get('errcode', 0) # 错误码（0 表示成功）
        errmsg = data_json.get('errmsg', '')  # 错误消息
        
        # 检查 API 是否返回错误
        if errcode != 0:
            # 如果返回错误，记录日志并退出循环
            logger.error(f"API返回错误: errcode={errcode}, errmsg={errmsg}")
            break
            
        # 检查是否还有消息
        if not chatdata:
            # 如果没有更多消息，记录日志并退出循环
            logger.info("没有更多消息，同步结束")
            break
            
        # 记录获取到的消息数量
        logger.info(f"获取到 {len(chatdata)} 条消息")
        # 更新 seq 值（使用最后一条消息的 seq，用于下次增量同步）
        start_seq = chatdata[-1].get('seq')
        
        # 遍历每条加密的消息，进行解密
        for msg in chatdata:
            try:
                # 解密消息流程：
                # 1. 提取消息序列号
                seq = msg.get('seq')
                # 2. 使用 RSA 私钥解密加密密钥（encrypt_random_key 是 Base64 编码的 RSA 加密密钥）
                encrypt_key = cipher.decrypt(base64.b64decode(msg.get('encrypt_random_key')), "ERROR")
                # 3. 创建一个新的 Slice 对象（用于接收解密后的数据）
                ss = dll.NewSlice()
                # 4. 使用解密后的密钥解密消息内容（encrypt_chat_msg 是使用 encrypt_key 加密的消息）
                dll.DecryptData(encrypt_key, msg.get('encrypt_chat_msg').encode(), ctypes.c_long(ss))
                # 5. 从 Slice 对象中获取解密后的数据指针
                result = dll.GetContentFromSlice(ss)
                # 6. 将 C 字符串转换为 Python 字符串
                result = ctypes.string_at(result, -1).decode("utf-8")
                # 7. 将 JSON 字符串解析为 Python 字典
                result = json.loads(result)
                # 8. 添加消息序列号到结果中（便于追踪）
                result['seq'] = seq
                # 9. 释放 Slice 对象
                dll.FreeSlice(ss)
                
                # 将解密后的消息添加到结果列表
                results.append(result)

            except Exception as e:
                # 如果解密失败，记录错误但继续处理下一条消息
                print(f"处理消息失败: {e}")
                continue
            
    # 销毁 SDK 实例（释放资源）
    dll.DestroySdk(new_sdk)

    # 返回解密后的消息列表
    return results


if __name__ == "__main__":
    results = get_msg_list(start_seq=0, limit=100)
    for r in results:
        pprint(json.dumps(r, ensure_ascii=False, indent=4))