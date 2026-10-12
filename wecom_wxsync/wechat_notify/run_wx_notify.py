#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
企业微信回调服务启动脚本

用途：启动 Flask 应用，提供企业微信回调接口服务
功能：
- 接收企业微信的回调通知（事件推送）
- 接收微信小店的回调通知（事件推送）
- 处理消息加解密
- 路由消息到相应的处理器
"""

# 导入 Flask 应用实例（从 wx_notify_app 模块导入）
from wx_notify_app import app
# 导入操作系统模块，用于环境变量操作
import os
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv

# 加载环境变量（从 .env 文件读取配置信息，如 FLASK_HOST、FLASK_PORT 等）
load_dotenv()

# 程序入口：如果直接运行此脚本（而不是作为模块导入），则执行以下代码
if __name__ == '__main__':
    # 获取主机配置（从环境变量读取，如果不存在则使用默认值 '0.0.0.0'，表示监听所有网络接口）
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    # 获取端口配置（从环境变量读取，如果不存在则使用默认值 '8880'，并转换为整数）
    port = int(os.getenv('FLASK_PORT', '8880'))

    # 协议类型（HTTP，未使用 HTTPS）
    protocol = "http"

    # 打印启动信息（用于提示用户服务正在启动）
    print("=" * 60)
    print("企业微信回调服务启动中...")
    # 显示访问地址（如果 host 是 '0.0.0.0'，则显示为 'localhost'，便于用户访问）
    print(f"访问地址: {protocol}://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    print("=" * 60)
    
    # 启动 Flask 应用
    app.run(
        host=host,      # 监听的主机地址
        port=port,      # 监听的端口号
        # 是否开启调试模式（从环境变量读取，如果值为 'true' 则开启，否则关闭）
        # 调试模式下会自动重载代码，并在出错时显示详细的错误信息
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
    ) 