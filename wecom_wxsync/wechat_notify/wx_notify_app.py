# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入日志模块（虽然导入了但可能未使用）
import logging
# 导入 JSON 处理模块，用于解析和生成 JSON 数据（虽然导入了但可能未使用）
import json
# 导入哈希库，用于 SHA1 签名计算（微信小店回调签名验证）
import hashlib
# 导入 URL 解码函数，用于解码 URL 编码的参数
from urllib.parse import unquote
# 导入 Flask 框架相关模块，用于创建 Web 应用和接收 HTTP 请求
from flask import Flask, request, abort
# 导入企业微信消息加解密类，用于验证签名和解密消息
from WXBizMsgCrypt import WXBizMsgCrypt
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

## 暂不启用（不处理微信消息通知）
#from wechat_notify_handler.notify_handler import NotifyHandler
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录企业微信回调服务相关的日志信息
logger = setup_logging("wx_notify_app")

# 加载环境变量（从 .env 文件读取配置信息）
load_dotenv()

# 创建 Flask 应用实例（用于接收企业微信和微信小店的回调请求）
app = Flask(__name__)

## 暂不启用（不处理微信消息通知）
#handler = NotifyHandler()
# 消息处理器实例（当前未启用，设为 None）
handler = None

# 获取企业微信配置信息的函数
def get_wecom_config():
    """获取企业微信配置信息（用于回调验证和消息加解密）
    
    Returns:
        tuple: (corp_id, token, encoding_aes_key) - 企业ID、Token、加解密密钥
    """
    # 从环境变量中读取企业微信的配置信息
    corp_id = os.getenv('CORP_ID')                  # 企业 ID
    token = os.getenv('TOKEN')                      # Token（用于签名验证）
    encoding_aes_key = os.getenv('ENCODING_AES_KEY')  # 加解密密钥（用于消息加解密）

    # 返回配置信息元组
    return corp_id, token, encoding_aes_key

# 获取微信小店配置信息的函数
def get_wxxd_config():
    """获取微信小店配置信息（用于回调签名验证）
    
    Returns:
        str: wxxd_token - 微信小店的 Token
    """
    # 从环境变量中读取微信小店的 Token（用于回调签名验证）
    wxxd_token = os.getenv('WXXD_TOKEN')
    return wxxd_token


# Flask 装饰器：在每个请求处理之前执行此函数
@app.before_request
def log_request_info():
    """记录请求信息（在每个请求处理之前执行）
    
    用途：记录所有 HTTP 请求的基本信息，便于调试和监控
    """
    # 记录请求的基本信息
    logger.info(f"=== 收到HTTP请求 ===")
    logger.info(f"请求方法: {request.method}")        # HTTP 方法（GET、POST 等）
    logger.info(f"请求URL: {request.url}")            # 完整的请求 URL
    logger.info(f"请求路径: {request.path}")          # 请求路径（不含查询参数）
    logger.info(f"客户端IP: {request.remote_addr}")   # 客户端 IP 地址
    

