from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.models.group import GroupConfig
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jinja2 import Template
from app.core.utils import to_timezone, get_now
from decimal import Decimal
from datetime import timedelta

router = APIRouter()

# Dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/bill/{group_id}", response_class=HTMLResponse)
async def get_bill_page(group_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    service = LedgerService(db)
    
    # 1. Find Config & Bot ID
    stmt = select(GroupConfig).where(GroupConfig.group_id == group_id)
    result = await db.execute(stmt)
    config = result.scalars().first()
    
    if not config:
        # Fallback or Error
        return HTMLResponse("<h1>未找到该群组的账单配置</h1>", status_code=404)
        
    bot_id = config.bot_id
    
    # 2. Get Records (Full List)
    records = await service.get_daily_records(group_id, bot_id)
    
    # 3. Process Records
    deposits = []
    payouts = []
    
    total_in = Decimal(0)
    total_out = Decimal(0)
    
    for r in records:
        if r.type == 'deposit':
            deposits.append(r)
            total_in += r.amount
        elif r.type == 'payout':
            payouts.append(r)
            total_out += r.amount
            
    # 4. Calculate Stats
    fee_percent = config.fee_percent if config.fee_percent is not None else Decimal(0)
    usd_rate = config.usd_rate if config.usd_rate is not None else Decimal(0)
    
    fee = total_in * (fee_percent / Decimal(100))
    should_pay = total_in - fee
    pending_pay = should_pay - total_out
    
    # 5. Date String (4AM Logic)
    now = get_now()
    if now.hour < 4:
         date_obj = now.date() - timedelta(days=1)
    else:
         date_obj = now.date()
    date_str = date_obj.strftime('%Y-%m-%d')
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>完整账单 - {{ date_str }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f5f5f7; padding: 20px; color: #333; max-width: 900px; margin: 0 auto; }
            .header { display: flex; justify-content: flex-start; align-items: center; margin-bottom: 30px; }
            .date-picker { background: white; border: 1px solid #ccc; padding: 5px 10px; border-radius: 4px; font-size: 14px; margin-right: 20px; color: #333; }
            .download-link { color: #0000EE; text-decoration: none; font-size: 14px; }
            
            .section-title { font-size: 20px; color: #333; margin: 40px 0 20px 0; font-weight: 300; display: flex; align-items: center; letter-spacing: 1px; }
            .section-title span { font-size: 16px; margin-left: 10px; color: #333; }
            .section-title::after { content: ""; flex: 1; height: 1px; background: #eee; margin-left: 20px; }
            
            .table-container { background: white; border: 1px solid #e0e0e0; border-radius: 0; margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; font-size: 14px; }
            th { text-align: left; color: #333; padding: 10px 15px; border-bottom: 1px solid #eee; font-weight: normal; background: #fff; border-right: 1px solid #eee; }
            td { padding: 12px 15px; border-bottom: 1px solid #eee; color: #333; border-right: 1px solid #eee; }
            tr:last-child td { border-bottom: none; }
            td:last-child, th:last-child { border-right: none; }
            
            .amount { font-weight: 700; font-size: 15px; }
            .meta { color: #333; font-size: 14px; }
            .calc-info { color: #333; font-size: 14px; }
            .user-info { color: #888; }
            
            /* Summary Table Specifics */
            .summary-table td { padding: 12px 15px; border-bottom: 1px solid #eee; }
            .summary-label { width: 120px; color: #333; }
            .summary-value { color: #333; }
            
            .empty-row { text-align: center; color: #999; padding: 30px; }
        </style>
    </head>
    <body>
        <div class="header">
            <select class="date-picker">
                <option>今天{{ date_str[5:] }}</option>
            </select>
            <a href="/admin/group/{{ group_id }}/export?date={{ date_str }}" class="download-link">下载Excel数据</a>
        </div>

        <!-- 入款列表 -->
        <div class="section-title">入款 <span>({{ deposits|length }})</span></div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">备注</th>
                        <th style="width: 100px;">时间</th>
                        <th style="width: 100px;">金额</th>
                        <th></th> <!-- Calc Column -->
                        <th style="width: 100px;">回复人</th>
                        <th style="width: 100px;">操作人</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in deposits %}
                    <tr>
                        <td></td>
                        <td class="meta">{{ to_timezone(r.created_at).strftime('%H:%M:%S') }}</td>
                        <td class="amount">{{ "%.0f"|format(r.amount) }}</td>
                        <td class="calc-info">
                            {% if usd_rate > 0 %}
                            / {{ usd_rate }}={{ "%.2f"|format(r.amount / usd_rate) }}u
                            {% endif %}
                        </td>
                        <td class="meta"></td>
                        <td class="user-info">{{ r.operator_name }}</td>
                    </tr>
                    {% else %}
                    <!-- Empty rows usually not shown in screenshot style if empty, but we keep structure -->
                    {% endfor %}
                </tbody>
            </table>
            {% if not deposits %}
            <div class="empty-row">无记录</div>
            {% endif %}
        </div>

        <!-- 下发列表 -->
        <div class="section-title">下发 <span>({{ payouts|length }})</span></div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">备注</th>
                        <th style="width: 100px;">时间</th>
                        <th style="width: 100px;">金额</th>
                        <th style="width: 100px;">回复人</th>
                        <th style="width: 100px;">操作人</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in payouts %}
                    <tr>
                        <td></td>
                        <td class="meta">{{ to_timezone(r.created_at).strftime('%H:%M:%S') }}</td>
                        <td class="amount">{{ "%.0f"|format(r.amount) }}</td>
                        <td class="meta"></td>
                        <td class="user-info">{{ r.operator_name }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
             {% if not payouts %}
            <div class="empty-row">无记录</div>
            {% endif %}
        </div>

        <!-- 总结 -->
        <div class="section-title">总结</div>
        <div class="table-container">
            <table class="summary-table">
                <tr>
                    <td class="summary-label">费率:</td>
                    <td class="summary-value">{{ fee_percent }}%</td>
                </tr>
                <tr>
                    <td class="summary-label">美元汇率:</td>
                    <td class="summary-value">{{ usd_rate }}</td>
                </tr>
                <tr>
                    <td class="summary-label">入款总数:</td>
                    <td class="summary-value">{{ "%.0f"|format(total_deposit) }} {% if usd_rate > 0 %}| {{ "%.2f"|format(total_deposit / usd_rate) }} USDT{% endif %}</td>
                </tr>
                <tr>
                    <td class="summary-label">应下发:</td>
                    <td class="summary-value">{{ "%.2f"|format(should_pay) }} {% if usd_rate > 0 %}| {{ "%.2f"|format(should_pay / usd_rate) }} USDT{% endif %}</td>
                </tr>
                <tr>
                    <td class="summary-label">下发总数:</td>
                    <td class="summary-value">{{ "%.2f"|format(total_payout) }} USDT</td>
                </tr>
                <tr>
                    <td class="summary-label">未下发:</td>
                    <td class="summary-value">{{ "%.2f"|format(pending_pay) }} USDT</td>
                </tr>
            </table>
        </div>
    </body>
    </html>
    """
    
    # Render
    t = Template(html_template)
    content = t.render(
        group_id=group_id,
        date_str=date_str,
        deposits=deposits,
        payouts=payouts,
        total_deposit=total_in,
        should_pay=should_pay,
        total_payout=total_out,
        pending_pay=pending_pay,
        fee_percent=fee_percent,
        usd_rate=usd_rate,
        to_timezone=to_timezone
    )
    
    return HTMLResponse(content=content)
