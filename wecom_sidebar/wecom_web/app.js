// 主页面 JavaScript
class WecomApp {
    constructor() {
        this.apiBaseUrl = '/api';
        this.token = localStorage.getItem('wecom_token');
        this.username = localStorage.getItem('wecom_username');
        this.currentStream = null;
        this.isProcessing = false;
        this.lastNodeResults = new Map(); // 存储最新的节点结果，避免重复显示
        this.currentTaskActive = false; // 当前是否有活跃任务
        this.taskStartTime = null; // 任务开始时间
        this.activeRunId = localStorage.getItem('wecom_active_run_id');
        this.activeThreadId = localStorage.getItem('wecom_active_thread_id');
        this.lastEventId = localStorage.getItem('wecom_last_event_id') || null;
        this._streamAbort = null;

        this.init();
    }

    init() {
        // 检查登录状态
        if (!this.token) {
            this.redirectToLogin();
            return;
        }

        this.bindEvents();
        this.enableInput();
        this.startInterruptCheck();
        // 页面打开：同步服务端 run 状态（关页后任务可能仍在跑）
        this.syncOnLoad();
    }

    bindEvents() {
        document.getElementById('logoutBtn').addEventListener('click', () => {
            this.logout();
        });

        document.getElementById('sendBtn').addEventListener('click', () => {
            this.sendMessage();
        });

        document.getElementById('messageInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        document.querySelectorAll('.menu-item').forEach(item => {
            item.addEventListener('click', () => {
                const menuId = item.dataset.menu;
                this.handleMenuClick(menuId, item);
            });
        });