# Flask 路由装饰器：定义企业微信回调接口的 GET 请求处理
@app.route('/callback/command', methods=['GET'])
def wecom_callback():
    """
    企业微信回调接口（GET 请求）
    
    用途：用于验证回调URL的有效性（企业微信在配置回调URL时会发送 GET 请求进行验证）
    
    验证流程：
    1. 企业微信发送 GET 请求，携带 msg_signature、timestamp、nonce、echostr 参数
    2. 服务器验证签名并解密 echostr
    3. 返回解密后的 echostr，企业微信验证通过后确认回调URL有效
    """
    # 获取企业微信配置信息（用于消息加解密）
    corp_id, token, encoding_aes_key = get_wecom_config()
    # 验证配置是否完整（所有配置项都不能为空）
    if not all([corp_id, token, encoding_aes_key]):
        logger.error("企业微信配置不完整")
        # 返回 500 错误（服务器内部错误）
        abort(500)
    
    # 获取URL参数（企业微信回调验证所需的参数）
    msg_signature = request.args.get('msg_signature', '')  # 消息签名（用于验证请求来源）
    timestamp = request.args.get('timestamp', '')          # 时间戳
    nonce = request.args.get('nonce', '')                  # 随机字符串
    
    # 记录收到的回调请求信息（用于调试）
    logger.info(f"收到回调请求 - Method: {request.method}, msg_signature: {msg_signature}, timestamp: {timestamp}, nonce: {nonce}")
    
    # 验证请求方法是否为 GET（如果不是，返回 405 方法不允许）
    if request.method != 'GET':
        abort(405)
    # URL验证：获取 echostr 参数（需要解密并返回，用于验证回调URL的有效性）
    echostr = request.args.get('echostr', '')
    # 验证 echostr 参数是否存在（如果不存在，返回 400 错误请求）
    if not echostr:
        logger.error("GET请求缺少echostr参数")
        abort(400)
    
    # 验证必要参数是否存在（如果缺少任何一个，返回 400 错误请求）
    if not all([msg_signature, timestamp, nonce]):
        logger.error("GET请求缺少必要参数")
        abort(400)
    
    # 使用 try-except 捕获验证过程中的异常
    try:
        # 创建加解密对象（用于验证签名和解密消息）
        # 参数：Token（用于签名验证）、EncodingAESKey（用于消息加解密）、ReceiverID（企业 ID，用于标识接收方）
        wxcpt = WXBizMsgCrypt(token, encoding_aes_key, corp_id)
        
        # URL解码echostr参数（echostr 可能是 URL 编码的，需要解码）
        echostr = unquote(echostr)
        # 记录验证过程的详细信息（仅显示前 50 个字符，避免日志过长）
        logger.info(f"开始验证URL - echostr: {echostr[:50]}...")
        # 记录验证参数（EncodingAESKey 仅显示前 10 个字符，避免密钥泄露）
        logger.info(f"验证参数 - Token: {token}, EncodingAESKey: {encoding_aes_key[:10]}..., ReceiverID: {corp_id}")

        # 记录完整的 echostr（用于调试）
        logger.info(f"echostr: {echostr}")

        # 验证URL并解密echostr
        # VerifyURL 方法会验证签名，如果验证通过则解密 echostr 并返回
        result = wxcpt.VerifyURL(msg_signature, timestamp, nonce, echostr)
        
        # 记录验证结果
        logger.info(f"验证URL结果: {result}")

        # 检查返回值类型（VerifyURL 可能返回元组 (ret, reply_echostr) 或单个返回值）
        if isinstance(result, tuple):
            # 如果返回元组，提取返回码和解密后的 echostr
            ret, reply_echostr = result
        else:
            # 如果返回单个值，使用该值作为返回码
            ret = result
            reply_echostr = None
        
        # 记录验证结果码
        logger.info(f"验证结果 - 返回码: {ret}")
        # 检查返回码（0 表示验证成功，非 0 表示失败）
        if ret != 0:
            # 如果验证失败，记录详细的错误信息
            logger.error(f"URL验证失败，错误码: {ret}")
            # 根据不同的错误码提供具体的错误提示
            if ret == -40001:
                logger.error("签名验证失败 - 请检查Token配置是否与企业微信后台一致")
            elif ret == -40002:
                logger.error("AES解密失败或CorpID不匹配 - 请检查EncodingAESKey和CorpID配置")
            else:
                logger.error(f"未知错误码: {ret}")
            # 返回 403 禁止访问（验证失败）
            abort(403)
        
        # 验证成功，记录日志
        logger.info("URL验证成功")
        # 返回解密后的 echostr（企业微信验证此返回值，确认回调URL有效）
        return reply_echostr
    except Exception as e:
        # 如果验证过程中发生异常，记录错误信息
        logger.error(f"URL验证过程发生错误: {str(e)}")
        # 导入 traceback 模块，用于获取详细的错误堆栈信息
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        # 返回 500 服务器内部错误
        abort(500)



