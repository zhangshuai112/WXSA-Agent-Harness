"""
WeCom Ops Harness Web API
基于 FastAPI 的 Web API 服务，用于与 企微运营 Harness 进行交互
"""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import json
import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from dotenv import load_dotenv
from wecom_agent_api.wecom_agent_api import (
    WecomAgentAPI,
    adapt_stream_chunk,
    build_agent_context,
    build_messages_input,
    extract_task_result_from_values,
    resolve_user_message,
    run_to_dict,
)

# 复用 Harness Agent 的运行限制器
import sys
from pathlib import Path

_AGENT_SRC = Path(__file__).resolve().parents[1] / "Harness_hand_write" / "src"
if _AGENT_SRC.is_dir() and str(_AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_SRC))

from agent.runtime.run_limits import (  # noqa: E402
    AgentRunLimitExceeded,
    AgentRunLimitTracker,
    infer_task_kind,
    watch_stream,
)

# FastAPI：创建 Web 应用的核心类。
# HTTPException：在接口中抛出 HTTP 错误用。
# Depends：依赖注入，用于认证等。
# status：内置的 HTTP 状态码常量。
# HTTPBearer / HTTPAuthorizationCredentials：用于 Bearer Token 鉴权（JWT）。
# CORSMiddleware：处理跨域请求。
# StreamingResponse：返回流式响应（SSE 风格）。
# StaticFiles：挂载静态文件目录（前端页面）。
# BaseModel, Field：Pydantic 数据模型和字段定义。
# Dict, List, Optional, Any：类型注解。
# json, os：标准库，用于 JSON 处理、环境变量读取。
# datetime, timedelta：处理过期时间。
# JWTError, jwt：使用 python-jose 进行 JWT 编解码。
# WecomAgentAPI：你自定义的类，用来连接后台的 企微运营 Harness / LangGraph 服务。

# load_dotenv：从 .env 文件加载环境变量。
load_dotenv()

#创建一个 FastAPI 应用实例，并设置文档标题、描述和版本号。
app = FastAPI(
    title="WeCom Ops Harness Web API",
    description="WeCom Ops Harness Web API 服务",
    version="1.0.0"
)


#给应用添加 CORS 中间件。CORS中间件的作用包括: 1.解决前端页面和后端api的跨域请求问题（CORS中间件通过在响应中添加特定的HTTP头部，告诉浏览器这个请求是被允许的。）
#2. 控制跨域访问权限：通过配置参数，可以精确控制哪些来源（域名）可以访问API，哪些HTTP方法可以使用，以及允许携带哪些请求头。
# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制具体的域名,allow_origins=["*"]：允许任何来源跨域访问（开发方便，生产应限制）
    allow_credentials=True,#允许携带 cookie
    allow_methods=["*"],#任意方法
    allow_headers=["*"],#任意头部
)

# 挂载静态文件目录，使前端能够通过浏览器使用url直接访问到路径下的静态文件
#app.mount("/wecom_web"挂载路径, StaticFiles(directory="./wecom_web"文件路径), name="wecom_web"内部名称)
app.mount("/wecom_web", StaticFiles(directory="./wecom_web"), name="wecom_web")

# 安全认证
security = HTTPBearer()

# 全局变量存储客户端连接
clients: Dict[str, WecomAgentAPI] = {}

# LangGraph / Agent 配置
LANGGRAPH_SERVER_URL = os.getenv("LANGGRAPH_SERVER_URL") or os.getenv("WECOM_SERVER_URL") or "http://127.0.0.1:2024"
LANGGRAPH_GRAPH_ID = os.getenv("LANGGRAPH_GRAPH_ID") or os.getenv("WECOM_GRAPH_ID") or "agent"
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY") or os.getenv("LANGSMITH_API_KEY")

# Web配置
WEB_USER_ID=os.getenv("WEB_USER_ID")
WEB_PASSWORD=os.getenv("WEB_PASSWORD")

# JWT配置
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# 业务DEMO配置
EXTERNAL_ID = os.getenv("EXTERNAL_ID")

# 请求模型
class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

class SendMessageRequest(BaseModel):
    message: Optional[str] = Field(None, description="消息内容")
    menu_id: Optional[str] = Field(None, description="菜单ID，如果是点击菜单触发")

class InterruptConfirmRequest(BaseModel):
    confirmed: str = Field(..., description="确认结果: ok, discard, recreate")


class LoginResponse(BaseModel):
    success: bool = Field(..., description="登录是否成功")
    token: str = Field(default="", description="访问令牌")
    message: str = Field(default="", description="响应消息")


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _run_status(run: Any) -> str:
    if isinstance(run, dict):
        return str(run.get("status") or "")
    return str(getattr(run, "status", "") or "")


def _run_id(run: Any) -> Optional[str]:
    if isinstance(run, dict):
        return run.get("run_id")
    return getattr(run, "run_id", None)


