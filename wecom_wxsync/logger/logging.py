# 导入 Python 标准库的日志模块，用于记录程序运行日志
import logging

# 配置日志系统的函数，用于统一设置日志格式和输出方式
def setup_logging(name="default", level=logging.INFO):
    """配置日志系统
    
    Args:
        name (str): 日志器名称，默认为 "default"，用于区分不同模块的日志
        level (int): 日志级别，默认为 logging.INFO（信息级别），可选值：
            - logging.DEBUG: 调试信息
            - logging.INFO: 一般信息
            - logging.WARNING: 警告信息
            - logging.ERROR: 错误信息
            - logging.CRITICAL: 严重错误
            
    Returns:
        logging.Logger: 配置好的日志器实例，可以用于记录日志
    """
    # 创建日志格式字符串
    # %(asctime)s: 时间戳（如：2025-01-15 10:30:45,123）
    # %(name)s: 日志器名称（如：wechat_work_api）
    # %(levelname)s: 日志级别（如：INFO、ERROR）
    # %(message)s: 日志消息内容
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 配置根日志器（所有日志器的父级）
    # basicConfig 只需要调用一次，后续调用不会生效
    logging.basicConfig(
        level=level,              # 设置日志级别（只显示该级别及以上的日志）
        format=log_format,        # 设置日志格式
        handlers=[
            logging.StreamHandler(),  # 添加控制台输出处理器（日志会输出到标准输出，如终端）
        ]
    )
    
    # 创建应用专用日志器（使用指定的名称）
    # 同一个名称的日志器只会创建一次，后续调用会返回同一个实例
    logger = logging.getLogger(name)
    # 设置日志器级别（虽然已经设置了根日志器级别，但单独设置可以更精确控制）
    logger.setLevel(level)
    
    # 返回配置好的日志器实例，调用方可以使用 logger.info()、logger.error() 等方法记录日志
    return logger