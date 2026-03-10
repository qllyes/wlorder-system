import base64
import io
import socket
import datetime
import zipfile
from pathlib import Path
from typing import Optional

import qrcode
from nicegui import app, ui

import backend_db
import waybill_generator
import freight_calc
from init_db import init_db

# 启动时自动初始化数据库
init_db()

# ════════════════════════════════════════════════
#  全局工具集与样式注入
# ════════════════════════════════════════════════

def get_local_ip() -> str:
    try:
        # 使用真实的外部连接探测自身IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"



def parse_logistics_options(raw: str) -> list[str]:
    values = [x.strip() for x in (raw or '').replace('，', ',').split(',') if x.strip()]
    uniq = []
    for v in values:
        if v not in uniq:
            uniq.append(v)
    return uniq


def normalize_spec_text(spec: str) -> str:
    """统一规格文本，降低用户手输差异造成的匹配失败。"""
    return (spec or '').strip().lower().replace('×', '*').replace('x', '*').replace(' ', '')

def generate_qr_base64(data: str) -> str:
    """根据字符串生成二维码图像的 Base64 编码"""
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"

def inject_modern_css():
    """注入现代 SaaS 风格 CSS，以及仿真托运单专属打印 CSS"""
    ui.add_head_html('''
        <style>
        :root {
            --primary-blue: #1677FF;
            --bg-body: #F5F7FA;
            --border-color: #E5E7EB;
        }
        body {
            background-color: var(--bg-body);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            color: #1F2937;
        }
        .modern-card {
            background: #FFFFFF;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03);
            border: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }
        .modern-card:hover {
            box-shadow: 0 4px 6px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.03);
        }
        .q-table tbody tr:nth-child(even) {
            background-color: #FAFAFA;
        }
        .q-table tbody tr:hover {
            background-color: #F3F4F6 !important;
        }
        .sidebar-item-active {
            background-color: #2563EB !important;
            color: white !important;
        }
        .mode-card {
            border: 1px solid #DBEAFE;
            border-radius: 12px;
            padding: 10px 14px;
            background: #EFF6FF;
        }
        .section-card {
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            background: #FFFFFF;
            padding: 14px;
        }
        .section-title {
            font-size: 12px;
            font-weight: 700;
            color: #6B7280;
            letter-spacing: .03em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .new-shipment-dialog .mode-switch {
            width: fit-content;
            margin: 0 auto;
            padding: 4px;
            border-radius: 9999px;
            border: 1px solid #BFDBFE;
            background: #FFFFFF;
        }
        .new-shipment-dialog .mode-switch .q-tab {
            border-radius: 9999px;
            min-height: 34px;
            padding: 0 16px;
            font-weight: 600;
        }
        .new-shipment-dialog .mode-switch .q-tab--active {
            background: #E0ECFF;
            color: #1E40AF;
            font-weight: 700;
        }
        .fixed-mode-panels {
            min-height: 112px;
            max-height: 112px;
            overflow: hidden;
        }
        .upload-pill {
            width: 100%;
        }
        .upload-pill .q-uploader {
            border: 1px dashed #93C5FD !important;
            border-radius: 12px !important;
            background: #EFF6FF;
        }
        .upload-pill .q-uploader__header {
            background: transparent !important;
            padding: 10px !important;
            border-bottom: none !important;
        }
        .upload-pill .q-uploader__add-trigger {
            border-radius: 9999px !important;
            background: #1677FF !important;
            color: #fff !important;
            padding: 8px 18px !important;
            min-height: 36px;
            box-shadow: 0 6px 16px rgba(22, 119, 255, 0.22);
            font-weight: 700;
            transition: all .2s ease;
        }
        .upload-pill .q-uploader__add-trigger:hover {
            background: #0958D9 !important;
            transform: translateY(-1px);
        }
        
        /* 仿真托运单专属 CSS - 强制绕过框架默认样式清除 */
        .printable-batch-container {
            display: flex;
            flex-direction: column;
            gap: 20px;
            padding-bottom: 50px;
        }
        .waybill-paper {
            width: 800px;
            margin: 0 auto;
            background-color: white !important;
            border: 1px solid #000 !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            padding: 20px 30px !important;
            color: #000 !important;
            font-family: "SimSun", "SongTi", "宋体", serif !important;
            position: relative;
            page-break-after: always; /* 强制打印换页 */
        }
        .waybill-paper:last-child {
            page-break-after: auto;
        }
        .waybill-title {
            text-align: center !important;
            font-size: 24px !important;
            font-weight: bold !important;
            letter-spacing: 12px !important;
            margin-bottom: 20px !important;
            border-bottom: 2px solid #000 !important;
            padding-bottom: 10px !important;
        }
        .waybill-header-info {
            display: flex !important;
            justify-content: space-between !important;
            font-size: 14px !important;
            margin-bottom: 10px !important;
            font-weight: bold !important;
        }
        .waybill-table {
            width: 100% !important;
            border-collapse: collapse !important;
            font-size: 13px !important;
            text-align: center !important;
            margin-bottom: 15px !important;
        }
        .waybill-table th, .waybill-table td {
            border: 1px solid #000 !important;
            padding: 8px 4px !important;
            height: 32px !important;
            color: #000 !important;
            background-color: transparent !important;
        }
        .waybill-table th {
            font-weight: bold !important;
        }
        .waybill-table .info-cell {
            text-align: left !important;
            padding-left: 8px !important;
        }
        .waybill-footer {
            font-size: 13px !important;
            line-height: 1.8 !important;
            font-weight: bold !important;
        }
        
        /* 打印媒介专有样式，隐藏 UI 控件 */
        @media print {
            body * { visibility: hidden !important; }
            #waybill-print-area, #waybill-print-area * { visibility: visible !important; }
            #waybill-print-area {
                position: absolute;
                left: 0;
                top: 0;
                width: 100%;
                padding: 0;
                background-color: white !important;
            }
            .waybill-paper {
                box-shadow: none !important;
                border: none !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            .nicegui-dialog, .q-dialog__backdrop { display: none !important; }
        }
        </style>
    ''')

# ════════════════════════════════════════════════
#  托运单 UI 渲染核心组件
# ════════════════════════════════════════════════

def build_waybill_preview_html(
    order_no: str, 
    customer_name: str, 
    customer_phone: str, 
    address: str, 
    products: list[dict], 
    total_qty: int, 
    total_weight: float, 
    freight_val: float,
    pickup_method: str,
    payment_method: str,
    created_at_date: str
) -> str:
    """构建单页高保真实体托运单 HTML 字符串 (纯内联样式以兼容打印)"""
    amount_cn = waybill_generator.num_to_chinese(freight_val)
    dao_zhan = waybill_generator._extract_dao_zhan(address)
    fix_cfg = waybill_generator.FIXED_CONFIG
    
    # 构建 12 个商品行，分为左右两列 (各6行)
    left_prods = products[:6] + [{'name':'', 'spec':'', 'qty':''}] * max(0, 6 - len(products[:6]))
    right_prods = products[6:12] + [{'name':'', 'spec':'', 'qty':''}] * max(0, 6 - len(products[6:12]))
    
    prod_rows_html = ""
    for i in range(6):
        lp = left_prods[i]
        rp = right_prods[i]
        
        row_html = "<tr>"
        row_html += f"""
            <td style="border: 1px solid #000; padding: 4px; text-align: left;">{lp.get('name', '')}</td>
            <td style="border: 1px solid #000; padding: 4px;">{lp.get('spec', '箱') if lp.get('name') else ''}</td>
            <td style="border: 1px solid #000; padding: 4px;">{lp.get('qty', '')}</td>
            <td style="border: 1px solid #000; padding: 4px; text-align: left;">{rp.get('name', '')}</td>
            <td style="border: 1px solid #000; padding: 4px;">{rp.get('spec', '箱') if rp.get('name') else ''}</td>
            <td style="border: 1px solid #000; padding: 4px;">{rp.get('qty', '')}</td>
        """
        if i == 0:
            row_html += f'<td rowspan="6" style="border: 1px solid #000; padding: 4px; vertical-align: top; text-align: left;"><br><span style="margin-left:5px;">运费:</span><br><br><div style="text-align:center; font-size: 16px; font-weight: bold;">{freight_val if freight_val else ""}</div></td>'
        row_html += "</tr>"
        prod_rows_html += row_html
        
    html = f"""
    <div style="width: 200mm; margin: 0 auto; background-color: #fff; padding: 10mm; font-family: 'SimSun', 'SongTi', '宋体', serif; color: #000; page-break-after: always; box-sizing: border-box; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="text-align: center; font-size: 26px; font-weight: bold; letter-spacing: 5px; margin-bottom: 15px;">啤酒厂物流托运单</div>
        <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 5px; font-weight: bold;">
            <span>托运日期： {created_at_date}</span>
            <span>发货号： X{order_no}</span>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; text-align: center; font-size: 13px; border: 2px solid #000; font-family: 'SimSun', 'SongTi', '宋体', serif; color: #000;">
            <tr>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 14%;">发站</td>
                <td style="border: 1px solid #000; padding: 6px; width: 19%;">{fix_cfg["发站"]}</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 14%;">发货方</td>
                <td style="border: 1px solid #000; padding: 6px; width: 19%;">{fix_cfg["发货方"]}</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 14%;">电话</td>
                <td style="border: 1px solid #000; padding: 6px; width: 20%;" colspan="2">{fix_cfg["发货电话"]}</td>
            </tr>
            <tr>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">到站</td>
                <td style="border: 1px solid #000; padding: 6px;">{dao_zhan}</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">收货方</td>
                <td style="border: 1px solid #000; padding: 6px;">{customer_name}</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">电话</td>
                <td style="border: 1px solid #000; padding: 6px;" colspan="2">{customer_phone}</td>
            </tr>
            <tr>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">收货地址</td>
                <td style="border: 1px solid #000; padding: 6px; text-align: left;" colspan="6">{address}</td>
            </tr>
            <tr>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 22%;">品名</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 8%;">包装</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 8%;">件数</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 22%;">品名</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 8%;">包装</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 8%;">件数</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold; width: 24%;">运输费用</td>
            </tr>
            {prod_rows_html}
            <tr>
                <td style="border: 1px solid #000; padding: 6px; text-align: right; font-weight: bold;" colspan="2">总件数</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">{total_qty}</td>
                <td style="border: 1px solid #000; padding: 6px; text-align: right; font-weight: bold;" colspan="2">总重量（吨）</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">{total_weight}</td>
                <td style="border: 1px solid #000; padding: 6px; font-weight: bold;">合计: {freight_val if freight_val else ''} 元</td>
            </tr>
            <tr>
                <td style="border: 1px solid #000; padding: 6px; text-align: left; font-weight: bold;" colspan="7">
                    总合计金额（大写）: <span style="font-size: 16px; margin-left: 20px;">{amount_cn}</span>
                </td>
            </tr>
            <tr>
                <td style="border: 1px solid #000; padding: 6px; text-align: left; font-weight: bold;" colspan="7">
                    <div style="display: flex; justify-content: space-between;">
                        <span>取货方式：送货上门({'√' if pickup_method=='送货上门' else ' '})  自提({'√' if pickup_method=='自提' else ' '})</span>
                        <span>付款方式：提付({'√' if payment_method=='提付' else ' '})  现付({'√' if payment_method=='现付' else ' '})</span>
                    </div>
                </td>
            </tr>
            <tr>
                <td style="border: 1px solid #000; padding: 6px; text-align: left; font-weight: bold;" colspan="7">
                    <div style="display: flex; justify-content: space-between;">
                        <span>查货电话: {fix_cfg['查货电话']}</span>
                        <span>业务电话: {fix_cfg['业务电话']}</span>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """
    return html

# ════════════════════════════════════════════════
#  SPA 页面组件：发货调度工作台
# ════════════════════════════════════════════════