# Flask 路由装饰器：定义企业微信回调接口的 POST 请求处理
@app.route('/callback/command', methods=['POST'])
def wecom_callback_post():
    """
    企业微信回调接口（POST 请求）
    
    用途：接收企业微信推送的消息和事件（如外部联系人变更、标签变更等）
    
    处理流程：
    1. 验证请求签名
    2. 解密消息内容
    3. 路由消息到相应的处理器（如果启用）
    4. 返回响应（可选，如果需要回复消息则加密后返回）
    """
    # 获取企业微信配置信息（用于消息加解密）
    corp_id, token, encoding_aes_key = get_wecom_config()
    # 验证配置是否完整
    if not all([corp_id, token, encoding_aes_key]):
        logger.error("企业微信配置不完整")
        abort(500)
    
    # 获取URL参数（用于消息签名验证）
    msg_signature = request.args.get('msg_signature', '')  # 消息签名
    timestamp = request.args.get('timestamp', '')          # 时间戳
    nonce = request.args.get('nonce', '')                  # 随机字符串
    
    # 记录收到的回调请求信息
    logger.info(f"收到回调请求 - Method: {request.method}, msg_signature: {msg_signature}, timestamp: {timestamp}, nonce: {nonce}")
    
    # 验证请求方法是否为 POST
    if request.method != 'POST':
        abort(405)

    # 接收消息：验证必要参数是否存在
    if not all([msg_signature, timestamp, nonce]):
        logger.error("POST请求缺少必要参数")
        abort(400)
        
    # 使用 try-except 捕获处理过程中的异常
    try:
        # 创建加解密对象（用于解密消息和加密响应）
        wxcpt = WXBizMsgCrypt(token, encoding_aes_key, corp_id)
        
        # 获取POST数据（请求体内容，包含加密的消息）
        post_data = request.get_data(as_text=True)
        # 验证请求体是否为空
        if not post_data:
            logger.error("POST请求体为空")
            abort(400)
        
        # 记录收到的 POST 消息（仅显示前 200 个字符，避免日志过长）
        logger.info(f"收到POST消息: {post_data[:200]}...")
        
        # 解密消息（验证签名并解密消息内容）
        # 返回：ret（返回码，0表示成功），msg（解密后的消息内容，XML格式）
        ret, msg = wxcpt.DecryptMsg(post_data, msg_signature, timestamp, nonce)
        
        # 检查解密是否成功
        if ret != 0:
            logger.error(f"消息解密失败，错误码: {ret}")
            abort(403)
        
        # 记录解密成功的消息内容
        logger.info(f"消息解密成功: {msg}")
        # 处理消息（调用 handle_message 函数，根据消息类型路由到相应的处理器）
        # msg_source 参数指定消息来源为 "wecom"（企业微信）
        response_msg = handle_message(msg, msg_source = "wecom")
        
        # 如果需要回复消息（response_msg 不为空）
        if response_msg:
            # 加密响应消息（将回复消息加密后返回给企业微信）
            ret, encrypted_msg = wxcpt.EncryptMsg(response_msg, nonce, timestamp)
            if ret == 0:
                logger.info("响应消息加密成功")
                # 返回加密后的响应消息
                return encrypted_msg
            else:
                logger.error(f"响应消息加密失败，错误码: {ret}")
        
        # 返回空字符串表示成功接收但不回复（大多数情况下不需要回复）
        return ''
        
    except Exception as e:
        # 如果处理过程中发生异常，记录错误信息
        logger.error(f"处理POST请求时发生错误: {str(e)}")
        # 返回 500 服务器内部错误
        abort(500)

@app.route('/callback/wxxd', methods=['GET'])
def wxxd_callback_get():
    """
    微信小店回调接口
    GET请求：用于验证回调URL的有效性
    """
    logger.info("收到微信小店回调验证请求")
    

    # 获取URL参数
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echostr = request.args.get('echostr', '')

    # 进行签名验证
    result = wxxd_signature_check(signature, timestamp, nonce, echostr)
    
    if result:
        logger.info("微信小店回调URL验证成功")
        return result
    else:
        logger.error("微信小店回调URL验证失败")
        abort(403)