async def _find_active_run(client: WecomAgentAPI, thread_id: str):
    """返回 thread 上最新的 pending/running run（若有）。"""
    try:
        runs = await client.list_runs(thread_id)
    except Exception:
        return None
    for run in runs or []:
        if _run_status(run) in {"pending", "running"}:
            return run
    return None


async def _sse_from_run_stream(
    stream,
    tracker: AgentRunLimitTracker,
    *,
    client: Optional[WecomAgentAPI] = None,
    thread_id: Optional[str] = None,
):
    """将 join_stream 事件转为 SSE data 行。

    流结束后再从 thread state 补发一次最终结果：join_stream 可能只推送
    updates、或结束后不回放 messages/values，避免前端一直停在「正在处理」。
    """
    try:
        async for chunk in watch_stream(stream, tracker):
            chunk_data = adapt_stream_chunk(chunk)
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
    except AgentRunLimitExceeded as exc:
        error_data = {"event": "error", "data": exc.to_dict()}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    except Exception as e:
        error_data = {"event": "error", "data": {"error": str(e)}}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    finally:
        if client is None or not thread_id:
            return
        try:
            state = await client.get_thread_state(thread_id)
            values = state.get("values") if isinstance(state, dict) else None
            task_result = extract_task_result_from_values(values)
            if task_result:
                final_event = {
                    "event": "values",
                    "data": {"task_result": task_result},
                }
                yield f"data: {json.dumps(final_event, ensure_ascii=False)}\n\n"
        except Exception:
            # 补发失败不影响主流程；前端仍可刷新走 thread_status
            pass

# JWT工具函数
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> dict:
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的访问令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

# 工具函数
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """获取当前用户"""
    token = credentials.credentials
    payload = verify_token(token)
    username = payload.get("sub")
    
    # 检查是否有对应的WECOM客户端连接
    if token not in clients:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="会话已过期，请重新登录"
        )
    return token, username

async def get_client(token: str) -> WecomAgentAPI:
    """获取客户端实例"""
    if token not in clients:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="客户端未连接"
        )
    return clients[token]

# API 路由
@app.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """用户登录 - 使用独立的Web账号验证"""
    try:
        # 验证Web服务账号（不是WECOM账号）
        if request.username != WEB_USER_ID or request.password != WEB_PASSWORD:
            return LoginResponse(
                success=False,
                message="用户名或密码错误"
            )
        
        # Web 账号验证成功后，连接 LangGraph Server（langgraph dev）
        client = WecomAgentAPI()
        success = await client.connect(
            wecom_server_url=LANGGRAPH_SERVER_URL,
            api_key=LANGGRAPH_API_KEY,
        )
        
        if success:
            # 生成JWT令牌
            access_token_expires = timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": request.username},
                expires_delta=access_token_expires
            )
            clients[access_token] = client
            
            return LoginResponse(
                success=True,
                token=access_token,
                message="登录成功"
            )
        else:
            return LoginResponse(
                success=False,
                message="后端服务连接失败，请稍后重试"
            )
            
    except Exception as e:
        return LoginResponse(
            success=False,
            message=f"登录失败: {str(e)}"
        )

@app.post("/api/logout")
async def logout(user_info = Depends(get_current_user)):
    """用户登出"""
    try:
        token, username = user_info
        if token in clients:
            await clients[token].disconnect()
            del clients[token]
        return {"success": True, "message": "登出成功"}
    except Exception as e:
        return {"success": False, "message": f"登出失败: {str(e)}"}

@app.post("/api/send_message")
async def send_message(request: SendMessageRequest, user_info=Depends(get_current_user)):
    """创建后台 Agent run，立即返回 thread_id/run_id（不阻塞在 SSE 上）。"""
    try:
        token, username = user_info
        client = await get_client(token)

        web_user_id = username
        agent_context = build_agent_context(web_user_id, EXTERNAL_ID, username=web_user_id)
        assistant_id = await client.create_assistant(
            graph_id=LANGGRAPH_GRAPH_ID,
            external_id=EXTERNAL_ID,
            user_id=web_user_id,
        )

        thread_id = await client.create_thread(
            user_id=web_user_id,
            external_id=EXTERNAL_ID,
        )
        if not thread_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建 thread 失败",
            )

        active = await _find_active_run(client, thread_id)
        if active is not None:
            return {
                "success": True,
                "already_running": True,
                "thread_id": thread_id,
                "run_id": _run_id(active),
                "status": _run_status(active),
                "message": "已有任务在运行，请订阅现有 run",
            }

        try:
            user_text = resolve_user_message(message=request.message, menu_id=request.menu_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        input_data = build_messages_input(user_text)

        try:
            run = await client.create_background_run(
                thread_id=thread_id,
                assistant_id=assistant_id,
                input=input_data,
                context=agent_context,
            )
        except Exception as exc:
            # multitask reject 等：回落查是否已有活跃 run
            active = await _find_active_run(client, thread_id)
            if active is not None:
                return {
                    "success": True,
                    "already_running": True,
                    "thread_id": thread_id,
                    "run_id": _run_id(active),
                    "status": _run_status(active),
                    "message": f"未能新建 run，已返回进行中的任务: {exc}",
                }
            raise

        run_info = run_to_dict(run)
        return {
            "success": True,
            "already_running": False,
            "thread_id": thread_id,
            "run_id": run_info.get("run_id"),
            "status": run_info.get("status") or "pending",
            "assistant_id": assistant_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发送消息失败: {str(e)}",
        )


@app.get("/api/join_stream")
async def join_stream(
    run_id: str,
    last_event_id: Optional[str] = None,
    user_info=Depends(get_current_user),
):
    """订阅已有 run 的 SSE 流；断开连接不会取消 Server 上的 run。"""
    try:
        token, username = user_info
        client = await get_client(token)
        web_user_id = username
        thread_id = await client.get_thread_id(
            user_id=web_user_id,
            external_id=EXTERNAL_ID,
        )
        if not run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="run_id 不能为空",
            )

        stream = await client.join_run_stream(
            thread_id=thread_id,
            run_id=run_id,
            last_event_id=last_event_id,
        )
        tracker = AgentRunLimitTracker(task_kind="default")
        return StreamingResponse(
            _sse_from_run_stream(
                stream,
                tracker,
                client=client,
                thread_id=thread_id,
            ),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"订阅 run 失败: {str(e)}",
        )