# ​页面上下文桥接器（用于在各 content 函数中访问 main_page 内的 panels 和 refreshable）
_page_ctx: dict = {}

async def shipments_content():
    @ui.refreshable
    async def main_shipments_refreshable():
        default_driver_base_url = f"http://{get_local_ip()}:8600"
        persisted_driver_base_url = await backend_db.get_setting('driver_base_url', default_driver_base_url)
        default_logistics_options = '整车,罗氏物流,小鹏物流'
        persisted_logistics_options = await backend_db.get_setting('logistics_provider_options', default_logistics_options)
        logistics_options = parse_logistics_options(persisted_logistics_options)

        with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12 gap-6'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('发货单调度与管理').classes('text-2xl font-bold tracking-tight text-gray-800')
                
                dlg_new_shipment = ui.dialog()
                with dlg_new_shipment, ui.card().classes('new-shipment-dialog w-[900px] max-w-[98vw] max-h-[90vh] p-0 overflow-y-auto'):
                    # 🎨 注入 CSS：彻底隐藏 Quasar Uploader 的原生 UI，仅保留逻辑和拖拽响应
                    ui.add_head_html('''
                        <style>
                        .new-shipment-dialog .hide-uploader-ui .q-uploader__header { display: none !important; }
                        .new-shipment-dialog .hide-uploader-ui .q-uploader__list { display: none !important; }
                        .new-shipment-dialog .hide-uploader-ui.q-uploader { 
                            background: transparent !important; 
                            box-shadow: none !important; 
                            min-height: unset !important;
                            border: none !important;
                            width: 100% !important;
                        }
                        /* 增加一个全局的拖拽提示样式 */
                        .drop-zone-active { border-color: #3b82f6 !important; background-color: #eff6ff !important; }
                        </style>
                    ''')

                    with ui.row().classes('w-full justify-between items-center px-6 py-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-blue-100'):
                        with ui.column().classes('gap-0'):
                            ui.label('📝 新建发货单').classes('text-lg font-bold text-gray-800')
                            ui.label('支持手工录入与 Excel 一键回填').classes('text-xs text-gray-500')
                        ui.button(icon='close', on_click=dlg_new_shipment.close).props('flat round dense')
                    
                    # 🧪 全局状态
                    global_spec_weights = {}  # 动态加载，避免设置页修改后不生效
                    
                    manual_items: list[dict] = [{'name': '', 'qty': 1, 'unit_weight_kg': 0.0, 'line_weight_kg': 0.0, 'spec': ''}]

                    async def reset_new_shipment_form():
                        # 🆕 动态加载规格权重
                        spec_rows_data = await backend_db.get_all_spec_weights()
                        global_spec_weights.clear()
                        global_spec_weights.update({normalize_spec_text(r['spec']): r['weight_kg'] for r in spec_rows_data})

                        # 清空商品行
                        manual_items.clear()
                        manual_items.append({'name': '', 'qty': 1, 'unit_weight_kg': 0.0, 'line_weight_kg': 0.0, 'spec': ''})
                        if 'manual_items_refreshable' in locals(): manual_items_refreshable.refresh()
                        # 清空输入框
                        if 'customer_input' in locals():
                            date_input.value = str(datetime.date.today())
                            shipper_input.value = '物流部'
                            customer_input.value = ''
                            phone_input.value = ''
                            province_input.value = ''
                            city_input.value = ''
                            district_input.value = ''
                            address_input.value = ''
                            pickup_method_input.value = '送货上门'
                            payment_method_input.value = '现付'
                            new_unit_price.value = 0
                            new_delivery_fee.value = 0
                            manual_freight_fee.value = 0
                            manual_total_weight.value = 0
                            total_qty_input.value = 1
                            if 'new_freight_display' in locals():
                                new_freight_display.text = '→ 托运单运输费: ¥0.00'
                            if 'upload_status_container' in locals():
                                upload_status_container.set_visibility(False)

                    def sync_summary_fields():
                        try:
                            # 汇总到 Module B 的总数量
                            total_qty = sum(int(p.get('qty', 0) or 0) for p in manual_items)
                            if 'total_qty_input' in locals() and total_qty_input:
                                total_qty_input.value = total_qty
                            
                            # 汇总到 Module B 的总重量
                            total_kg = sum(float(p.get('line_weight_kg', 0) or 0) for p in manual_items)
                            if 'manual_total_weight' in locals() and manual_total_weight:
                                manual_total_weight.value = round(total_kg / 1000, 3)
                            
                            if 'update_preview_freight' in locals():
                                update_preview_freight(sync_to_input=True)
                        except:
                            pass

                    @ui.refreshable
                    def manual_items_refreshable():
                        with ui.scroll_area().classes('w-full max-h-[300px] bg-slate-50 p-1 rounded border'):
                            # 🆕 添加表头
                            with ui.row().classes('w-full items-center gap-1 px-1 mb-1'):
                                ui.label('商品名称').classes('flex-1 text-[10px] text-gray-400 font-bold')
                                ui.label('规格').classes('w-24 text-[10px] text-gray-400 font-bold text-center')
                                ui.label('件数').classes('w-16 text-[10px] text-gray-400 font-bold text-center')
                                ui.label('单重(kg)').classes('w-20 text-[10px] text-gray-400 font-bold text-center')
                                ui.label('').classes('w-8')

                            with ui.column().classes('w-full gap-1'):
                                for i, item in enumerate(manual_items):
                                    with ui.row().classes('w-full items-center gap-1 bg-white p-0.5 rounded border-b border-gray-50 last:border-0'):
                                        n = ui.input(value=item.get('name', ''), on_change=lambda e: _n(e.value)).props('outlined dense hide-bottom-space').classes('flex-1 scale-95 origin-left')
                                        s = ui.input(value=item.get('spec', ''), on_change=lambda e: _s(e.value)).props('outlined dense hide-bottom-space').classes('w-24 scale-95')
                                        q = ui.number(value=item.get('qty', 1), min=0, format='%.0f', on_change=lambda e: _q(e.value)).props('outlined dense hide-bottom-space').classes('w-16 scale-95')
                                        w = ui.number(value=item.get('unit_weight_kg', 0), min=0, format='%.3f', on_change=lambda e: _w(e.value)).props('outlined dense hide-bottom-space').classes('w-20 scale-95')

                                        def _n(val, row=item): row['name'] = val or ''
                                        def _q(val, row=item):
                                            row['qty'] = int(float(val or 0))
                                            row['line_weight_kg'] = round(float(row.get('unit_weight_kg', 0) or 0) * row['qty'], 3)
                                            sync_summary_fields()
                                        def _w(val, row=item):
                                            row['unit_weight_kg'] = float(val or 0)
                                            row['line_weight_kg'] = round(row['unit_weight_kg'] * int(row.get('qty', 0) or 0), 3)
                                            sync_summary_fields()
                                        def _s(val, row=item, w_input=w): 
                                            clean_val = (val or '').strip()
                                            row['spec'] = clean_val
                                            normalized_spec = normalize_spec_text(clean_val)
                                            # 🆕 实时权重联动：查表并更新单重输入框
                                            if normalized_spec in global_spec_weights:
                                                new_w = global_spec_weights[normalized_spec]
                                                row['unit_weight_kg'] = new_w
                                                w_input.value = new_w  # 强制更新 UI 组件值
                                            row['line_weight_kg'] = round(float(row.get('unit_weight_kg', 0) or 0) * int(row.get('qty', 0) or 0), 3)
                                            sync_summary_fields()

                                        if len(manual_items) > 1:
                                            def _rm(row=item):
                                                manual_items.remove(row)
                                                manual_items_refreshable.refresh()
                                                sync_summary_fields()
                                            ui.button(icon='delete', on_click=_rm).props('flat round color=red-5 dense').classes('w-8 scale-75')

                    async def on_excel_upload(e):
                        try:
                            import tempfile, os, asyncio
                            filename = getattr(e, 'name', getattr(e, 'filename', 'order.xlsx'))
                            suffix = Path(filename).suffix or '.xlsx'
                            content_io = getattr(e, 'content', None) or getattr(e, 'file', None)
                            if content_io is None: return
                            raw = content_io.read()
                            if hasattr(raw, '__await__'): raw = await raw
                            
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                tmp.write(raw)
                                tmp_path = tmp.name

                            data = waybill_generator.parse_order_excel(tmp_path)
                            os.unlink(tmp_path)

                            spec_rows = await backend_db.get_all_spec_weights()
                            sw = {r['spec']: r['weight_kg'] for r in spec_rows}

                            if 'customer_input' in locals():
                                customer_input.value = data['receiver_name']
                                phone_input.value = data['receiver_phone']
                                address_input.value = data['receiver_address']
                                province_input.value = data.get('receiver_province', '')
                                city_input.value = data.get('receiver_city', '')
                                district_input.value = data.get('receiver_district', '')

                            prods = waybill_generator.enrich_products_with_weight(data.get('products', []), sw)
                            
                            manual_items.clear()
                            current_prods_list = []
                            for p in prods:
                                row_data = {
                                    'name': p.get('name', ''),
                                    'qty': int(p.get('qty', 0) or 0),
                                    'unit_weight_kg': float(p.get('unit_weight_kg', 0) or 0),
                                    'line_weight_kg': round(float(p.get('unit_weight_kg', 0) or 0) * int(p.get('qty', 0) or 0), 3),
                                    'spec': p.get('parsed_spec') or p.get('spec') or '',
                                }
                                manual_items.append(row_data)
                                current_prods_list.append(row_data.copy())
                            manual_items_refreshable.refresh()
                            sync_summary_fields()
                            
                            try:
                                matched_price = freight_calc.lookup_unit_price(province_input.value, city_input.value, district_input.value)
                                if matched_price is not None:
                                    new_unit_price.value = float(matched_price)
                            except: pass
                            
                            if 'update_preview_freight' in locals():
                                update_preview_freight(sync_to_input=True)
                                
                            ui.notify(f'订单导入成功！已加载 {len(manual_items)} 行商品数据', type='positive')
                            if 'status_label' in locals():
                                status_label.set_text(f"已加载: {filename} ({len(manual_items)}行)")
                                upload_status_container.set_visibility(True)
                        except Exception as ex:
                            import traceback
                            traceback.print_exc()
                            ui.notify(f'导入失败：{ex}', type='negative')

                    with ui.column().classes('px-3 pb-4 gap-3'):
                        # 🆕 数据录入区紧凑重构 (Excel 导入)
                        with ui.card().classes('w-full p-4 bg-slate-50 border-2 border-dashed border-blue-200 rounded-xl shadow-none mb-1'):
                            with ui.row().classes('w-full items-center justify-between gap-4'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('cloud_upload', color='blue-500', size='24px')
                                    with ui.column().classes('gap-0'):
                                        ui.label('Excel 导入').classes('text-sm font-bold text-slate-700')
                                        ui.label('支持 .xlsx / .xls，自动识别信息').classes('text-[10px] text-slate-400')
                                
                                with ui.row().classes('items-center gap-2 relative'):
                                    # 真正的上传器：覆盖整个区域，捕获点击和拖拽
                                    uploader = ui.upload(on_upload=on_excel_upload, auto_upload=True) \
                                        .props('accept=".xlsx,.xls" flat hide-upload-list') \
                                        .classes('hide-uploader-ui absolute inset-0 opacity-0 z-10 cursor-pointer')
                                    # 明确绑定点击事件触发文件选择器 (Scheme A Enhanced Fix)
                                    uploader.on('click', lambda: uploader.run_method('pickFiles'))
                                    
                                    # 视觉层：用户看到的按钮 (z-0)
                                    with ui.row().classes('items-center bg-blue-50 hover:bg-blue-100 transition-colors rounded-full px-4 py-1.5 border border-blue-200 gap-2 shrink-0'):
                                        ui.icon('add_circle', color='blue-600', size='18px')
                                        ui.label('点击选择或拖拽至此').classes('text-xs text-blue-700 font-bold')

                            # 🆕 状态反馈区 (绿色胶囊样式)
                            upload_status_container = ui.row().classes('w-full mt-3 items-center gap-2 px-3 py-1.5 bg-green-50 rounded-full border border-green-200')
                            upload_status_container.set_visibility(False)
                            with upload_status_container:
                                ui.icon('check_circle', color='green-500', size='18px')
                                status_label = ui.label('').classes('text-[11px] text-green-700 font-bold')
                                ui.button(icon='close', on_click=lambda: upload_status_container.set_visibility(False)).props('flat round dense color=grey-4').classes('ml-auto size-xs')




                        with ui.card().classes('w-full p-3 border shadow-sm'):
                            ui.label('模块A：基础与物流信息').classes('section-title')
                            with ui.grid(columns=4).classes('w-full gap-2'):
                                date_input = ui.input('接单日期', value=str(datetime.date.today())).props('outlined dense')
                                shipper_input = ui.input('托运人(发货方)', value='物流部').props('outlined dense')
                                customer_input = ui.input('收货人*').props('outlined dense')
                                phone_input = ui.input('收货电话').props('outlined dense')
                                province_input = ui.input('省份').props('outlined dense')
                                city_input = ui.input('城市').props('outlined dense')
                                district_input = ui.input('区/县').props('outlined dense')
                                address_input = ui.input('目的地/详细地址*').props('outlined dense').classes('col-span-4')

                        with ui.card().classes('w-full p-3 border shadow-sm'):
                            ui.label('模块B：财务与交接要求').classes('section-title')
                            with ui.grid(columns=4).classes('w-full gap-2'):
                                pickup_method_input = ui.select(['送货上门', '客户自提'], value='送货上门', label='交接方式').props('outlined dense')
                                payment_method_input = ui.select(['现付', '到付', '月结'], value='现付', label='付款方式').props('outlined dense')
                                total_qty_input = ui.number('总数量(件)(自动汇总)', value=1, format='%.0f').props('outlined dense readonly bg-blue-50')
                                new_unit_price = ui.number('单价(元/吨)*', value=0, min=0, format='%.2f').props('outlined dense input-class="text-blue-600 font-bold"')
                                new_delivery_fee = ui.number('运送费(元)*', value=0, min=0, format='%.2f').props('outlined dense')
                                manual_total_weight = ui.number('总重量(吨)(自动汇总)', value=0, min=0, format='%.3f').props('outlined dense readonly bg-blue-50 input-class="text-blue-600 font-bold"')
                                manual_freight_fee = ui.number('托运单运输费(预估/实填)', value=0, min=0, format='%.2f').props('outlined dense input-class="text-blue-600 font-bold"')

                        with ui.card().classes('w-full p-2 border shadow-sm'):
                            ui.label('模块C：商品明细清单').classes('section-title')
                            
                            manual_items_refreshable()
                            def add_manual_item():
                                manual_items.append({'name': '', 'qty': 1, 'unit_weight_kg': 0.0, 'line_weight_kg': 0.0, 'spec': ''})
                                manual_items_refreshable.refresh()
                                sync_summary_fields()
                            ui.button('➕ 新增商品行', on_click=add_manual_item, color='primary').props('outline dense').classes('mt-2')

                        with ui.row().classes('w-full items-center justify-between gap-2 p-2 rounded-lg bg-white border border-blue-100'):
                            new_freight_display = ui.label('→ 托运单运输费: ¥0.00').classes('text-sm font-bold text-blue-700')
                            ui.label('业务模式将在后续【分配物流】自动判定（整车/零单）').classes('text-xs text-gray-500 text-right')
                        
                        # 🆕 实时更新运费预览逻辑 (支持回填)
                        def update_preview_freight(sync_to_input=False):
                            # 核心修复：优先从“实填”框读取总重量，而非导入明细
                            total_w_ton = float(manual_total_weight.value or 0)
                            
                            up = float(new_unit_price.value or 0)
                            df = float(new_delivery_fee.value or 0)
                            
                            # 按照阶梯公式计算自动预估值
                            auto_calc_val = freight_calc.calc_freight(total_w_ton, '零单', up, df)
                            
                            # 当重量达到 8 吨时，开启“请人工填写”模式
                            is_manual_threshold = total_w_ton >= 8.0

                            # 🆕 逻辑优化：一旦超过 8 吨，同步清空运费框（显示为 0），由用户手工填入
                            if is_manual_threshold and sync_to_input:
                                manual_freight_fee.value = 0

                            # 如果需要同步（如导入或单价变动时），且未达到人工阈值，则更新输入框
                            if sync_to_input and not is_manual_threshold:
                                manual_freight_fee.value = auto_calc_val

                            # 预览显示始终以输入框的“实填”值为准
                            current_val = float(manual_freight_fee.value or 0)
                            
                            if is_manual_threshold:
                                # >= 8吨 重点变色提醒
                                new_freight_display.text = f'→ 托运单运输费: ¥{current_val:,.2f} (请人工填写)'
                                new_freight_display.classes(replace='text-blue-700 text-orange-700')
                            else:
                                new_freight_display.text = f'→ 托运单运输费: ¥{current_val:,.2f}'
                                new_freight_display.classes(replace='text-orange-700 text-blue-700')

                        new_unit_price.on('update:model-value', lambda: update_preview_freight(sync_to_input=True))
                        new_delivery_fee.on('update:model-value', lambda: update_preview_freight(sync_to_input=True))
                        manual_total_weight.on('update:model-value', lambda: update_preview_freight(sync_to_input=True))
                        manual_freight_fee.on('update:model-value', lambda: update_preview_freight(sync_to_input=False))
                        
                        # 初始调用一次
                        update_preview_freight()
                    
                    async def submit_shipment():
                        if not customer_input.value or not address_input.value:
                            ui.notify('请完整填写必填项', type='warning')
                            return
                        spec_rows = await backend_db.get_all_spec_weights()
                        sw = {r['spec']: r['weight_kg'] for r in spec_rows}

                        # 🆕 统一处理商品行数据
                        typed_rows = [r for r in manual_items if (r.get('name') or '').strip()]
                        if not typed_rows:
                            ui.notify('请至少填写一行商品明细', type='warning')
                            return
                            
                        prods = [{
                            'name': r.get('name', ''),
                            'spec': r.get('spec', ''),
                            'qty': int(r.get('qty', 0) or 0),
                            'parsed_spec': '',
                            'unit_weight_kg': float(r.get('unit_weight_kg', 0) or 0),
                            'line_weight_kg': round(float(r.get('unit_weight_kg', 0) or 0) * int(r.get('qty', 0) or 0), 3),
                            'weight_source': 'manual_input',
                            'weight_locked': 1,
                        } for r in typed_rows]
                        
                        total_qty = sum(int(p.get('qty', 0) or 0) for p in prods)
                        # 自动生成货物品类汇总 (取前 3 个品名)
                        summary_product_name = '、'.join([p['name'] for p in prods[:3]])
                        if len(prods) > 3:
                            summary_product_name += f' 等 {len(prods)} 项'
                        # 公式: 托运单运输费 = 总重量 * 单价 + 运送费
                        up = float(new_unit_price.value or 0)
                        df = float(new_delivery_fee.value or 0)
                        
                        parsed_addr = waybill_generator.parse_cn_address(address_input.value)
                        province_val = province_input.value or parsed_addr.get('province', '')
                        city_val = city_input.value or parsed_addr.get('city', '')
                        district_val = district_input.value or parsed_addr.get('district', '')

                        # 自动匹配单价
                        try:
                            matched_price = freight_calc.lookup_unit_price(province_val, city_val, district_val)
                        except Exception as ex:
                            ui.notify(f'单价表匹配失败，将使用手工单价：{ex}', type='warning')
                            matched_price = None
                        
                        unit_price_source = 'manual_input'
                        if matched_price is not None:
                            up = float(matched_price)
                            new_unit_price.value = up
                            unit_price_source = 'district_match'
                        
                        # 核心：使用“预估/实填”框中的值作为最终存入数据库的值
                        total_weight_t = float(manual_total_weight.value or 0)
                        freight_fee = float(manual_freight_fee.value or 0)
                        
                        # 判定计费模式
                        # 核心逻辑：如果重量 >= 8 吨，或者实填值与阶梯公式计算值不符，则标记为 manual
                        expected_auto = freight_calc.calc_freight(total_weight_t, '零单', up, df)
                        
                        if total_weight_t < 8.0 and abs(freight_fee - expected_auto) < 0.01:
                            freight_fee_mode = 'auto'
                        else:
                            freight_fee_mode = 'manual'
                        
                        new_sid = await backend_db.create_order_with_items(
                            {
                                'customer_name': customer_input.value,
                                'product_name': summary_product_name,
                                'quantity': total_qty,
                                'delivery_address': address_input.value,
                                'receiver_province': province_val,
                                'receiver_city': city_val,
                                'receiver_district': district_val,
                                'ship_type': '待分配',
                                'customer_phone': phone_input.value,
                                'total_weight': total_weight_t,
                                'unit_price': up,
                                'delivery_fee': df,
                                'freight_fee': freight_fee,
                                'freight_fee_mode': freight_fee_mode,
                                'unit_price_source': unit_price_source,
                                'pickup_method': pickup_method_input.value,
                                'payment_method': payment_method_input.value,
                                'order_date': date_input.value,
                                'shipper_name': shipper_input.value,
                                'cod_amount':  0,
                                'receipt_requirement': '不要求', # 移除 UI 后默认不要求
                            },
                            prods,
                        )
                        await backend_db.recalc_shipment_weight_and_fee(new_sid)
                        ui.notify(f'发货单已生成 | 总重量: {total_weight_t}吨 | 托运单运输费: ¥{freight_fee}', type='positive')
                        customer_input.value = ''
                        phone_input.value = ''
                        province_input.value = ''
                        city_input.value = ''
                        district_input.value = ''
                        address_input.value = ''
                        new_unit_price.value = 0
                        new_delivery_fee.value = 0
                        manual_freight_fee.value = 0
                        manual_total_weight.value = 0
                        total_qty_input.value = 1
                        new_freight_display.text = '→ 托运单运输费: ¥0.00'
                        manual_items.clear()
                        manual_items.append({'name': '', 'qty': 1, 'unit_weight_kg': 0.0, 'line_weight_kg': 0.0, 'spec': ''})
                        manual_items_refreshable.refresh()
                        dlg_new_shipment.close()
                        list_refreshable.refresh()

                    with ui.row().classes('w-full justify-end items-center gap-3 mt-6 px-4 py-4 bg-white border-t border-gray-100'):
                        ui.button('取消', on_click=dlg_new_shipment.close).props('outline text-gray-600 border-gray-300')
                        ui.button('🚀 确认创建订单', on_click=submit_shipment, color='primary')
                
                ui.button('新建发货单', icon='add', on_click=lambda: (reset_new_shipment_form(), dlg_new_shipment.open())).classes('bg-primary text-white font-bold')

            # ── 调度总台账 ──
            with ui.card().classes('modern-card w-full p-0 overflow-hidden'):
                # （把弹窗定义移出布局主干，保持结构清晰）
                dlg_batch_del = ui.dialog()
                with dlg_batch_del, ui.card().classes('p-6 min-w-[380px]'):
                    ui.label('⚠️ 确认批量删除？').classes('text-lg font-bold text-red-600 mb-2')
                    batch_del_info = ui.label('').classes('text-sm text-gray-500 mb-4')
                    with ui.row().classes('w-full justify-center gap-4'):
                        ui.button('取消', on_click=dlg_batch_del.close).props('outline')
                        confirm_btn = ui.button('确认删除', color='red')

                selected_ids_for_delete: list[str] = []

                async def confirm_batch_delete():
                    if not selected_ids_for_delete:
                        ui.notify('未检测到可删除的发货单记录', type='warning')
                        dlg_batch_del.close()
                        return
                    deleted = await backend_db.batch_delete_shipments(selected_ids_for_delete)
                    ui.notify(f'已删除 {deleted} 条发货单记录', type='positive')
                    dlg_batch_del.close()
                    list_refreshable.refresh()

                confirm_btn.on_click(confirm_batch_delete)

                curr_sid = ui.label().classes('hidden')
                current_edit_ship_type = {'value': '待分配'}
                current_edit_logistics = {'value': ''}
                current_edit_logistics_mutable = {'value': False}

                smart_logistics_selectors = []

                def create_smart_logistics_selector() -> dict:
                    with ui.column().classes('w-full mb-2 gap-1'):
                        select_el = ui.select(logistics_options, label='物流选项*').props('use-input fill-input hide-selected input-debounce=0 new-value-mode=add-unique').classes('w-full')
                        ui.label('输入后若不存在将自动新增并完成分配').classes('text-[11px] text-gray-400')

                    def set_value(value: str):
                        select_el.value = (value or '').strip() or None

                    def get_value() -> str:
                        return (select_el.value or '').strip()

                    def refresh_options():
                        select_el.options = logistics_options
                        select_el.update()

                    def set_editable(can_edit: bool):
                        if can_edit:
                            select_el.enable()
                        else:
                            select_el.disable()

                    selector = {
                        'set_value': set_value,
                        'get_value': get_value,
                        'refresh_options': refresh_options,
                        'set_editable': set_editable,
                    }
                    smart_logistics_selectors.append(selector)
                    return selector

                def refresh_all_logistics_selectors():
                    for selector in smart_logistics_selectors:
                        selector['refresh_options']()

                async def ensure_logistics_option(provider: str):
                    normalized_provider = (provider or '').strip()
                    if not normalized_provider or normalized_provider in logistics_options:
                        return
                    logistics_options.append(normalized_provider)
                    refresh_all_logistics_selectors()
                    await backend_db.set_setting('logistics_provider_options', ','.join(logistics_options))
                
                # ── 弹窗：编辑发货单 ──
                dlg_edit = ui.dialog()
                with dlg_edit, ui.card().classes('min-w-[500px] p-6'):
                    with ui.row().classes('w-full justify-between items-center mb-4'):
                        ui.label('✏️ 修改发货单').classes('text-lg font-bold text-blue-800')
                        ui.button(icon='close', on_click=dlg_edit.close).props('flat round dense')
                    
                    edit_customer = ui.input('客户名称*').classes('w-full mb-2')
                    edit_product = ui.input('货物品类*').classes('w-full mb-2')
                    edit_spec = ui.input('规格').classes('w-full mb-2')
                    edit_qty = ui.number('数量(件)*', min=1, format='%.0f').classes('w-full mb-2')
                    edit_address = ui.input('收货详细地址*').classes('w-full mb-2')
                    
                    ui.separator().classes('my-4')
                    ui.label('单据打印及运费配置').classes('text-xs font-bold text-gray-400 mb-1')
                    with ui.row().classes('w-full gap-2 mb-2'):
                        edit_pickup = ui.select(['送货上门', '自提'], value='送货上门', label='取货方式').classes('flex-1')
                        edit_payment = ui.select(['现付', '提付'], value='现付', label='付款方式').classes('flex-1')
                    with ui.row().classes('w-full gap-2 mb-2'):
                        edit_unit_price = ui.number('单价(元/吨)', value=0, min=0, format='%.2f').classes('flex-1')
                        edit_delivery = ui.number('运送费(元)', value=0, min=0, format='%.2f').classes('flex-1')
                    edit_manual_freight = ui.number('托运单运输费(>8吨手填)', value=0, min=0, format='%.2f').classes('w-full mb-3')
                        
                    ui.separator().classes('my-4')
                    ui.label('物流分配（自动推导业务模式）').classes('text-xs font-bold text-gray-400 mb-1')
                    edit_selector = create_smart_logistics_selector()
                    edit_mode_hint = ui.label('当前业务模式：待分配').classes('text-[11px] text-blue-600 mb-4')
                    
                    async def save_edit():
                        if not edit_customer.value or not edit_product.value or not edit_address.value:
                            ui.notify('请完整填写必填项', type='warning')
                            return
                        # 计算总重量
                        spec_rows = await backend_db.get_all_spec_weights()
                        sw = {r['spec']: r['weight_kg'] for r in spec_rows}
                        prods = [{'name': edit_product.value, 'spec': '', 'qty': int(edit_qty.value)}]
                        _, total_weight_t = waybill_generator.calc_total_weight(prods, sw)
                        up = float(edit_unit_price.value or 0)
                        df = float(edit_delivery.value or 0)
                        parsed_addr = waybill_generator.parse_cn_address(edit_address.value)
                        try:
                            matched_price = freight_calc.lookup_unit_price(
                                parsed_addr.get('province', ''),
                                parsed_addr.get('city', ''),
                                parsed_addr.get('district', ''),
                            )
                        except Exception as ex:
                            ui.notify(f'单价表匹配失败，将使用手工单价：{ex}', type='warning')
                            matched_price = None
                        unit_price_source = 'manual_input'
                        if matched_price is not None:
                            up = float(matched_price)
                            edit_unit_price.value = up
                            unit_price_source = 'district_match'
                        if total_weight_t > 8:
                            freight_fee = float(edit_manual_freight.value or 0)
                            if freight_fee <= 0:
                                ui.notify('总重量超过8吨，托运单运输费需手动填写且大于0', type='warning')
                                return
                            freight_fee_mode = 'manual'
                        else:
                            freight_fee = round(total_weight_t * up + df, 2)
                            freight_fee_mode = 'auto'
                        
                        provider = current_edit_logistics['value']
                        inferred_mode = current_edit_ship_type['value']
                        if current_edit_logistics_mutable['value']:
                            provider = edit_selector['get_value']()
                            inferred_mode = '整车' if provider == '整车' else ('零单' if provider else current_edit_ship_type['value'])

                        # 🆕 更新主表
                        await backend_db.update_shipment_info(
                            curr_sid.text, edit_customer.value, edit_product.value, 
                            int(edit_qty.value), edit_address.value, inferred_mode,
                            edit_pickup.value, edit_payment.value,
                            total_weight=total_weight_t, unit_price=up,
                            delivery_fee=df, freight_fee=freight_fee,
                            freight_fee_mode=freight_fee_mode, unit_price_source=unit_price_source,
                        )
                        # 🆕 同步更新明细子表 (单品模式)
                        prods_to_save = [{
                            'name': edit_product.value,
                            'spec': edit_spec.value or '',
                            'qty': int(edit_qty.value),
                            'unit_weight_kg': (total_weight_t * 1000 / int(edit_qty.value)) if int(edit_qty.value) > 0 else 0
                        }]
                        await backend_db.save_shipment_products(curr_sid.text, prods_to_save)
                        if provider:
                            await ensure_logistics_option(provider)
                            await backend_db.set_shipment_logistics_provider(curr_sid.text, provider)
                        ui.notify(f'修改已保存 | 总重量: {total_weight_t}吨 | 托运单运输费: ¥{freight_fee}', type='positive')
                        dlg_edit.close()
                        list_refreshable.refresh()
                        
                    with ui.row().classes('w-full justify-end gap-2 mt-6'):
                        ui.button('取消', on_click=dlg_edit.close).props('outline text-gray-600 border-gray-300')
                        ui.button('保存修改', on_click=save_edit, color='primary')
                
                # ── 商品明细下钻（已升级为页面级面板，见 detail_view_content） ──

                # ── 其它弹窗 (扫码, 补录快递单, 撤销, 作废) ──
                dlg_lingdan = ui.dialog()
                with dlg_lingdan, ui.card().classes('min-w-[460px] p-6'):
                    ui.label('分配物流并自动判定业务模式').classes('font-bold text-lg mb-1')
                    ui.label('可搜索、可选择、可直接输入新物流').classes('text-xs text-gray-500 mb-4')

                    lingdan_selector = create_smart_logistics_selector()
                    trk_in = ui.input('运单号（选填）').classes('w-full mb-1')
                    ui.label('规则：物流=整车 → 业务模式整车；其他物流公司 → 业务模式零单').classes('text-[11px] text-blue-600 mb-3')

                    async def save_lingdan():
                        provider = lingdan_selector['get_value']()
                        tracking_no = (trk_in.value or '').strip()
                        if not provider:
                            ui.notify('请填写或选择物流公司', type='warning')
                            return
                        await ensure_logistics_option(provider)
                        await backend_db.assign_logistics(curr_sid.text, provider, tracking_no)
                        if provider == '整车':
                            ui.notify('已分配为整车，状态更新为已订车', type='positive')
                        else:
                            ui.notify('已分配第三方物流并完成发货', type='positive')
                        dlg_lingdan.close()
                        lingdan_selector['set_value']('')
                        list_refreshable.refresh()

                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('取消', on_click=dlg_lingdan.close).props('flat')
                        ui.button('确认分配', on_click=save_lingdan, color='primary')
                        
                dlg_qr = ui.dialog()
                with dlg_qr, ui.card().classes('p-6 items-center'):
                    ui.label('司机发车扫码').classes('font-bold text-lg mb-4 text-primary')
                    qr_img = ui.image().classes('w-60 h-60 bg-white p-2 rounded shadow')
                    ui.button('关闭', on_click=dlg_qr.close).classes('mt-4 w-full').props('outline')

                dlg_cancel = ui.dialog()
                with dlg_cancel, ui.card().classes('p-6 items-center'):
                    ui.label('⚠️ 确定要作废这笔发货单吗？').classes('text-lg font-bold text-red-600 mb-2')
                    async def confirm_cancel():
                        await backend_db.cancel_shipment(curr_sid.text)
                        ui.notify('此单据已作废，数据已归档', type='warning')
                        dlg_cancel.close()
                        list_refreshable.refresh()
                    with ui.row().classes('w-full justify-center gap-4'):
                        ui.button('暂不作废', on_click=dlg_cancel.close).props('outline text-gray-600')
                        ui.button('确认作废', on_click=confirm_cancel, color='red')

                dlg_rollback = ui.dialog()
                with dlg_rollback, ui.card().classes('p-6 items-center'):
                    ui.label('🔄 确定要撤销这笔发货单吗？').classes('text-lg font-bold text-orange-600 mb-2')
                    async def confirm_rollback():
                        await backend_db.rollback_to_unbooked(curr_sid.text)
                        ui.notify('单据已撤销发货并打回未订车状态', type='info')
                        dlg_rollback.close()
                        list_refreshable.refresh()
                    with ui.row().classes('w-full justify-center gap-4'):
                        ui.button('暂不撤销', on_click=dlg_rollback.close).props('outline text-gray-600')
                        ui.button('确认撤销', on_click=confirm_rollback, color='orange')


                # ── 重构的全局批量托运单展示弹窗 ──
                dlg_batch_print = ui.dialog().props('maximized transition-show="slide-up" transition-hide="slide-down"')
                batch_print_container = None
                
                with dlg_batch_print, ui.card().classes('w-full h-full p-0 bg-gray-100 flex flex-col overflow-hidden'):
                    # 顶部操作栏
                    with ui.row().classes('w-full h-16 bg-white border-b border-gray-200 shadow z-10 items-center justify-between px-6 flex-shrink-0'):
                        with ui.row().classes('items-center'):
                            ui.button(icon='arrow_back', on_click=dlg_batch_print.close).props('flat round dense color=gray-600')
                            ui.label('单据预览与批量打印').classes('text-xl font-bold ml-4 text-gray-800')
                        
                        ui.button('调用浏览器执行全部打印记录', icon='print', color='primary').classes('h-10').on_click(lambda: ui.run_javascript('window.print()'))
                    
                    # 滚动预览区
                    with ui.column().classes('flex-grow w-full bg-gray-200 p-8 overflow-y-auto items-center'):
                        batch_print_container = ui.html('').classes('printable-batch-container w-full max-w-[850px]')

                async def display_batch_print_dialog(rows):
                    """循环渲染 HTML 列表并塞入占位符"""
                    dlg_batch_print.open()
                    try:
                        spec_rows = await backend_db.get_all_spec_weights()
                        sw = {r['spec']: r['weight_kg'] for r in spec_rows}
                        
                        html_pieces = []
                        for row in rows:
                            sid = row.get('shipment_id', '')
                            ship = await backend_db.get_shipment_by_id(sid)
                            if not ship: continue
                            
                            products = [{'name': ship.get('product_name',''), 'spec': '', 'qty': ship.get('quantity', 0)}]
                            total_qty, total_weight_t = waybill_generator.calc_total_weight(products, sw)
                            
                            f_fee = ship.get('freight_fee', 0.0)
                            if f_fee == 0.0 and ship.get('ship_type') in ('零单', '拼车'):
                                d_fee = ship.get('delivery_fee', 0.0)
                                f_fee = freight_calc.calc_freight(total_weight_t, ship.get('ship_type'), 0, d_fee)
                                
                            created_dt_str = ship.get('created_at', str(datetime.date.today()))[:10]
                            
                            html_piece = build_waybill_preview_html(
                                order_no=sid,
                                customer_name=ship.get('customer_name', ''),
                                customer_phone='', 
                                address=ship.get('delivery_address', ''),
                                products=products,
                                total_qty=total_qty,
                                total_weight=total_weight_t,
                                freight_val=f_fee,
                                pickup_method=ship.get('pickup_method', '送货上门'),
                                payment_method=ship.get('payment_method', '现付'),
                                created_at_date=created_dt_str
                            )
                            html_pieces.append(html_piece)
                            
                        # 拼装包裹层，并放入到HTML组件中
                        # 外层需要设定一个带 ID 的打印区，确保 CSS 能查找到
                        final_html = f'<div id="waybill-print-area">{"".join(html_pieces)}</div>'
                        batch_print_container.content = final_html
                    except Exception as e:
                        ui.notify(f'预览生成失败: {e}', type='negative')

                async def execute_batch_export(rows):
                    try:
                        spec_rows = await backend_db.get_all_spec_weights()
                        sw = {r['spec']: r['weight_kg'] for r in spec_rows}
                        
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                            for row in rows:
                                sid = row.get('shipment_id', '')
                                ship = await backend_db.get_shipment_by_id(sid)
                                if not ship: continue
                                
                                products = [{'name': ship.get('product_name',''), 'spec': '', 'qty': ship.get('quantity', 0)}]
                                order_data = {
                                    'order_no': sid,
                                    'receiver_name': ship.get('customer_name', ''),
                                    'receiver_phone': '',
                                    'receiver_address': ship.get('delivery_address', ''),
                                    'products': products,
                                    'created_at': ship.get('created_at', '')[:10]
                                }
                                
                                f_fee = ship.get('freight_fee', 0.0)
                                excel_bytes = waybill_generator.generate_waybill_excel(
                                    order_data, freight=f_fee,
                                    pickup_method=ship.get('pickup_method', '送货上门'), 
                                    payment_method=ship.get('payment_method', '现付'),
                                    spec_weights=sw,
                                )
                                filename = f"托运单_{sid}.xlsx"
                                zip_file.writestr(filename, excel_bytes)
                                
                        zip_data = zip_buffer.getvalue()
                        ui.download(zip_data, f"批量托运单导出_{datetime.date.today().isoformat()}.zip")
                        ui.notify(f'已成功导出 {len(rows)} 份托运单', type='positive')
                    except Exception as ex:
                        ui.notify(f'批量导出失败：{ex}', type='negative')


                # （把筛选变量移到外层，不然 refreshable 里读不到最新状态）
                filter_status = {'value': '全部'}
                filter_customer = {'value': ''}
                filter_phone = {'value': ''}
                filter_start = {'value': ''}
                filter_end = {'value': ''}

                table = None
                
                @ui.refreshable
                async def list_refreshable():
                    shipments = await backend_db.fetch_all_shipments(
                        filter_status['value'], filter_customer['value'],
                        filter_start['value'], filter_end['value'],
                        phone=filter_phone['value'],
                    )
                    cols = [
                        {'name': 'shipment_id', 'label': '发货号', 'field': 'shipment_id', 'align': 'left'},
                        {'name': 'ship_type', 'label': '类型', 'field': 'ship_type', 'align': 'center'},
                        {'name': 'status', 'label': '状态', 'field': 'status', 'align': 'center'},
                        {'name': 'logistics_provider', 'label': '物流', 'field': 'logistics_provider', 'align': 'left'},
                        {'name': 'customer', 'label': '收货人', 'field': 'customer_name', 'align': 'left'},
                        {'name': 'customer_phone', 'label': '收货电话', 'field': 'customer_phone', 'align': 'center'},
                        {'name': 'delivery_address', 'label': '收货地址', 'field': 'delivery_address', 'align': 'left'},
                        {'name': 'driver_name', 'label': '司机姓名', 'field': 'driver_name', 'align': 'center'},
                        {'name': 'driver_phone', 'label': '司机电话', 'field': 'driver_phone', 'align': 'center'},
                        {'name': 'truck_plate', 'label': '车牌号', 'field': 'truck_plate', 'align': 'center'},
                        {'name': 'total_weight', 'label': '总重量(吨)', 'field': 'total_weight', 'align': 'center', 'sortable': True},
                        {'name': 'freight_fee', 'label': '托运单运输费', 'field': 'freight_fee', 'align': 'center', 'sortable': True},
                        {'name': 'actual_cost', 'label': '实付运输费', 'field': 'actual_cost', 'align': 'center', 'sortable': True},
                        {'name': 'batch', 'label': '合单批次', 'field': 'batch_id', 'align': 'left'},
                        {'name': 'actions', 'label': '操作', 'align': 'center'}
                    ]
                    with ui.table(columns=cols, rows=shipments, row_key='shipment_id', selection='multiple').classes('w-full').props('dense flat') as global_table:
                        nonlocal table
                        table = global_table
                        
                        # ── 核心改造：使用 top 插槽高度内聚所有控制器 ──
                        with table.add_slot('top'):
                            with ui.column().classes('w-full gap-4 pb-2'):
                                # 上层：仅保留批量操作（动态）
                                with ui.row().classes('w-full justify-start items-center'):
                                    batch_actions = ui.row().classes('items-center gap-2 transition-all overflow-hidden')
                                    with batch_actions:
                                        ui.label().bind_text_from(table, 'selected', lambda s: f'已选 {len(s)} 项:').classes('text-sm font-bold text-blue-600')

                                        async def do_batch_lingdan():
                                            selected = [row['shipment_id'] for row in table.selected if row['ship_type'] == '零单' and not row.get('batch_id')]
                                            if not selected:
                                                ui.notify('请勾选尚未合单的【零单】进行合单', type='warning')
                                                return
                                            bid = await backend_db.batch_lingdan(selected)
                                            ui.notify(f'合单成功: {bid}', type='positive')
                                            list_refreshable.refresh()

                                        async def on_batch_preview():
                                            await display_batch_print_dialog([row for row in table.selected])

                                        async def on_batch_export():
                                            await execute_batch_export([row for row in table.selected])

                                        def do_batch_delete():
                                            nonlocal selected_ids_for_delete
                                            selected_ids_for_delete = [row['shipment_id'] for row in table.selected]
                                            batch_del_info.text = f'即将永久删除 {len(selected_ids_for_delete)} 条发货单记录，此操作不可恢复！'
                                            dlg_batch_del.open()

                                        ui.button('🔗 零单合单', on_click=do_batch_lingdan).props('outline dense color=secondary')
                                        ui.button('🖨️ 预览', on_click=on_batch_preview).props('outline dense color=blue')
                                        ui.button('📥 导出Excel', on_click=on_batch_export).props('outline dense color=green')
                                        ui.button('🗑️ 删除', on_click=do_batch_delete).props('outline dense color=red')

                                    batch_actions.bind_visibility_from(table, 'selected', lambda s: len(s) > 0)

                                # 下层：紧凑的筛选表单
                                with ui.row().classes('w-full items-center gap-3 bg-gray-50 p-2 rounded justify-between'):
                                    with ui.row().classes('items-center gap-3'):
                                        status_sel = ui.select(['全部', '未订车', '已订车', '已发货', '已作废'], value=filter_status['value'], label='状态').props('dense outlined').classes('w-28')
                                        cust_in = ui.input('收货人', value=filter_customer['value']).props('dense outlined').classes('w-32')
                                        phone_in = ui.input('手机号', value=filter_phone['value']).props('dense outlined').classes('w-32')
                                        start_in = ui.input('开始日期', value=filter_start['value']).props('dense outlined').classes('w-32')
                                        end_in = ui.input('结束日期', value=filter_end['value']).props('dense outlined').classes('w-32')
                                        
                                        def apply_search():
                                            filter_status['value'] = status_sel.value
                                            filter_customer['value'] = cust_in.value
                                            filter_phone['value'] = phone_in.value
                                            filter_start['value'] = start_in.value
                                            filter_end['value'] = end_in.value
                                            list_refreshable.refresh()
                                            
                                        def apply_reset():
                                            status_sel.value = '全部'
                                            cust_in.value = ''
                                            phone_in.value = ''
                                            start_in.value = ''
                                            end_in.value = ''
                                            apply_search()
                                            
                                        ui.button(icon='search', on_click=apply_search, color='primary').props('dense flat').tooltip('查询')
                                        ui.button(icon='refresh', on_click=apply_reset, color='primary').props('dense flat').tooltip('重置')
                                    
                                    with ui.row().classes('items-center'):
                                        async def export_csv():
                                            import csv
                                            rows = await backend_db.fetch_all_shipments(filter_status['value'], filter_customer['value'], filter_start['value'], filter_end['value'])
                                            output = io.StringIO()
                                            writer = csv.DictWriter(output, fieldnames=["shipment_id", "ship_type", "status", "customer_name", "product_name", "quantity", "delivery_address", "created_at"])
                                            writer.writerow({
                                                "shipment_id": "发货号", "ship_type": "模式", "status": "状态",
                                                "customer_name": "收货人", "product_name": "货物品类", "quantity": "数量",
                                                "delivery_address": "收货地址", "created_at": "创建时间"
                                            })
                                            for row in rows:
                                                clean_row = {k: row.get(k, '') for k in writer.fieldnames}
                                                writer.writerow(clean_row)
                                            csv_data = output.getvalue().encode('utf-8-sig')
                                            ui.download(csv_data, f"骄阳物流总台账导出_{datetime.date.today().isoformat()}.csv")
                                        ui.button(icon='file_download', on_click=export_csv, color='green').props('dense flat tooltip="下载明细CSV"')
                        
                        table.add_slot('body-cell-ship_type', '''
                            <q-td :props="props">
                                <q-badge :color="props.row.ship_type === \'整车\' ? \'purple\' : \'teal\'">{{ props.row.ship_type }}</q-badge>
                            </q-td>
                        ''')
                        table.add_slot('body-cell-status', '''
                            <q-td :props="props">
                                <q-chip 
                                    :color="props.row.status === \'已作废\' ? \'grey\' : (props.row.status === \'已发货\' ? \'green\' : (props.row.status === \'未订车\' ? \'blue\' : \'orange\'))" 
                                    text-color="white" dense size="sm">
                                    {{ props.row.status }}
                                </q-chip>
                            </q-td>
                        ''')
                        table.add_slot('body-cell-batch', '''
                            <q-td :props="props">
                                <span v-if="props.row.batch_id" class="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded cursor-help" :title="props.row.batch_id">
                                    {{ props.row.batch_id.substring(0, 12) + '...' }}
                                </span>
                            </q-td>
                        ''')
                        table.add_slot('body-cell-actions', '''
                            <q-td :props="props">
                                <template v-if="props.row.status !== \'已作废\'">
                                    <q-btn v-if="props.row.status === \'未订车\' || props.row.status === \'已订车\'" 
                                        dense flat color="blue-7" icon="edit" @click="$parent.$emit('edit_shipment', props.row)" class="mr-1"/>
                                    <q-btn dense flat color="teal-7" icon="list_alt" @click="$parent.$emit('show_detail', props.row)" class="mr-1"/>
                                    <q-btn v-if="props.row.status === '未订车'" 
                                        dense color="primary" icon="local_shipping" label="分配物流" @click="$parent.$emit('fill_lingdan', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'未订车\'" 
                                        dense outline color="primary" label="改为已订车" @click="$parent.$emit('mark_booked', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'已订车\'" 
                                        dense color="orange" icon="qr_code" label="发车码" @click="$parent.$emit('show_qr', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.ship_type === '整车' && props.row.status === '已发货'" 
                                        dense flat color="teal-7" icon="history" label="查看回执" @click="$parent.$emit('show_qr', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.ship_type === \'零单\' && props.row.status === \'未订车\'" 
                                        dense color="orange" label="补录快递" @click="$parent.$emit('fill_lingdan', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.status === \'未订车\' || props.row.status === \'已订车\'" 
                                        dense flat color="red-5" icon="delete" @click="$parent.$emit('cancel_shipment', props.row)" class="ml-2"/>
                                    <q-btn v-if="props.row.status === \'已发货\'" 
                                        dense flat color="orange-9" icon="replay" @click="$parent.$emit('rollback_shipment', props.row)" class="ml-2"/>
                                </template>
                            </q-td>
                        ''')
                        
                        def handle_edit_shipment(e):
                            row = e.args
                            curr_sid.set_text(row['shipment_id'])
                            edit_customer.value = row['customer_name']
                            edit_product.value = row['product_name']
                            edit_qty.value = row['quantity']
                            # 🆕 异步加载明细表中的规格
                            async def _load_spec():
                                p_list = await backend_db.get_shipment_products(row['shipment_id'])
                                if p_list: edit_spec.value = p_list[0].get('spec', '')
                                else: edit_spec.value = ''
                            ui.timer(0, _load_spec, once=True)

                            edit_address.value = row['delivery_address']
                            current_edit_ship_type['value'] = row.get('ship_type', '待分配')
                            provider = (row.get('logistics_provider') or '').strip()
                            current_edit_logistics['value'] = provider
                            can_modify_logistics = bool(provider)
                            current_edit_logistics_mutable['value'] = can_modify_logistics
                            edit_selector['set_value'](provider)
                            edit_selector['set_editable'](can_modify_logistics)
                            if can_modify_logistics:
                                edit_mode_hint.text = f"当前业务模式：{row.get('ship_type', '待分配')} | 可修改物流"
                            else:
                                edit_mode_hint.text = f"当前业务模式：{row.get('ship_type', '待分配')} | 未分配物流时不可修改"
                            edit_pickup.value = row.get('pickup_method', '送货上门')
                            edit_payment.value = row.get('payment_method', '现付')
                            edit_unit_price.value = row.get('unit_price', 0)
                            edit_delivery.value = row.get('delivery_fee', 0)
                            edit_manual_freight.value = row.get('freight_fee', 0)
                            dlg_edit.open()
                            
                        def handle_cancel_shipment(e):
                            curr_sid.set_text(e.args['shipment_id'])
                            dlg_cancel.open()
                            
                        def handle_rollback_shipment(e):
                            curr_sid.set_text(e.args['shipment_id'])
                            dlg_rollback.open()
                        
                        async def handle_mark_booked(e):
                            await backend_db.update_zhengche_to_yidingche(e.args['shipment_id'])
                            ui.notify('已变更为已订车', type='info')
                            list_refreshable.refresh()
                        
                        async def handle_show_qr(e):
                            sid = e.args.get('shipment_id', '')
                            tk = e.args.get('driver_token', '')
                            if not tk: return
                            try:
                                base_url = await backend_db.get_setting('driver_base_url', default_driver_base_url)
                                if not (base_url.startswith('http://') or base_url.startswith('https://')):
                                    ui.notify('司机端访问前缀格式错误，请先保存正确链接', type='warning')
                                    return
                                url = f"{base_url.rstrip('/')}/driver_confirm?id={sid}&token={tk}"
                                b64 = generate_qr_base64(url)
                                qr_img.set_source(b64) 
                            except Exception as ex:
                                ui.notify(f'凭证生成失败：{ex}', type='negative')
                            dlg_qr.open()
                            
                        async def handle_fill_lingdan(e):
                            curr_sid.set_text(e.args['shipment_id'])
                            latest_opts_raw = await backend_db.get_setting('logistics_provider_options', default_logistics_options)
                            latest_options = parse_logistics_options(latest_opts_raw)
                            logistics_options.clear()
                            logistics_options.extend(latest_options)
                            refresh_all_logistics_selectors()
                            lingdan_selector['set_value']('')
                            trk_in.value = ''
                            dlg_lingdan.open()

                        async def handle_show_detail(e):
                            sid = e.args.get('shipment_id', '')
                            _page_ctx['detail_shipment_id'] = sid
                            # 通过页面上下文桥接SPA切换
                            if 'panels' in _page_ctx:
                                _page_ctx['panels'].value = 'detail_view'
                            if 'detail_refresh' in _page_ctx:
                                _page_ctx['detail_refresh'].refresh()

                        table.on('edit_shipment', handle_edit_shipment)
                        table.on('cancel_shipment', handle_cancel_shipment)
                        table.on('rollback_shipment', handle_rollback_shipment)
                        table.on('mark_booked', handle_mark_booked)
                        table.on('show_qr', handle_show_qr)
                        table.on('fill_lingdan', handle_fill_lingdan)
                        table.on('show_detail', handle_show_detail)

                _page_ctx['shipments_refresh'] = list_refreshable
                await list_refreshable()
    
    await main_shipments_refreshable()

# ════════════════════════════════════════════════
#  SPA 页面组件：数据看板 & 费用核算
# ════════════════════════════════════════════════

async def dashboard_content():
    stats = await backend_db.get_dashboard_stats()
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12'):
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('数据资产与作业看板').classes('text-2xl font-bold tracking-tight text-gray-800')
        with ui.row().classes('w-full gap-6 mb-6'):
            def kpi_card(title, value, color_class, icon):
                with ui.card().classes(f'modern-card flex-grow p-6 border-l-4 {color_class}'):
                    with ui.row().classes('justify-between items-center w-full'):
                        with ui.column():
                            ui.label(title).classes('text-gray-500 text-sm font-bold')
                            ui.label(str(value)).classes('text-4xl font-black mt-2 text-gray-800')
                        ui.icon(icon, size='2.5rem', color='grey-4')
            kpi_card('今日新增', stats['today_orders'], 'border-l-blue-500', 'add_shopping_cart')
            kpi_card('积压未发数', stats['pending_count'], 'border-l-orange-500', 'hourglass_empty')
            kpi_card('今日已发车', stats['shipped_today'], 'border-l-green-500', 'local_shipping')
        with ui.row().classes('w-full gap-6'):
            with ui.card().classes('modern-card p-6 w-1/3'):
                ui.label('状态分布').classes('text-lg font-bold mb-4')
                for item in stats['status_dist']:
                    with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-100'):
                        ui.label(item['status']).classes('text-gray-600')
                        ui.label(str(item['cnt'])).classes('font-bold text-lg')
            with ui.card().classes('modern-card p-6 flex-grow'):
                ui.label('当日作业流水').classes('text-lg font-bold mb-4')
                cols = [{'name': 'id', 'label': 'ID', 'field': 'shipment_id'},{'name': 'type', 'label': '类型', 'field': 'ship_type'},{'name': 'status', 'label': '状态', 'field': 'status'}]
                ui.table(columns=cols, rows=stats['today_shipments']).classes('w-full').props('dense flat')

async def finance_content():
    summary = await backend_db.get_finance_summary()
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12'):
        ui.label('财务核算与利差对账').classes('text-2xl font-bold tracking-tight text-gray-800 mb-6')
        with ui.card().classes('modern-card w-full p-6 mb-6 bg-gray-50'):
            with ui.row().classes('w-full gap-12'):
                ui.html(f'<div><div class="text-sm text-gray-500">累计托运单运输费收入</div><div class="text-2xl font-bold text-blue-600">¥ {summary.get("total_fee", 0):.2f}</div></div>')
                ui.html(f'<div><div class="text-sm text-gray-500">累计实付运输费支出</div><div class="text-2xl font-bold text-red-500">¥ {summary.get("total_cost", 0):.2f}</div></div>')
                ui.html(f'<div><div class="text-sm text-gray-500">累计净利</div><div class="text-3xl font-black text-green-600">¥ {summary.get("total_profit", 0):.2f}</div></div>')
        with ui.card().classes('modern-card w-full p-6'):
            curr_sid = ui.label().classes('hidden')
            fee_weight_label = ui.label('').classes('hidden')
            dlg_fee = ui.dialog()
            with dlg_fee, ui.card().classes('p-6 min-w-[400px]'):
                ui.label('实付运输费核算').classes('font-bold text-lg mb-2')
                fee_info_label = ui.label('').classes('text-sm text-gray-500 mb-4')
                actual_up_input = ui.number('实付单价(元/吨)', value=0, min=0, format='%.2f').classes('w-full mb-2')
                actual_df_input = ui.number('实付运送费(元)', value=0, min=0, format='%.2f').classes('w-full mb-4')
                async def save_fee():
                    await backend_db.update_shipment_fee(
                        curr_sid.text,
                        float(actual_up_input.value or 0),
                        float(actual_df_input.value or 0),
                    )
                    ui.notify('实付费用已登记，利润已自动计算', type='positive')
                    dlg_fee.close()
                    fin_table.refresh()
                ui.button('保存并计算利润', on_click=save_fee, color='green').classes('w-full')
            @ui.refreshable
            async def fin_table():
                rows = await backend_db.fetch_shipped_shipments()
                cols = [
                    {'name': 'shipment_id', 'label': '发货号', 'field': 'shipment_id', 'align': 'left'},
                    {'name': 'customer_name', 'label': '客户', 'field': 'customer_name', 'align': 'left'},
                    {'name': 'total_weight', 'label': '总重量(吨)', 'field': 'total_weight', 'align': 'center'},
                    {'name': 'freight_fee', 'label': '托运单运输费', 'field': 'freight_fee', 'align': 'center'},
                    {'name': 'actual_cost', 'label': '实付运输费', 'field': 'actual_cost', 'align': 'center'},
                    {'name': 'profit', 'label': '利润', 'field': 'profit', 'align': 'center'},
                    {'name': 'actions', 'label': '操作', 'align': 'center'},
                ]
                with ui.table(columns=cols, rows=rows, row_key='shipment_id').classes('w-full') as ft:
                    ft.add_slot('body-cell-actions', '<q-td :props="props"><q-btn outline dense color="secondary" label="登记实付" @click="$parent.$emit(\'edit_fee\', props.row)" /></q-td>')
                    def on_edit_fee(e):
                        row = e.args
                        curr_sid.set_text(row['shipment_id'])
                        tw = row.get('total_weight', 0) or 0
                        ff = row.get('freight_fee', 0) or 0
                        fee_info_label.text = f'总重量: {tw}吨 | 托运单运输费: ¥{ff} | 公式: 实付运输费 = 总重量 × 实付单价 + 实付运送费'
                        actual_up_input.value = row.get('actual_unit_price', 0) or 0
                        actual_df_input.value = row.get('actual_delivery_fee', 0) or 0
                        dlg_fee.open()
                    ft.on('edit_fee', on_edit_fee)
            await fin_table()

# ════════════════════════════════════════════════
#  SPA 主入口 & 规格配置
# ════════════════════════════════════════════════

@ui.page('/')
async def main_page():
    inject_modern_css()
    active_tab = 'shipments'
    def switch_to_tab(tab_name: str):
        nonlocal active_tab
        active_tab = tab_name
        panels.value = tab_name
        for k, btn in sidebar_btns.items():
            if k == tab_name: btn.classes('sidebar-item-active', remove='text-gray-400 hover:bg-gray-700 hover:text-white')
            else: btn.classes('text-gray-400 hover:bg-gray-700 hover:text-white', remove='sidebar-item-active')

    with ui.header().classes('bg-white text-gray-800 border-b border-gray-200 px-4 flex items-center justify-between'):
        with ui.row().classes('items-center gap-2'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat round color=primary')
            ui.label('骄阳物流调度后台').classes('font-bold text-lg hidden md:block')
        with ui.row().classes('items-center gap-4 text-sm'):
            ui.label(f"📅 {datetime.date.today()}").classes('text-gray-400')
            ui.icon('account_circle', size='sm').classes('text-gray-400')

    with ui.left_drawer(fixed=True).classes('bg-slate-900 text-white w-30 min-h-screen flex flex-col p-0') as left_drawer:
        with ui.row().classes('items-center gap-3 p-4 pl-6 mb-2 mt-4 w-full'):
            ui.icon('local_shipping', size='lg', color='blue-400')
            ui.label('骄阳物流').classes('text-lg font-bold text-white tracking-widest')
        with ui.column().classes('flex-grow px-3 gap-1 w-full'):
            sidebar_btns = {}
            for key, icon, label in [('shipments', '📦', '发货调度'),('dashboard', '📊', '数据看板'),('finance', '💰', '费用核算'),('settings', '⚙️', '系统设置')]:
                with ui.row().classes('w-full items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-colors text-gray-400 hover:bg-gray-700 hover:text-white') as btn:
                    sidebar_btns[key] = btn
                    ui.label(icon).classes('text-lg')
                    ui.label(label).classes('font-medium')
                    btn.on('click', lambda k=key: switch_to_tab(k))
        with ui.row().classes('p-4 border-t border-gray-700 w-full'):
            ui.button('收起菜单', icon='chevron_left', on_click=left_drawer.toggle).props('flat dense size=sm').classes('text-gray-500 w-full')

    # ── 商品明细下钻面板（全景视口）──
    @ui.refreshable
    async def detail_view_refreshable():
        sid = _page_ctx.get('detail_shipment_id', '')
        detail_rows = await backend_db.get_shipment_products(sid) if sid else []
        ship_info = await backend_db.get_shipment_by_id(sid) if sid else {}
        allow_edit_shipped = (await backend_db.get_setting('allow_edit_shipped_weight', '0')) == '1'
        can_edit_weight = bool(ship_info) and (ship_info.get('status') in ('未订车', '已订车') or allow_edit_shipped)
        logs = await backend_db.get_shipment_weight_logs(sid) if sid else []

        editable_rows: list[dict] = []
        for r in detail_rows:
            editable_rows.append({
                'id': r.get('id'),
                'shipment_id': sid,
                'product_name': r.get('product_name', ''),
                'spec': r.get('spec', ''),
                'parsed_spec': r.get('parsed_spec', ''),
                'quantity': int(float(r.get('quantity', 0) or 0)),
                'unit_weight_kg': float(r.get('unit_weight_kg', 0) or 0),
                'line_weight_kg': float(r.get('line_weight_kg', 0) or 0),
            })

        _page_ctx['detail_pending_edits'] = _page_ctx.get('detail_pending_edits', {})
        pending_edits = _page_ctx['detail_pending_edits']

        def patch_row(row_id: int, key: str, value):
            target = next((x for x in editable_rows if int(x.get('id') or 0) == int(row_id)), None)
            if not target:
                return
            target[key] = value
            qty = int(float(target.get('quantity', 0) or 0))
            unit_w = float(target.get('unit_weight_kg', 0) or 0)
            if key in {'quantity', 'unit_weight_kg'}:
                target['line_weight_kg'] = round(qty * unit_w, 3)
            pending_edits[row_id] = dict(target)

        with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12 gap-4'):
            # ── 顶部动作栏 ──
            with ui.row().classes('w-full justify-between items-center bg-white p-4 rounded-xl border shadow-sm'):
                with ui.row().classes('items-center gap-3'):
                    ui.button(icon='arrow_back', on_click=lambda: switch_to_tab('shipments')).props('flat round color=primary')
                    ui.label(f'订单明细：{sid or "-"}').classes('text-xl font-bold text-gray-800')

                with ui.row().classes('gap-2 items-center'):
                    save_btn_holder = ui.row().classes('items-center')
                    async def export_detail_excel():
                        if not detail_rows:
                            ui.notify('无商品明细可导出', type='warning')
                            return
                        import csv
                        output = io.StringIO()
                        # 动态获取所有列名
                        all_keys = list(dict.fromkeys(k for row in detail_rows for k in row.keys()))
                        writer = csv.DictWriter(output, fieldnames=all_keys)
                        writer.writeheader()
                        for row in detail_rows:
                            writer.writerow({k: row.get(k, '') for k in all_keys})
                        csv_bytes = output.getvalue().encode('utf-8-sig')
                        ui.download(csv_bytes, f'订单明细_{sid}.csv')
                    ui.button('📥 导出明细 Excel', on_click=export_detail_excel, color='green-7').props('outline')

            if ship_info:
                with ui.card().classes('w-full p-4 bg-blue-50 border border-blue-100 rounded-xl shadow-sm'):
                    with ui.grid(columns=4).classes('w-full gap-2'):
                        ui.label(f"发货单号：{sid}").classes('text-sm text-blue-900')
                        ui.label(f"收货人：{ship_info.get('customer_name','')}").classes('text-sm text-blue-900')
                        ui.label(f"总件数：{ship_info.get('quantity',0)}").classes('text-sm text-blue-900')
                        ui.label(f"总运费：¥{ship_info.get('freight_fee',0)}").classes('text-sm text-blue-900')
                        ui.label(f"状态：{ship_info.get('status','')}").classes('text-sm text-blue-900')
                        ui.label(f"总重量：{ship_info.get('total_weight',0)}吨").classes('text-sm text-blue-900')
                        ui.label(f"物流：{ship_info.get('logistics_provider','') or '-'}").classes('text-sm text-blue-900')
                        ui.label(f"地址：{ship_info.get('delivery_address','')}").classes('text-sm text-blue-900 truncate')

            # ── 下方：动态列宽表 ──
            with ui.card().classes('modern-card w-full p-6'):
                if not detail_rows:
                    with ui.column().classes('w-full items-center py-12'):
                        ui.icon('inbox', size='4rem', color='grey-4')
                        ui.label('该发货单暂无商品明细记录').classes('text-gray-400 text-lg mt-4')
                        ui.label('通过 Excel 导入创建的发货单才会有完整的商品明细行').classes('text-gray-300 text-sm')
                else:
                    cols = [
<<<<<<< codex/fix-auto-update-for-shipping-order-weight
                        {'name': 'product_name', 'label': '品名', 'field': 'product_name', 'align': 'left', 'style': 'width: 28%;', 'headerStyle': 'width: 28%; text-align: left;'},
                        {'name': 'spec', 'label': '规格', 'field': 'spec', 'align': 'center', 'style': 'width: 16%;', 'headerStyle': 'width: 16%; text-align: center;'},
                        {'name': 'quantity', 'label': '件数', 'field': 'quantity', 'align': 'center', 'style': 'width: 12%;', 'headerStyle': 'width: 12%; text-align: center;'},
                        {'name': 'unit_weight_kg', 'label': '单重(kg)', 'field': 'unit_weight_kg', 'align': 'center', 'style': 'width: 14%;', 'headerStyle': 'width: 14%; text-align: center;'},
                        {'name': 'line_weight_kg', 'label': '行重(kg)', 'field': 'line_weight_kg', 'align': 'center', 'style': 'width: 14%;', 'headerStyle': 'width: 14%; text-align: center;'},
                    ]
                    ui.label(f'共 {len(editable_rows)} 条商品记录（单重变更将自动同步行重）').classes('text-sm text-gray-500 mb-2')
                    with ui.table(columns=cols, rows=editable_rows, row_key='id').props('table-style="table-layout:fixed;width:100%"').classes('w-full') as editable_table:
=======
                        {'name': 'product_name', 'label': '品名', 'field': 'product_name', 'align': 'left'},
                        {'name': 'spec', 'label': '规格', 'field': 'spec', 'align': 'center'},
                        {'name': 'quantity', 'label': '件数', 'field': 'quantity', 'align': 'center'},
                        {'name': 'unit_weight_kg', 'label': '单重(kg)', 'field': 'unit_weight_kg', 'align': 'center'},
                        {'name': 'line_weight_kg', 'label': '行重(kg)', 'field': 'line_weight_kg', 'align': 'center'},
                        {'name': 'weight_source', 'label': '计费方', 'field': 'weight_source', 'align': 'center'},
                    ]
                    ui.label(f'共 {len(editable_rows)} 条商品记录（单重变更将自动同步行重）').classes('text-sm text-gray-500 mb-2')
                    with ui.table(columns=cols, rows=editable_rows, row_key='id').classes('w-full') as editable_table:
>>>>>>> main
                        editable_table.add_slot('body', r'''
                            <q-tr :props="props">
                                <q-td key="product_name" :props="props" class="text-left">
                                    <q-input dense borderless v-model="props.row.product_name" input-class="text-left"
                                        @update:model-value="$parent.$emit('cell_change', {id: props.row.id, key:'product_name', value: $event})" />
                                </q-td>
                                <q-td key="spec" :props="props" class="text-center">
                                    <q-input dense borderless v-model="props.row.spec" input-class="text-center"
                                        @update:model-value="$parent.$emit('cell_change', {id: props.row.id, key:'spec', value: $event})" />
                                </q-td>
<<<<<<< codex/fix-auto-update-for-shipping-order-weight
                                <q-td key="quantity" :props="props" class="text-center">
                                    <q-input dense borderless type="number" v-model.number="props.row.quantity" input-class="text-center"
                                        @update:model-value="(props.row.line_weight_kg = Math.round(((Number($event) || 0) * (Number(props.row.unit_weight_kg) || 0)) * 1000) / 1000, $parent.$emit('cell_change', {id: props.row.id, key:'quantity', value: $event}), $parent.$emit('cell_change', {id: props.row.id, key:'line_weight_kg', value: props.row.line_weight_kg}))" />
                                </q-td>
                                <q-td key="unit_weight_kg" :props="props" class="text-center">
                                    <q-input dense borderless type="number" step="0.001" v-model.number="props.row.unit_weight_kg" input-class="text-center"
                                        @update:model-value="(props.row.line_weight_kg = Math.round(((Number(props.row.quantity) || 0) * (Number($event) || 0)) * 1000) / 1000, $parent.$emit('cell_change', {id: props.row.id, key:'unit_weight_kg', value: $event}), $parent.$emit('cell_change', {id: props.row.id, key:'line_weight_kg', value: props.row.line_weight_kg}))" />
=======
                                <q-td key="quantity" :props="props">
                                    <q-input dense borderless type="number" v-model.number="props.row.quantity"
                                        @update:model-value="(props.row.line_weight_kg = Math.round(((Number($event) || 0) * (Number(props.row.unit_weight_kg) || 0)) * 1000) / 1000, $parent.$emit('cell_change', {id: props.row.id, key:'quantity', value: $event}), $parent.$emit('cell_change', {id: props.row.id, key:'line_weight_kg', value: props.row.line_weight_kg}))" />
                                </q-td>
                                <q-td key="unit_weight_kg" :props="props">
                                    <q-input dense borderless type="number" step="0.001" v-model.number="props.row.unit_weight_kg"
                                        @update:model-value="(props.row.line_weight_kg = Math.round(((Number(props.row.quantity) || 0) * (Number($event) || 0)) * 1000) / 1000, $parent.$emit('cell_change', {id: props.row.id, key:'unit_weight_kg', value: $event}), $parent.$emit('cell_change', {id: props.row.id, key:'line_weight_kg', value: props.row.line_weight_kg}))" />
                                </q-td>
                                <q-td key="line_weight_kg" :props="props">
                                    <q-input dense borderless readonly input-class="text-gray-700" type="number" step="0.001" v-model.number="props.row.line_weight_kg" />
>>>>>>> main
                                </q-td>
                                <q-td key="line_weight_kg" :props="props" class="text-center">
                                    <q-input dense borderless readonly input-class="text-gray-700 text-center" type="number" step="0.001" v-model.number="props.row.line_weight_kg" />
                                </q-td>
                            </q-tr>
                        ''')
                        def on_cell_change(e):
                            data = e.args
                            patch_row(int(data['id']), data['key'], data['value'])
                        editable_table.on('cell_change', on_cell_change)

                    if not can_edit_weight:
                        ui.label('当前状态默认禁止编辑；如需修改已发货单，请在系统配置打开特权。').classes('text-xs text-gray-500 mt-2')
                    else:
                        save_btn = None
                        async def save_all_changes():
                            if not pending_edits:
                                ui.notify('没有可保存的变更', type='warning')
                                return
                            save_btn.props(add='loading')
                            try:
                                await backend_db.update_order_item_batch(list(pending_edits.values()))
                                # 🆕 批量更新后立即重算主表总重和运费
                                await backend_db.recalc_shipment_weight_and_fee(sid)
                                ui.notify('修改成功并已刷新总重/运费', type='positive', position='top')
                                pending_edits.clear()
                                detail_view_refreshable.refresh()
                                shipments_refresh = _page_ctx.get('shipments_refresh')
                                if shipments_refresh:
                                    shipments_refresh.refresh()
                            except Exception as ex:
                                ui.notify(f'保存失败：{ex}', type='negative', position='top')
                            finally:
                                save_btn.props(remove='loading')
                        with save_btn_holder:
                            save_btn = ui.button('💾 保存所有修改', on_click=save_all_changes, color='primary')

                    if logs:
                        with ui.expansion('最近重量修改记录', icon='history').classes('mt-3 w-full'):
                            for lg in logs[:20]:
                                ui.label(
                                    f"[{lg.get('created_at','')}] 行#{lg.get('product_row_id')} 单重 {lg.get('old_unit_weight_kg')}→{lg.get('new_unit_weight_kg')}kg, 行重 {lg.get('old_line_weight_kg')}→{lg.get('new_line_weight_kg')}kg, 备注:{lg.get('note','')}"
                                ).classes('text-xs text-gray-600 mb-1')

    with ui.tab_panels(value='shipments').classes('w-full bg-transparent h-full') as panels:
        with ui.tab_panel('shipments').classes('p-0'): await shipments_content()
        with ui.tab_panel('dashboard').classes('p-0'): await dashboard_content()
        with ui.tab_panel('finance').classes('p-0'): await finance_content()
        with ui.tab_panel('settings').classes('p-0'): await settings_content()
        with ui.tab_panel('detail_view').classes('p-0'): await detail_view_refreshable()

    # 将 panels 和 refreshable 注册到模块级上下文，供 shipments_content 等外部函数使用
    _page_ctx['panels'] = panels
    _page_ctx['detail_refresh'] = detail_view_refreshable

    switch_to_tab('shipments')

async def settings_content():
    with ui.column().classes('w-full max-w-4xl mx-auto mt-6 px-4 mb-12 gap-6'):
        ui.label('⚙️ 系统配置').classes('text-2xl font-bold tracking-tight text-gray-800')
        with ui.card().classes('modern-card w-full p-6'):
            ui.label('🔧 系统参数').classes('text-lg font-bold mb-4')
            default_driver_base_url = f"http://{get_local_ip()}:8600"
            current_driver_base_url = await backend_db.get_setting('driver_base_url', default_driver_base_url)
            default_logistics_options = '整车,罗氏物流,小鹏物流'
            current_logistics_options = await backend_db.get_setting('logistics_provider_options', default_logistics_options)
            allow_edit_shipped = await backend_db.get_setting('allow_edit_shipped_weight', '0')

            driver_prefix_input = ui.input('司机端访问前缀', value=(current_driver_base_url or default_driver_base_url)).props('outlined').classes('w-full mb-3')
            logistics_options_input = ui.input('物流选项（逗号分隔）', value=current_logistics_options or default_logistics_options).props('outlined').classes('w-full mb-3')
            allow_edit_checkbox = ui.checkbox('允许编辑已发货单重量（特权）', value=allow_edit_shipped == '1').classes('mb-3')

            async def save_system_params():
                driver_val = (driver_prefix_input.value or '').strip()
                if not driver_val:
                    ui.notify('司机端访问前缀不能为空', type='warning')
                    return
                if not (driver_val.startswith('http://') or driver_val.startswith('https://')):
                    ui.notify('司机端访问前缀需以 http:// 或 https:// 开头', type='warning')
                    return

                parsed_opts = parse_logistics_options(logistics_options_input.value)
                if not parsed_opts:
                    ui.notify('请至少保留一个物流选项', type='warning')
                    return

                await backend_db.set_setting('driver_base_url', driver_val.rstrip('/'))
                await backend_db.set_setting('logistics_provider_options', ','.join(parsed_opts))
                await backend_db.set_setting('allow_edit_shipped_weight', '1' if allow_edit_checkbox.value else '0')
                ui.notify('系统参数已保存', type='positive')

            with ui.row().classes('w-full justify-end'):
                ui.button('保存系统参数', on_click=save_system_params, color='primary')

        with ui.card().classes('modern-card w-full p-6'):
            ui.label('📦 规格配置').classes('text-lg font-bold mb-4')
            @ui.refreshable
            async def spec_table_refreshable():
                rows = await backend_db.get_all_spec_weights()
                cols = [{'name': 'spec', 'label': '规格名称', 'field': 'spec', 'align': 'left'},{'name': 'weight', 'label': '单重(kg)', 'field': 'weight_kg', 'align': 'center'},{'name': 'acts', 'label': '', 'align': 'center'}]
                with ui.table(columns=cols, rows=rows, row_key='spec').classes('w-full') as st:
                    st.add_slot('body-cell-acts', '<q-td :props="props"><q-btn flat color="red" icon="delete" @click="$parent.$emit(\'del\', props.row)"/></q-td>')
                    async def on_del(e):
                        await backend_db.delete_spec_weight(e.args['spec'])
                        spec_table_refreshable.refresh()
                    st.on('del', on_del)
            await spec_table_refreshable()
            
            with ui.row().classes('w-full items-end gap-2 mt-4'):
                ns = ui.input('规格').classes('flex-1')
                nw = ui.number('单重(kg)', value=0).classes('w-36')
                async def do_add():
                    if not ns.value: return
                    await backend_db.save_spec_weight(ns.value, float(nw.value))
                    ns.value = ''
                    spec_table_refreshable.refresh()
                ui.button('➕ 新增', on_click=do_add, color='primary')

@ui.page('/driver_confirm')
async def driver_confirm_page(id: str = '', token: str = ''):
    """手机端即扫即用页面，无 Header/Sidebar，移动端适配。"""
    ui.page_title('司机发车确认')
    # 注入基础移动端优化 css (覆盖可能冲突的全局样式)
    ui.add_head_html('''
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <style>
            body, html { background-color: #F8FAFC !important; margin: 0; padding: 0; visibility: visible !important; min-height: 100vh; }
            #app { display: flex; flex-direction: column; min-height: 100%; visibility: visible !important; }
        </style>
    ''')
    
    with ui.column().classes('w-full max-w-lg mx-auto p-4 items-center min-h-screen').style('visibility: visible !important;'):
        ui.label('🚚 极速物流发货单').classes('text-2xl font-black text-blue-900 mt-6 mb-8')
        
        if not id or not token:
            ui.label('❌ 二维码无效或缺少参数').classes('text-red-500 font-bold')
            return
            
        ship = await backend_db.get_shipment_by_id(id)
        if not ship or ship['driver_token'] != token:
            ui.label('❌ 鉴权失败：订单不存在或发车码失效').classes('text-red-500 font-bold p-6 bg-red-50 rounded text-center')
            return
            
        if ship['status'] == '已发货':
            with ui.column().classes('w-full items-center p-8 bg-green-50 rounded-xl border border-green-200 mt-10'):
                ui.icon('check_circle', size='6xl', color='green')
                ui.label('认证成功').classes('text-2xl font-bold text-green-800 mt-4')
                ui.label(f"承运人: {ship.get('driver_name', '')} ({ship.get('truck_plate', '')})").classes('text-gray-600 mt-2')
                ui.label('祝师傅一路顺风，平安到达！').classes('text-green-700 font-bold mt-4')
            return
            
        # ── 正常填报流 ──
        with ui.card().classes('w-full p-5 rounded-xl border-t-4 border-t-primary shadow-sm mb-6'):
            ui.label('📦 配送任务简报').classes('font-bold text-gray-500 mb-2')
            ui.label(f"目的地: {ship['delivery_address']}").classes('text-xl font-bold text-gray-800 leading-tight mb-2')
            ui.label(f"物品: {ship['product_name']} | {ship['quantity']}件").classes('text-md bg-blue-50 text-blue-800 p-2 rounded')
            
        with ui.card().classes('w-full p-5 rounded-xl shadow-sm'):
            ui.label('🧑‍🔧 填报车辆资质').classes('font-bold text-lg mb-4')
            d_name = ui.input('真实姓名*').props('outlined dense').classes('w-full mb-3')
            d_id = ui.input('身份证号').props('outlined dense').classes('w-full mb-3')
            d_phone = ui.input('手机号*').props('outlined dense type=tel').classes('w-full mb-3')
            ui.separator().classes('mb-3')
            t_plate = ui.input('车牌号* (例: 闽A88888)').props('outlined dense').classes('w-full mb-3')
            t_type = ui.select(['4.2米轻卡','6.8米中卡','9.6米重卡','13.5米挂车','17.5米平板','其他'], 
                               label='车型*').props('outlined dense').classes('w-full mb-6')
            
            async def submit_info():
                if not all([d_name.value, d_phone.value, t_plate.value, t_type.value]):
                    ui.notify('请完整填写带有*号的必填信息', type='negative')
                    return
                await backend_db.confirm_zhengche_driver(
                    id, d_name.value, d_id.value, d_phone.value, t_plate.value, t_type.value
                )
                ui.notify('确认发车成功！', type='positive')
                ui.navigate.to(f'/driver_confirm?id={id}&token={token}')
                
            ui.button('确认装货完毕，立即发车', on_click=submit_info).classes('w-full h-14 bg-blue-600 text-white font-bold text-lg rounded-lg shadow-lg')

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='骄阳物流调度系统', port=8600, host='0.0.0.0', language='zh-CN', favicon='🚚')