@app.route('/callback/wxxd', methods=['POST'])
def wxxd_callback_post():
    """
    微信小店回调接口
    POST请求：接收微信小店推送的消息和事件
    """

    post_json = request.get_json()
    if not post_json:
        logger.error("POST请求体为空")
        abort(400)

    logger.info(f"收到POST消息: {post_json}")



    # 获取配置
    wxxd_token = get_wxxd_config()
    
    msg_signature = request.args.get('msg_signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echostr = post_json.get('Encrypt', '')


    encrypted_msg = wxxd_signature_check(msg_signature, timestamp, nonce, echostr, include_echostr=True)

    if not encrypted_msg:
        logger.error("微信小店签名验证失败")
        abort(403)

    
    
    try:

        wxxd_corp_id = os.getenv('WXXD_CORP_ID')
        wxxd_encoding_aes_key = os.getenv('WXXD_ENCODING_AES_KEY')

        # 创建加解密对象 - 使用CorpID作为receiveid
        wxcpt = WXBizMsgCrypt(wxxd_token, wxxd_encoding_aes_key, wxxd_corp_id)
        
        
        # 解密消息
        ret, msg = wxcpt.DecryptMsg_Direct(encrypted_msg)
        
        if ret != 0:
            logger.error(f"消息解密失败，错误码: {ret}")
            abort(403)
        
        logger.info(f"消息解密成功: {msg}")
        # 处理消息（这里可以根据业务需求进行扩展）
        response_msg = handle_message(msg, msg_source = "wxxd")
        
        if response_msg:
            # 加密响应消息
            ret, encrypted_msg = wxcpt.EncryptMsg(response_msg, nonce, timestamp)
            if ret == 0:
                logger.info("响应消息加密成功")
                return encrypted_msg
            else:
                logger.error(f"响应消息加密失败，错误码: {ret}")
        
        # 返回空字符串表示成功接收但不回复
        return ''
        
    except Exception as e:
        logger.error(f"处理POST请求时发生错误: {str(e)}")
        return ''


# 微信小店回调接口签名验证函数
def wxxd_signature_check(signature, timestamp, nonce, echostr, include_echostr=False):
    """
    微信小店回调接口签名验证
    
    签名验证算法（微信小店使用 SHA1 签名）：
    1. 将 token、timestamp、nonce（以及可选的 echostr）按字典序排序
    2. 拼接成一个字符串
    3. 使用 SHA1 计算哈希值
    4. 与接收到的 signature 进行对比
    
    Args:
        signature (str): 接收到的签名值
        timestamp (str): 时间戳
        nonce (str): 随机字符串
        echostr (str): 验证字符串（GET 请求）或加密的消息（POST 请求）
        include_echostr (bool): 是否在签名计算中包含 echostr（POST 请求需要）
        
    Returns:
        str: 验证通过返回 echostr，验证失败返回空字符串
    """
    try:
        # 获取微信小店Token配置（用于签名计算）
        wxxd_token = get_wxxd_config()
        if not wxxd_token:
            logger.error("微信小店Token配置不完整")
            return ""
        
        # 记录签名验证的详细信息（echostr 仅显示前 50 个字符）
        logger.info(f"微信小店签名验证 - signature: {signature}, timestamp: {timestamp}, nonce: {nonce}, echostr: {echostr[:50] if echostr else ''}...")
        
        # 检查必要参数（所有参数都不能为空）
        if not all([signature, timestamp, nonce, echostr]):
            logger.error("微信小店回调请求缺少必要参数")
            return ""
        
        # 构建参数字符串列表（用于签名计算）
        # 根据 include_echostr 参数决定是否包含 echostr（POST 请求需要包含）
        if include_echostr:
            params = [wxxd_token, timestamp, nonce, echostr]
        else:
            params = [wxxd_token, timestamp, nonce]
        
        # 对参数进行字典序排序（这是微信签名算法的要求）
        params.sort()
        
        # 将参数字符串拼接成一个字符串（用于 SHA1 计算）
        concat_str = ''.join(params)
        logger.info(f"拼接字符串: {concat_str}")
        
        # 进行 SHA1 计算签名（将拼接后的字符串进行 SHA1 哈希计算）
        sha1_hash = hashlib.sha1(concat_str.encode('utf-8')).hexdigest()
        logger.info(f"计算的签名: {sha1_hash}")
        logger.info(f"接收的签名: {signature}")
        
        # 与URL链接中的signature参数进行对比（如果一致，则验证通过）
        if sha1_hash == signature:
            logger.info("微信小店签名验证成功")
            # 验证通过，返回 echostr（GET 请求）或加密消息（POST 请求）
            return echostr
        else:
            logger.error("微信小店签名验证失败")
            return ""
            
    except Exception as e:
        # 如果验证过程中发生异常，记录错误信息
        logger.error(f"微信小店签名验证过程发生错误: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return ""

# 处理消息的函数（根据消息类型路由到相应的处理器）
def handle_message(msg, msg_source = "wecom"):  ## msg_source: wecom, wxxd
    """处理消息（将解密后的消息路由到相应的处理器）
    
    Args:
        msg (str): 解密后的消息内容（XML 格式或 JSON 格式）
        msg_source (str): 消息来源，"wecom"（企业微信）或 "wxxd"（微信小店）
        
    Returns:
        str|None: 如果需要回复消息，返回回复内容；否则返回 None
    """
    logger.info(f"处理消息: {msg}")
    
    # 导入消息处理器（如果 handler 为 None，说明未启用消息处理）
    try:
        # 如果 handler 为 None，会抛出 AttributeError
        # 调用处理器的 process_message 方法处理消息（解析消息并路由到相应的处理器）
        result = handler.process_message(msg)
        logger.info(f"处理消息结果: {result}")
        return None
    except (ImportError, AttributeError) as e:
        # 如果导入失败或 handler 为 None，记录错误信息
        logger.error(f"导入消息处理器失败: {e}")
        logger.info(f"处理消息结果：暂不实现业务逻辑。")
        return None
    except Exception as e:
        # 如果处理过程中发生其他异常，记录错误信息
        logger.error(f"处理消息时发生错误: {e}")
        return None

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return {'status': 'ok', 'message': '企业微信回调服务运行正常'}

@app.route('/', methods=['GET'])
def index():
    """根路径接口"""
    return '''
    <h1>企业微信回调服务</h1>
    <p>服务正在运行...</p>
    <h2>API接口</h2>
    <ul>
        <li>回调地址: <code>/callback/command</code></li>
        <li>健康检查: <a href="/health"><code>/health</code></a></li>
    </ul>
    '''

