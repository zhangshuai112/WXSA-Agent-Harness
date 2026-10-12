"""Per-user OpenSandbox lifecycle management backed by PostgreSQL."""

# 推迟类型注解解析，支持在注解中使用尚未定义的类型。
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from agent.backends.sandbox_proxy import SandboxBackendProxy
from agent.config import SANDBOX_CONFIG
from agent.utils.agent_logger import get_logger

logger = get_logger("sandbox_manager")

# 数据库 schema/table 专门保存沙箱注册信息，避免和业务表混在一起。
# 指定 PostgreSQL 中保存沙箱信息的 schema 名称。
SANDBOX_SCHEMA = "agent_runtime"
# 指定 schema 内保存用户和沙箱映射的表名。
SANDBOX_TABLE = "sandbox_registry"

# 进程内热缓存：当前进程已连接的用户沙箱代理。
# 按用户 ID 缓存当前进程已连接的沙箱代理。
SANDBOX_BACKENDS: dict[str, SandboxBackendProxy] = {}
# 尚未分配给用户的预热沙箱，只维持一个以控制闲置成本。
# 保存一个尚未分配给任何用户的预热沙箱代理。
_warm_reserve: SandboxBackendProxy | None = None
# 防止并发首请求领取同一预热沙箱或重复补货。
# 使用异步锁保证预热沙箱的领取和补货不会并发冲突。
_warm_lock = asyncio.Lock()
# 可由 initialize 注入的连接池；未注入时回退至全局配置池。
# 保存可选的 PostgreSQL 连接池注入值；默认未初始化。
_postgres_pool: Any | None = None


def _get_postgres_pool() -> Any:
    # 返回显式注入的连接池，或懒加载应用默认连接池。
    # 测试或应用启动时可显式注入；生产默认从 agent.config 延迟导入。
    # 已有注入连接池时不再导入默认配置。
    if _postgres_pool is not None:
        # 返回缓存的连接池。
        return _postgres_pool
    # 延迟导入默认连接池，避免模块导入时过早初始化数据库。
    from agent.config import pool
    # 返回配置模块导出的默认连接池。
    return pool


