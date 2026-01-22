from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.models.group import GroupConfig
from sqlalchemy.ext.asyncio import AsyncSession
from jinja2 import Template
from app.core.utils import to_timezone

router = APIRouter()

# Dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/bill/{group_id}", response_class=HTMLResponse)
async def get_bill_page(group_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    service = LedgerService(db)
    
    # We assume bot_id=1 for now as per current simple setup, 
    # or we can try to find config first.
    # But usually group_id is unique enough or passed with bot_id.
    # Let's just find the first config matching this group_id to get bot_id if needed,
    # or just query ledger directly by group_id.
    
    # Quick fix: Hardcode bot_id=1 or find it.
    # Better: Query ledger directly ignoring bot_id? No, index uses it.
    # Let's assume bot_id=1 for MVP.
    bot_id = 1 
    
    summary = await service.get_daily_summary(group_id, bot_id)
    config = await service.get_group_config(group_id, bot_id)
    
    total_in = summary['total_deposit']
    fee = total_in * (config.fee_percent / 100.0)
    net_in = total_in - fee
    should_pay = net_in
    pending_pay = should_pay - summary['total_payout']
    
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
    
    # Sort lists
    summary['deposits'].sort(key=lambda x: x.created_at, reverse=True)
    summary['payouts'].sort(key=lambda x: x.created_at, reverse=True)
    
    t = Template(html_template)
    content = t.render(
        group_id=group_id,
        date_str=summary['date_str'],
        deposits=summary['deposits'],
        payouts=summary['payouts'],
        total_deposit=total_in,
        total_payout=summary['total_payout'],
        fee_percent=config.fee_percent,
        usd_rate=config.usd_rate,
        should_pay=should_pay,
        pending_pay=pending_pay,
        to_timezone=to_timezone
    )
    
    return HTMLResponse(content=content)
