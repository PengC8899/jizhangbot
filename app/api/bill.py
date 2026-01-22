from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.models.group import GroupConfig
from sqlalchemy.ext.asyncio import AsyncSession
from jinja2 import Template

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
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f5f5f7; padding: 20px; color: #333; max-width: 800px; margin: 0 auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
            .date-picker { background: white; border: 1px solid #ddd; padding: 5px 10px; border-radius: 6px; font-size: 14px; }
            .download-link { color: #007aff; text-decoration: none; font-size: 14px; }
            
            .section-title { font-size: 18px; color: #666; margin: 30px 0 15px 0; font-weight: normal; display: flex; align-items: center; }
            .section-title span { font-size: 14px; margin-left: 5px; }
            .section-title::after { content: ""; flex: 1; height: 1px; background: #eee; margin-left: 15px; }
            
            .table-container { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; font-size: 14px; }
            th { text-align: left; color: #333; padding: 12px 15px; border-bottom: 1px solid #eee; font-weight: 500; background: #fafafa; }
            td { padding: 12px 15px; border-bottom: 1px solid #f5f5f5; color: #333; }
            tr:last-child td { border-bottom: none; }
            
            .amount { font-weight: 600; }
            .meta { color: #999; font-size: 13px; }
            
            .summary-table td { padding: 10px 15px; border-bottom: 1px solid #eee; }
            .summary-label { color: #666; width: 150px; }
            .summary-value { font-weight: 500; }
            
            .fab { position: fixed; bottom: 20px; right: 20px; width: 50px; height: 50px; background: white; border-radius: 50%; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; align-items: center; justify-content: center; color: #666; cursor: pointer; }
            .fab-lang { bottom: 80px; background: #ff7043; color: white; }
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <select class="date-picker">
                    <option>{{ date_str }}</option>
                </select>
                <a href="#" class="download-link" style="margin-left: 15px;">下载Excel数据</a>
            </div>
        </div>

        <!-- 入款列表 -->
        <div class="section-title">入款 <span>({{ deposits|length }})</span></div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>备注</th>
                        <th>时间</th>
                        <th>金额</th>
                        <th>回复人</th>
                        <th>操作人</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in deposits %}
                    <tr>
                        <td></td>
                        <td class="meta">{{ r.created_at.strftime('%H:%M:%S') }}</td>
                        <td class="amount">{{ "%.2f"|format(r.amount) }}</td>
                        <td class="meta">{{ r.original_text }}</td>
                        <td class="meta">{{ r.operator_name }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="5" style="text-align:center; color:#999; padding: 20px;">无记录</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <!-- 下发列表 -->
        <div class="section-title">下发 <span>({{ payouts|length }})</span></div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>备注</th>
                        <th>时间</th>
                        <th>金额</th>
                        <th>回复人</th>
                        <th>操作人</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in payouts %}
                    <tr>
                        <td></td>
                        <td class="meta">{{ r.created_at.strftime('%H:%M:%S') }}</td>
                        <td class="amount">{{ "%.2f"|format(r.amount) }}</td>
                        <td class="meta">{{ r.original_text }}</td>
                        <td class="meta">{{ r.operator_name }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="5" style="text-align:center; color:#999; padding: 20px;">无记录</td></tr>
                    {% endfor %}
                </tbody>
            </table>
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
                    <td class="summary-value">{{ "%.2f"|format(total_deposit) }} {% if usd_rate > 0 %}| {{ "%.2f"|format(total_deposit / usd_rate) }} USDT{% endif %}</td>
                </tr>
                <tr>
                    <td class="summary-label">应下发:</td>
                    <td class="summary-value">{{ "%.2f"|format(should_pay) }} {% if usd_rate > 0 %}| {{ "%.2f"|format(should_pay / usd_rate) }} USDT{% endif %}</td>
                </tr>
                <tr>
                    <td class="summary-label">下发总数:</td>
                    <td class="summary-value">{{ "%.2f"|format(total_payout) }} {% if usd_rate > 0 %}USDT{% endif %}</td>
                </tr>
                <tr>
                    <td class="summary-label">未下发:</td>
                    <td class="summary-value">{{ "%.2f"|format(pending_pay) }} {% if usd_rate > 0 %}USDT{% endif %}</td>
                </tr>
            </table>
        </div>

        <div class="fab">⊞</div>
        <div class="fab fab-lang">中/A</div>
    </body>
    </html>
    """
    
    # Sort lists
    summary['deposits'].sort(key=lambda x: x.created_at, reverse=True)
    summary['payouts'].sort(key=lambda x: x.created_at, reverse=True)
    
    t = Template(html_template)
    content = t.render(
        date_str=summary['date_str'],
        deposits=summary['deposits'],
        payouts=summary['payouts'],
        total_deposit=total_in,
        total_payout=summary['total_payout'],
        fee_percent=config.fee_percent,
        usd_rate=config.usd_rate,
        should_pay=should_pay,
        pending_pay=pending_pay
    )
    
    return HTMLResponse(content=content)