def _initialize_sync(postgres_pool: Any | None = None) -> None:
    # 同步初始化 PostgreSQL 的 schema、映射表和索引。
    global _postgres_pool
    # 调用方传入连接池时，以它覆盖此前保存的连接池。
    if postgres_pool is not None:
        # 保存显式传入的连接池，供后续所有数据库操作复用。
        _postgres_pool = postgres_pool
    # 取得当前应使用的连接池。
    pool = _get_postgres_pool()
    # 从连接池借出数据库连接，并在退出时归还。
    with pool.connection() as connection:
        # 创建游标以执行 SQL 语句，并在退出时关闭。
        with connection.cursor() as cursor:
            # schema 与表均使用 IF NOT EXISTS，初始化可安全重复调用。
            # 创建专用 schema；已存在时保持不变。
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {SANDBOX_SCHEMA}")
            # 创建用户到沙箱的注册表；表已存在时保持不变。
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SANDBOX_SCHEMA}.{SANDBOX_TABLE} (
                    user_id TEXT PRIMARY KEY,
                    sandbox_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_health_check_at TIMESTAMPTZ,
                    last_error TEXT
                )
                """
            )
            # 为按更新时间查询注册记录创建索引。
            cursor.execute(
                # 时间索引用于后续按最后更新时间扫描、清理或运维查询。
                f"""
                CREATE INDEX IF NOT EXISTS sandbox_registry_updated_at_idx
                ON {SANDBOX_SCHEMA}.{SANDBOX_TABLE} (updated_at)
                """
            )


async def initialize(postgres_pool: Any | None = None) -> None:
    """Initialize the PostgreSQL table used for user-to-sandbox mappings."""
    # psycopg 操作是同步 I/O，放在线程中避免阻塞异步启动流程。
    # 在线程中运行同步数据库初始化，避免阻塞事件循环。
    await asyncio.to_thread(_initialize_sync, postgres_pool)
    # 记录初始化成功，方便服务启动排查。
    logger.info("Sandbox manager PostgreSQL registry initialized")


def _ensure_initialized() -> None:
    # 确保数据库结构已创建。
    # 各数据库助手自包含，调用前确保表已经存在。
    # 调用幂等初始化函数，因此可在每个数据库帮助函数前安全调用。
    _initialize_sync()


def _save_mapping(
    user_id: str,
    sandbox_id: str,
    *,
    created: bool = False,
    status: str = "active",
    last_error: str | None = None,
) -> None:
    # 新增或覆盖用户到沙箱 ID 的数据库映射。
    # 保存或更新用户到当前沙箱的绑定；created 参数保留给调用语义，
    # 创建时间由首次 INSERT 写入，冲突更新不会覆盖原 created_at。
    # 先保证表和索引存在。
    _ensure_initialized()
    # 统一使用带时区 UTC，跨机器、跨时区写入可比较。
    # 生成当前 UTC 时间戳。
    now = datetime.now(timezone.utc)
    # 取得数据库连接池。
    pool = _get_postgres_pool()
    # 借出连接，退出上下文时归还。
    with pool.connection() as connection:
        # 创建 SQL 执行游标。
        with connection.cursor() as cursor:
            # 使用参数化 SQL 执行插入或冲突更新。
            # ON CONFLICT 确保一个 user_id 始终只映射一个当前沙箱。
            cursor.execute(
                f"""
                INSERT INTO {SANDBOX_SCHEMA}.{SANDBOX_TABLE}
                    (user_id, sandbox_id, status, created_at, updated_at, last_error)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    sandbox_id = EXCLUDED.sandbox_id,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    last_error = EXCLUDED.last_error
                """,
                # 为 SQL 中的 %s 占位符提供参数，避免将用户输入拼进 SQL。
                (user_id, sandbox_id, status, now, now, last_error),
            )


def _touch_mapping(user_id: str, *, error: str | None = None) -> None:
    # 更新用户映射的活动时间、健康检查时间和最近错误。
    # 健康访问后更新活动时间；也会清除或记录最近一次错误信息。
    # 确保注册表存在。
    _ensure_initialized()
    # 取得当前 UTC 时间。
    now = datetime.now(timezone.utc)
    # 获取数据库连接池。
    pool = _get_postgres_pool()
    # 借出数据库连接。
    with pool.connection() as connection:
        # 创建 SQL 游标。
        with connection.cursor() as cursor:
            # 根据用户 ID 更新已有的注册记录。
            cursor.execute(
                f"""
                UPDATE {SANDBOX_SCHEMA}.{SANDBOX_TABLE}
                SET updated_at = %s, last_health_check_at = %s,
                    last_error = %s, status = 'active'
                WHERE user_id = %s
                """,
                # 依次绑定更新时间、健康检查时间、错误文本和用户 ID。
                (now, now, error, user_id),
            )


def _get_mapping(user_id: str) -> dict[str, Any] | None:
    # 查询指定用户的持久化沙箱注册记录。
    # 查询跨进程持久化记录，以便在本地缓存未命中时重连。
    # 确保注册表存在。
    _ensure_initialized()
    # 获取数据库连接池。
    pool = _get_postgres_pool()
    # 借出数据库连接。
    with pool.connection() as connection:
        # 创建 SQL 游标。
        with connection.cursor() as cursor:
            # 查询该用户完整的沙箱注册信息。
            cursor.execute(
                f"""
                SELECT user_id, sandbox_id, status, created_at, updated_at,
                       last_health_check_at, last_error
                FROM {SANDBOX_SCHEMA}.{SANDBOX_TABLE}
                WHERE user_id = %s
                """,
                # 单元素元组为 SQL 占位符传入用户 ID。
                (user_id,),
            )
            # 没有记录时返回 None，让调用方进入创建流程。
            # 读取最多一条查询结果。
            row = cursor.fetchone()
            # 没有注册记录时直接返回空结果。
            if row is None:
                # 让调用方改走创建新沙箱流程。
                return None
            # cursor.description 给出列名，将元组转换为便于调用的字典。
            # 将列名生成器和查询结果元组配对，构造成字典后返回。
            return dict(zip((column.name for column in cursor.description), row))


def _delete_mapping(user_id: str) -> None:
    # 删除指定用户的持久化沙箱映射。
    # 清理用户时同时删除持久化绑定，阻止以后重连已删除沙箱。
    # 确保表存在。
    _ensure_initialized()
    # 获取数据库连接池。
    pool = _get_postgres_pool()
    # 借出数据库连接。
    with pool.connection() as connection:
        # 创建 SQL 游标。
        with connection.cursor() as cursor:
            # 使用参数化 DELETE 移除该用户的记录。
            cursor.execute(
                f"DELETE FROM {SANDBOX_SCHEMA}.{SANDBOX_TABLE} WHERE user_id = %s",
                # 向 DELETE 语句绑定用户 ID。
                (user_id,),
            )


async def _kill_remote_sandbox(sandbox_id: str) -> None:
    """按 ID 终止远端沙箱（异步 SDK）。"""
    from opensandbox import SandboxManager

    manager = await SandboxManager.create(connection_config=SANDBOX_CONFIG)
    try:
        await manager.kill_sandbox(sandbox_id)
    finally:
        await manager.close()


async def pre_warm() -> None:
    """Create one reserve sandbox for the first user request."""
    # 声明函数需要修改模块级预热库存变量。
    global _warm_reserve
    # 预热失败不影响服务运行，因此将所有创建异常转为日志。
    try:
        # 创建完整初始化过的沙箱，但暂不写入用户映射。
        from agent.backends.sandbox_setup import setup_sandbox
        sandbox_backend = await setup_sandbox(SANDBOX_CONFIG)
        logger.info("Warm sandbox ready: %s", sandbox_backend.id)
        _warm_reserve = SandboxBackendProxy(sandbox_backend)
    except Exception:
        # 预热失败不应阻断服务启动；首次请求会走普通创建路径。
        logger.warning("Failed to create warm sandbox", exc_info=True)
        _warm_reserve = None


async def ensure_sandbox_for_user(user_id: str) -> SandboxBackendProxy:
    """Return a healthy sandbox assigned to ``user_id`` or create one."""
    # 空用户 ID 会破坏按用户隔离与数据库主键映射。
    if not user_id:
        raise ValueError("user_id is required")

    # 第一优先级：复用当前进程内存中的已连接代理。
    proxy = SANDBOX_BACKENDS.get(user_id)
    if proxy is not None:
        try:
            result = await proxy.aexecute("echo ok")
            if result.exit_code != 0:
                raise RuntimeError(result.output[:200])
            return proxy
        except Exception:
            logger.warning("Sandbox %s is unhealthy; recreating", proxy.id, exc_info=True)
            return await _recreate_sandbox(user_id, proxy)

    # 第二优先级：领取启动时已建好的预热实例，减少首个请求的冷启动。
    global _warm_reserve
    acquired_proxy = None
    async with _warm_lock:
        if _warm_reserve is not None:
            acquired_proxy = _warm_reserve
            _warm_reserve = None
    if acquired_proxy is not None:
        proxy = acquired_proxy
        await asyncio.to_thread(_save_mapping, user_id, proxy.id, created=True)
        SANDBOX_BACKENDS[user_id] = proxy
        asyncio.create_task(_replenish_warm())
        return proxy

    # 第三优先级：在跨进程持久化记录中查找既有沙箱 ID。
    mapping = await asyncio.to_thread(_get_mapping, user_id)
    if mapping and mapping.get("sandbox_id"):
        sandbox_id = mapping["sandbox_id"]
        try:
            from agent.backends.sandbox_setup import setup_sandbox
            sandbox_backend = await setup_sandbox(
                SANDBOX_CONFIG, sandbox_id=sandbox_id
            )
            result = await sandbox_backend.aexecute("echo ok")
            if result.exit_code != 0:
                raise RuntimeError(result.output[:200])

            proxy = SandboxBackendProxy(sandbox_backend)
            SANDBOX_BACKENDS[user_id] = proxy
            await asyncio.to_thread(_touch_mapping, user_id)
            return proxy
        except Exception:
            logger.warning("Failed to reconnect sandbox %s", sandbox_id, exc_info=True)
            return await _recreate_sandbox(user_id, None)

    return await _create_sandbox_for_user(user_id)


async def ping_user_sandbox(user_id: str) -> bool:
    """Check whether the cached user sandbox is healthy."""
    proxy = SANDBOX_BACKENDS.get(user_id)
    if proxy is None:
        return False
    try:
        result = await proxy.aexecute("echo ok")
        if result.exit_code != 0:
            return False
        await asyncio.to_thread(_touch_mapping, user_id)
        return True
    except Exception:
        return False


async def recreate_user_sandbox(user_id: str) -> SandboxBackendProxy:
    """Recreate a user sandbox after a health check failure."""
    return await _recreate_sandbox(user_id, SANDBOX_BACKENDS.get(user_id))


async def cleanup_user(user_id: str) -> None:
    """Delete a user's sandbox and its PostgreSQL registry mapping."""
    proxy = SANDBOX_BACKENDS.pop(user_id, None)
    if proxy is not None:
        try:
            await _kill_remote_sandbox(proxy.id)
        except Exception:
            logger.warning("Failed to delete sandbox %s", proxy.id, exc_info=True)
    await asyncio.to_thread(_delete_mapping, user_id)