        document.querySelectorAll('.confirm-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                this.confirmInterrupt(action);
            });
        });
    }

    saveActiveRun(threadId, runId) {
        this.activeThreadId = threadId || null;
        this.activeRunId = runId || null;
        if (threadId) {
            localStorage.setItem('wecom_active_thread_id', threadId);
        } else {
            localStorage.removeItem('wecom_active_thread_id');
        }
        if (runId) {
            localStorage.setItem('wecom_active_run_id', runId);
        } else {
            localStorage.removeItem('wecom_active_run_id');
        }
    }

    clearActiveRun() {
        this.saveActiveRun(null, null);
        this.lastEventId = null;
        localStorage.removeItem('wecom_last_event_id');
    }

    async logout() {
        try {
            if (this._streamAbort) {
                this._streamAbort.abort();
            }
            await fetch(`${this.apiBaseUrl}/logout`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
        } catch (error) {
            console.error('登出请求失败:', error);
        }

        localStorage.removeItem('wecom_token');
        localStorage.removeItem('wecom_username');
        this.clearActiveRun();

        this.redirectToLogin();
    }

    redirectToLogin() {
        window.location.href = 'login.html';
    }

    enableInput() {
        this.isProcessing = false;
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');

        messageInput.disabled = false;
        sendBtn.disabled = false;
        sendBtn.textContent = '发送';
        messageInput.placeholder = '请输入您的问题...';

        document.getElementById('progressArea').style.display = 'none';

        this.finalizeCurrentTask();

        this.lastNodeResults.clear();
        this.currentTaskActive = false;
        this.taskStartTime = null;
    }

    disableInput() {
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');

        messageInput.disabled = true;
        sendBtn.disabled = true;
        messageInput.placeholder = 'Agent 正在处理中...';
        messageInput.value = '';

        this.showProgress('正在处理中...');
        this.startNewTask();
    }

    startNewTask() {
        if (this.currentTaskActive) {
            return;
        }

        const displayArea = document.getElementById('displayArea');
        if (displayArea.children.length > 1) {
            this.addTaskSeparator();
        }

        this.currentTaskActive = true;
        this.taskStartTime = new Date();

        document.getElementById('currentTaskArea').style.display = 'block';
        document.getElementById('currentTaskContent').innerHTML = '<div class="task-loading">正在处理任务...</div>';
    }

    finalizeCurrentTask() {
        if (!this.currentTaskActive) return;

        const currentTaskContent = document.getElementById('currentTaskContent');
        if (currentTaskContent && currentTaskContent.innerHTML.trim()) {
            const displayArea = document.getElementById('displayArea');
            const taskHistoryDiv = document.createElement('div');
            taskHistoryDiv.className = 'message agent task-history';
            taskHistoryDiv.innerHTML = currentTaskContent.innerHTML;
            displayArea.appendChild(taskHistoryDiv);
            displayArea.scrollTop = displayArea.scrollHeight;
        }

        document.getElementById('currentTaskArea').style.display = 'none';
        this.currentTaskActive = false;
    }

    addTaskSeparator() {
        const displayArea = document.getElementById('displayArea');
        const separator = document.createElement('div');
        separator.className = 'task-separator';

        const now = new Date();
        const timeString = now.toLocaleTimeString('zh-CN', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        separator.innerHTML = `<span class="task-separator-text">任务执行时间：${timeString}</span>`;
        displayArea.appendChild(separator);
        displayArea.scrollTop = displayArea.scrollHeight;
    }

    async syncOnLoad() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/thread_status`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            if (!response.ok) {
                return;
            }
            const info = await response.json();
            const statusName = info.status;

            if (statusName === 'pending' || statusName === 'running') {
                this.addMessage('检测到进行中的任务，正在恢复进度…', 'system');
                this.disableInput();
                this.isProcessing = true;
                this.saveActiveRun(info.thread_id, info.run_id);
                try {
                    await this.subscribeRun(info.run_id);
                } catch (error) {
                    console.error('恢复订阅失败:', error);
                    this.addMessage('恢复任务进度失败: ' + error.message, 'error');
                } finally {
                    this.enableInput();
                    this.isProcessing = false;
                    this.clearActiveRun();
                }
                return;
            }

            if (statusName === 'interrupted' && info.interrupts) {
                this.showInterrupt(info.interrupts);
                return;
            }

            if ((statusName === 'success' || statusName === 'error') && info.task_result) {
                this.disableInput();
                this.handleTaskResult(info.task_result);
                if (statusName === 'error') {
                    this.addMessage('上次任务已结束（含错误），已加载最终状态', 'system');
                } else {
                    this.addMessage('已加载上次任务结果', 'system');
                }
                this.enableInput();
                this.clearActiveRun();
            }
        } catch (error) {
            console.error('进页同步失败:', error);
        }
    }

    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();

        if (!message || this.isProcessing) {
            return;
        }

        messageInput.value = '';
        this.disableInput();
        this.isProcessing = true;
        this.addMessage(message, 'user');

        try {
            await this.streamMessage({ message: message });
        } catch (error) {
            console.error('发送消息失败:', error);
            this.addMessage('发送失败: ' + error.message, 'error');
        } finally {
            this.enableInput();
            this.isProcessing = false;
            this.clearActiveRun();
        }
    }

    async handleMenuClick(menuId, menuElement) {
        if (this.isProcessing) {
            return;
        }

        document.querySelectorAll('.menu-item').forEach(item => {
            item.classList.remove('active');
        });
        menuElement.classList.add('active');

        const messageInput = document.getElementById('messageInput');
        messageInput.value = menuId;

        this.disableInput();
        this.isProcessing = true;
        this.addMessage(`正在执行: ${this.getMenuName(menuId)}`, 'system');

        try {
            await this.streamMessage({ menu_id: menuId });
        } catch (error) {
            console.error('菜单操作失败:', error);
            this.addMessage('操作失败: ' + error.message, 'error');
        } finally {
            this.enableInput();
            this.isProcessing = false;
            this.clearActiveRun();
            messageInput.value = '';
            menuElement.classList.remove('active');
        }
    }

    getMenuName(menuId) {
        const menuNames = {
            'profile_suggestion': '生成客户画像',
            'tag_suggestion': '生成客户标签',
            'chat_suggestion': '生成聊天建议',
            'kf_chat_suggestion': '生成客服建议',
            'schedule_suggestion': '生成日程建议'
        };
        return menuNames[menuId] || menuId;
    }

    async streamMessage(data) {
        const createResp = await fetch(`${this.apiBaseUrl}/send_message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.token}`
            },
            body: JSON.stringify(data)
        });

        if (!createResp.ok) {
            const errText = await createResp.text();
            throw new Error(`HTTP ${createResp.status}: ${errText || createResp.statusText}`);
        }

        const created = await createResp.json();
        if (!created.run_id) {
            throw new Error(created.message || '未返回 run_id');
        }
        if (created.already_running) {
            this.addMessage('已有任务在运行，改为订阅现有进度', 'system');
        }

        this.saveActiveRun(created.thread_id, created.run_id);
        await this.subscribeRun(created.run_id);
    }

    async subscribeRun(runId, lastEventId = null) {
        if (!runId) {
            throw new Error('run_id 为空，无法订阅');
        }

        const url = new URL(`${window.location.origin}${this.apiBaseUrl}/join_stream`);
        url.searchParams.set('run_id', runId);
        const resumeId = lastEventId || this.lastEventId;
        if (resumeId) {
            url.searchParams.set('last_event_id', resumeId);
        }

        if (this._streamAbort) {
            this._streamAbort.abort();
        }
        this._streamAbort = new AbortController();

        const response = await fetch(url.toString(), {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${this.token}`
            },
            signal: this._streamAbort.signal
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errText || response.statusText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('id: ')) {
                    this.lastEventId = line.slice(4).trim();
                    localStorage.setItem('wecom_last_event_id', this.lastEventId);
                    continue;
                }
                if (line.startsWith('data: ')) {
                    try {
                        const jsonData = JSON.parse(line.slice(6));
                        this.handleStreamData(jsonData);
                    } catch (e) {
                        console.error('解析流数据失败:', e, line);
                    }
                }
            }
        }

        if (buffer && buffer.startsWith('data: ')) {
            try {
                const jsonData = JSON.parse(buffer.slice(6));
                this.handleStreamData(jsonData);
            } catch (e) {
                // ignore trailing incomplete
            }
        }

        // 流结束后若仍无正文（旧后端 / 丢事件），用 thread_status 兜底拉最终结果
        if (!this._hasTaskResultContent()) {
            await this.loadFinalTaskResult();
        }
    }

    _hasTaskResultContent() {
        const currentTaskContent = document.getElementById('currentTaskContent');
        if (!currentTaskContent) {
            return false;
        }
        const text = (currentTaskContent.textContent || '').trim();
        return Boolean(text) && text !== '正在处理任务...';
    }

    async loadFinalTaskResult() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/thread_status`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            if (!response.ok) {
                return;
            }
            const info = await response.json();
            if (info.task_result) {
                this.handleTaskResult(info.task_result);
            }
        } catch (error) {
            console.error('拉取最终任务结果失败:', error);
        }
    }

    handleStreamData(data) {
        console.log('收到流数据:', data);

        if (data.event === 'error') {
            const errMsg = (data.data && (data.data.error || data.data.message)) || '未知错误';
            this.addMessage('错误: ' + errMsg, 'error');
            return;
        }

        if (data.event === 'messages' && data.data) {
            const messageChunk = Array.isArray(data.data) ? data.data[data.data.length - 1] : data.data;
            const content = typeof messageChunk?.content === 'string'
                ? messageChunk.content
                : '';
            if (content) {
                this.handleTaskResult({
                    task_result: content,
                    task_result_explain: '',
                    task_result_code: 0
                });
            }
            return;
        }

        if (data.event === 'values' && data.data) {
            if (data.data.task_result) {
                this.handleTaskResult(data.data.task_result);
            }

            if (data.data.node_result && Array.isArray(data.data.node_result)) {
                const latestNodeResult = data.data.node_result[data.data.node_result.length - 1];
                if (latestNodeResult) {
                    this.updateProgress(latestNodeResult);
                }
            }
        }
    }

    addMessage(content, type = 'agent') {
        const displayArea = document.getElementById('displayArea');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = content;

        displayArea.appendChild(messageDiv);
        displayArea.scrollTop = displayArea.scrollHeight;
    }

    handleTaskResult(taskResult) {
        if (!this.currentTaskActive) {
            this.startNewTask();
        }
        this.updateCurrentTaskContent(taskResult);
    }

    updateCurrentTaskContent(taskResult) {
        const currentTaskContent = document.getElementById('currentTaskContent');
        if (!currentTaskContent) return;

        let contentHtml = '';

        if (taskResult.task_result) {
            if (this.isJsonString(taskResult.task_result)) {
                try {
                    const parsed = JSON.parse(taskResult.task_result);
                    if (parsed.profile_items && Array.isArray(parsed.profile_items)) {
                        contentHtml += this.formatProfileContent(parsed.profile_items);
                    } else {
                        contentHtml += `<div class="task-result-item">
                            <div class="task-result-main json-content">${JSON.stringify(parsed, null, 2)}</div>
                        </div>`;
                    }
                } catch (e) {
                    contentHtml += `<div class="task-result-item">
                        <div class="task-result-main">${taskResult.task_result}</div>
                    </div>`;
                }
            } else if (taskResult.task_result.includes('profile_items') || taskResult.task_result.includes('客户profile')) {
                const jsonMatch = taskResult.task_result.match(/\{[\s\S]*\}/);
                if (jsonMatch) {
                    try {
                        const parsed = JSON.parse(jsonMatch[0]);
                        if (parsed.profile_items && Array.isArray(parsed.profile_items)) {
                            contentHtml += this.formatProfileContent(parsed.profile_items);
                        } else {
                            contentHtml += `<div class="task-result-item">
                                <div class="task-result-main">${taskResult.task_result}</div>
                            </div>`;
                        }
                    } catch (e) {
                        contentHtml += `<div class="task-result-item">
                            <div class="task-result-main">${taskResult.task_result}</div>
                        </div>`;
                    }
                } else {
                    contentHtml += `<div class="task-result-item">
                        <div class="task-result-main">${taskResult.task_result}</div>
                    </div>`;
                }
            } else {
                contentHtml += `<div class="task-result-item">
                    <div class="task-result-main">${taskResult.task_result}</div>
                </div>`;
            }
        }

        if (taskResult.task_result_explain) {
            contentHtml += `<div class="task-result-item">
                <div class="task-result-explain">💡 ${taskResult.task_result_explain}</div>
            </div>`;
        }

        currentTaskContent.innerHTML = contentHtml;
    }

    formatProfileContent(profileItems) {
        let html = `<div class="task-result-item">
            <div class="task-result-main">
                <h4 style="margin: 0 0 10px 0; color: #2e7d32;">📋 客户画像更新成功</h4>
                <div class="profile-table">`;

        profileItems.forEach(item => {
            html += `<div class="profile-row">
                <span class="profile-label">${item.item_name}:</span>
                <span class="profile-value">${item.item_value}</span>
            </div>`;
        });

        html += `</div></div></div>`;
        return html;
    }

    isJsonString(str) {
        try {
            const parsed = JSON.parse(str);
            return typeof parsed === 'object' && parsed !== null;
        } catch (e) {
            return false;
        }
    }

    updateProgress(nodeResult) {
        const nodeKey = `${nodeResult.execute_node_name}_${nodeResult.execute_result_msg}`;
        if (this.lastNodeResults.has(nodeKey)) {
            return;
        }

        this.lastNodeResults.set(nodeKey, nodeResult);

        const progressText = nodeResult.execute_result_msg || nodeResult.execute_node_name;
        this.showProgress(progressText);

        if (nodeResult.execute_result_code !== 0 ||
            (nodeResult.execute_exceptions && nodeResult.execute_exceptions.length > 0)) {
            this.showProgress(`错误: ${progressText}`, 'error');
        }
    }

    async startInterruptCheck() {
        setInterval(async () => {
            if (!this.isProcessing) {
                await this.checkInterrupt();
            }
        }, 3000);
    }

    async checkInterrupt() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/get_interrupt`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.has_interrupt && data.interrupt_info) {
                    this.showInterrupt(data.interrupt_info);
                }
            }
        } catch (error) {
            console.error('检查中断失败:', error);
        }
    }

    showInterrupt(interruptInfo) {
        const interruptArea = document.getElementById('interruptArea');
        const interruptDescription = document.getElementById('interruptDescription');

        let description = '需要您的确认';
        let fullContent = '';

        if (interruptInfo && typeof interruptInfo === 'object') {
            const firstKey = Object.keys(interruptInfo)[0];
            if (firstKey && interruptInfo[firstKey] && interruptInfo[firstKey][0]) {
                const interruptData = interruptInfo[firstKey][0].value;
                if (interruptData) {
                    if (interruptData.description) {
                        description = interruptData.description;
                    }

                    fullContent = description;

                    if (interruptData.new_profile && interruptData.new_profile.profile_items) {
                        const profileItems = interruptData.new_profile.profile_items;
                        fullContent += '\n\n📋 客户画像预览：\n';
                        profileItems.slice(0, 5).forEach(item => {
                            fullContent += `• ${item.item_name}: ${item.item_value}\n`;
                        });
                        if (profileItems.length > 5) {
                            fullContent += `... 还有 ${profileItems.length - 5} 项信息`;
                        }
                    }

                    if (interruptData.new_tags) {
                        fullContent += '\n\n🏷️ 标签建议预览：\n';

                        if (interruptData.new_tags.tag_ids_add && interruptData.new_tags.tag_ids_add.length > 0) {
                            fullContent += '\n➕ 建议添加标签：\n';
                            interruptData.new_tags.tag_ids_add.slice(0, 3).forEach(tag => {
                                fullContent += `• ${tag.tag_name} (${tag.tag_id})\n`;
                                if (tag.tag_reason) {
                                    fullContent += `  理由：${tag.tag_reason.substring(0, 50)}...\n`;
                                }
                            });
                            if (interruptData.new_tags.tag_ids_add.length > 3) {
                                fullContent += `... 还有 ${interruptData.new_tags.tag_ids_add.length - 3} 个标签\n`;
                            }
                        }

                        if (interruptData.new_tags.tag_ids_remove && interruptData.new_tags.tag_ids_remove.length > 0) {
                            fullContent += '\n➖ 建议移除标签：\n';
                            interruptData.new_tags.tag_ids_remove.forEach(tag => {
                                fullContent += `• ${tag.tag_name} (${tag.tag_id})\n`;
                            });
                        }
                    }

                    if (interruptData.old_profile && interruptData.old_profile.profile_items && interruptData.old_profile.profile_items.length > 0) {
                        fullContent += '\n\n📝 将替换现有客户信息';
                    }

                    if (interruptData.old_tags && interruptData.old_tags.customer_tags && interruptData.old_tags.customer_tags.length > 0) {
                        fullContent += '\n\n📝 当前客户标签数量：' + interruptData.old_tags.customer_tags.length + ' 个';
                    }
                }
            }
        }

        interruptDescription.innerHTML = fullContent.replace(/\n/g, '<br>');
        interruptArea.style.display = 'block';

        this.disableInput();
    }

    hideInterrupt() {
        const interruptArea = document.getElementById('interruptArea');
        interruptArea.style.display = 'none';
        this.enableInput();
    }

    async confirmInterrupt(action) {
        try {
            this.hideInterrupt();
            this.disableInput();
            this.isProcessing = true;

            this.addMessage(`您选择了: ${this.getActionName(action)}`, 'system');

            const response = await fetch(`${this.apiBaseUrl}/confirm_interrupt`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.token}`
                },
                body: JSON.stringify({
                    confirmed: action
                })
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errText || response.statusText}`);
            }

            const created = await response.json();
            if (!created.run_id) {
                throw new Error(created.message || '确认中断未返回 run_id');
            }
            this.saveActiveRun(created.thread_id, created.run_id);
            await this.subscribeRun(created.run_id);
        } catch (error) {
            console.error('确认中断失败:', error);
            this.addMessage('确认失败: ' + error.message, 'error');
        } finally {
            this.enableInput();
            this.isProcessing = false;
            this.clearActiveRun();
        }
    }

    getActionName(action) {
        const actionNames = {
            'ok': '确认',
            'discard': '放弃',
            'recreate': '重新生成'
        };
        return actionNames[action] || action;
    }

    showProgress(text, type = 'normal') {
        const progressArea = document.getElementById('progressArea');
        const progressText = document.getElementById('progressText');
        const progressIcon = progressArea.querySelector('.progress-icon');

        progressText.textContent = text;
        progressArea.style.display = 'block';

        if (type === 'error') {
            progressArea.className = 'progress-area error';
            progressIcon.textContent = '❌';
        } else {
            progressArea.className = 'progress-area';
            progressIcon.textContent = '⚡';
        }
    }

    hideProgress() {
        const progressArea = document.getElementById('progressArea');
        progressArea.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new WecomApp();
});
