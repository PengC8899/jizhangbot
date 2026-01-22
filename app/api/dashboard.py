from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HYPay 管理后台</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-3xl font-bold text-gray-800">🤖 HYPay 机器人管理后台</h1>
            <div class="space-x-4">
                <button onclick="loadPendingRequests()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded shadow">
                    🔄 刷新申请
                </button>
            </div>
        </div>

        <!-- Dashboard Stats (Optional Placeholder) -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-gray-500 text-sm font-medium">待审核申请</h3>
                <p class="text-3xl font-bold text-orange-500" id="pendingCount">0</p>
            </div>
            <!-- Add more stats later -->
        </div>

        <!-- Pending Requests Section -->
        <div class="bg-white rounded-lg shadow overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-200">
                <h2 class="text-xl font-semibold text-gray-800">📝 试用申请列表</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">用户</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">申请时间</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200" id="requestsTableBody">
                        <!-- Data will be populated here -->
                    </tbody>
                </table>
            </div>
            <div id="emptyState" class="hidden p-8 text-center text-gray-500">
                暂无待审核申请
            </div>
        </div>
    </div>

    <!-- JavaScript Logic -->
    <script>
        const API_BASE = '/admin';

        async function loadPendingRequests() {
            try {
                const response = await axios.get(`${API_BASE}/trials/pending`);
                const requests = response.data;
                
                const tbody = document.getElementById('requestsTableBody');
                const emptyState = document.getElementById('emptyState');
                const pendingCount = document.getElementById('pendingCount');
                
                tbody.innerHTML = '';
                pendingCount.innerText = requests.length;

                if (requests.length === 0) {
                    emptyState.classList.remove('hidden');
                } else {
                    emptyState.classList.add('hidden');
                    requests.forEach(req => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">#${req.id}</td>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="flex items-center">
                                    <div>
                                        <div class="text-sm font-medium text-gray-900">${req.username || '未知'}</div>
                                        <div class="text-sm text-gray-500">ID: ${req.user_id}</div>
                                    </div>
                                </div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                ${new Date(req.created_at).toLocaleString()}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-2">
                                <button onclick="approveRequest(${req.id})" class="text-green-600 hover:text-green-900 bg-green-50 px-3 py-1 rounded">✅ 通过</button>
                                <button onclick="rejectRequest(${req.id})" class="text-red-600 hover:text-red-900 bg-red-50 px-3 py-1 rounded">❌ 拒绝</button>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });
                }
            } catch (error) {
                console.error('Failed to load requests:', error);
                Swal.fire('错误', '加载数据失败', 'error');
            }
        }

        async function approveRequest(id) {
            const { value: days } = await Swal.fire({
                title: '批准试用',
                input: 'number',
                inputLabel: '授权天数',
                inputValue: 1,
                showCancelButton: true,
                confirmButtonText: '确定批准',
                cancelButtonText: '取消',
                inputValidator: (value) => {
                    if (!value || value <= 0) {
                        return '请输入有效的天数！'
                    }
                }
            });

            if (days) {
                try {
                    await axios.post(`${API_BASE}/trials/${id}/approve?days=${days}`);
                    Swal.fire('成功', `已授权 ${days} 天`, 'success');
                    loadPendingRequests();
                } catch (error) {
                    Swal.fire('失败', '操作失败', 'error');
                }
            }
        }

        async function rejectRequest(id) {
            const result = await Swal.fire({
                title: '确认拒绝?',
                text: "此操作无法撤销",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#d33',
                confirmButtonText: '是的, 拒绝',
                cancelButtonText: '取消'
            });

            if (result.isConfirmed) {
                try {
                    await axios.post(`${API_BASE}/trials/${id}/reject`);
                    Swal.fire('已拒绝', '该申请已被拒绝', 'success');
                    loadPendingRequests();
                } catch (error) {
                    Swal.fire('失败', '操作失败', 'error');
                }
            }
        }

        // Initial Load
        document.addEventListener('DOMContentLoaded', loadPendingRequests);
    </script>
</body>
</html>
    """