async def shutdown() -> None:
    """Delete managed sandboxes without closing the shared PostgreSQL pool."""
    global _warm_reserve
    if _warm_reserve is not None:
        try:
            await _kill_remote_sandbox(_warm_reserve.id)
        except Exception:
            logger.warning("Failed to delete warm sandbox", exc_info=True)
        _warm_reserve = None
    for user_id in list(SANDBOX_BACKENDS):
        await cleanup_user(user_id)


async def _create_sandbox_for_user(user_id: str) -> SandboxBackendProxy:
    """Create a sandbox and persist its user mapping."""
    from agent.backends.sandbox_setup import setup_sandbox
    sandbox_backend = await setup_sandbox(SANDBOX_CONFIG)
    proxy = SandboxBackendProxy(sandbox_backend)
    SANDBOX_BACKENDS[user_id] = proxy
    await asyncio.to_thread(_save_mapping, user_id, proxy.id, created=True)
    logger.info("Created sandbox %s for user %s", proxy.id, user_id)
    return proxy


async def _recreate_sandbox(
    user_id: str,
    existing_proxy: SandboxBackendProxy | None,
) -> SandboxBackendProxy:
    """Create a replacement, swap the mapping, then remove the old sandbox."""
    from agent.backends.sandbox_setup import setup_sandbox

    old_id = existing_proxy.id if existing_proxy is not None else None
    if old_id is None:
        mapping = await asyncio.to_thread(_get_mapping, user_id)
        old_id = mapping.get("sandbox_id") if mapping else None

    sandbox_backend = await setup_sandbox(SANDBOX_CONFIG)
    if existing_proxy is not None:
        existing_proxy.replace_backend(sandbox_backend)
        proxy = existing_proxy
    else:
        proxy = SandboxBackendProxy(sandbox_backend)
        SANDBOX_BACKENDS[user_id] = proxy

    await asyncio.to_thread(_save_mapping, user_id, proxy.id)
    if old_id and old_id != proxy.id:
        try:
            await _kill_remote_sandbox(old_id)
        except Exception:
            logger.warning("Failed to delete old sandbox %s", old_id, exc_info=True)
    logger.info("Recreated sandbox %s for user %s", proxy.id, user_id)
    return proxy


async def _replenish_warm() -> None:
    """Create a replacement warm sandbox in the background."""
    global _warm_reserve
    if _warm_reserve is not None:
        return
    try:
        from agent.backends.sandbox_setup import setup_sandbox
        sandbox_backend = await setup_sandbox(SANDBOX_CONFIG)
        async with _warm_lock:
            if _warm_reserve is None:
                _warm_reserve = SandboxBackendProxy(sandbox_backend)
                logger.info("Replenished warm sandbox: %s", sandbox_backend.id)
    except Exception:
        logger.warning("Failed to replenish warm sandbox", exc_info=True)