@app.get("/api/thread_status")
async def thread_status(user_info=Depends(get_current_user)):
    """查询当前用户 thread 最新 run 状态，供页面重开后同步。"""
    try:
        token, username = user_info
        client = await get_client(token)
        web_user_id = username
        thread_id = await client.get_thread_id(
            user_id=web_user_id,
            external_id=EXTERNAL_ID,
        )

        try:
            runs = await client.list_runs(thread_id)
        except Exception:
            runs = []

        if not runs:
            return {
                "status": "idle",
                "thread_id": thread_id,
                "run_id": None,
                "task_result": None,
                "interrupts": None,
            }

        latest = runs[0]
        latest_info = run_to_dict(latest)
        status_name = latest_info.get("status") or "idle"
        run_id = latest_info.get("run_id")

        if status_name in {"pending", "running"}:
            return {
                "status": status_name,
                "thread_id": thread_id,
                "run_id": run_id,
                "task_result": None,
                "interrupts": None,
            }

        interrupts = await client.get_interrupts_from_thread(thread_id)
        if interrupts or status_name == "interrupted":
            return {
                "status": "interrupted",
                "thread_id": thread_id,
                "run_id": run_id,
                "task_result": None,
                "interrupts": interrupts,
            }

        task_result = None
        try:
            state = await client.get_thread_state(thread_id)
            values = state.get("values") if isinstance(state, dict) else None
            task_result = extract_task_result_from_values(values)
        except Exception:
            task_result = None

        return {
            "status": status_name or "idle",
            "thread_id": thread_id,
            "run_id": run_id,
            "task_result": task_result,
            "interrupts": None,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询 thread 状态失败: {str(e)}",
        )


@app.get("/api/get_interrupt")
async def get_interrupt(user_info=Depends(get_current_user)):
    """获取中断信息"""
    try:
        token, username = user_info
        client = await get_client(token)

        web_user_id = username
        thread_id = await client.get_thread_id(
            user_id=web_user_id,
            external_id=EXTERNAL_ID,
        )

        if not thread_id:
            return {"has_interrupt": False, "interrupt_info": None}

        has_interrupt = await client.has_interrupts(thread_id)

        if has_interrupt:
            interrupts = await client.get_interrupts_from_thread(thread_id)
            return {
                "has_interrupt": True,
                "interrupt_info": interrupts,
            }
        return {"has_interrupt": False, "interrupt_info": None}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取中断信息失败: {str(e)}",
        )


@app.post("/api/confirm_interrupt")
async def confirm_interrupt(
    request: InterruptConfirmRequest,
    user_info=Depends(get_current_user),
):
    """确认中断：后台 create resume run，返回 run_id 供前端 join_stream。"""
    try:
        token, username = user_info
        client = await get_client(token)

        web_user_id = username
        agent_context = build_agent_context(web_user_id, EXTERNAL_ID, username=web_user_id)
        assistant_id = await client.create_assistant(
            graph_id=LANGGRAPH_GRAPH_ID,
            external_id=EXTERNAL_ID,
            user_id=web_user_id,
        )

        thread_id = await client.get_thread_id(
            user_id=web_user_id,
            external_id=EXTERNAL_ID,
        )

        confirmed = {"confirmed": request.confirmed}
        command = {"resume": confirmed}

        run = await client.create_background_run(
            thread_id=thread_id,
            assistant_id=assistant_id,
            command=command,
            context=agent_context,
            multitask_strategy="interrupt",
        )
        run_info = run_to_dict(run)
        return {
            "success": True,
            "thread_id": thread_id,
            "run_id": run_info.get("run_id"),
            "status": run_info.get("status") or "pending",
            "assistant_id": assistant_id,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"确认中断失败: {str(e)}",
        )


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "message": "WeCom Ops Harness Web API 运行正常"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
