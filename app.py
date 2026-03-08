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
                
                # ── 新建发货单入口 ──
                dlg_new_shipment = ui.dialog()
                with dlg_new_shipment, ui.card().classes('new-shipment-dialog w-[780px] max-w-[96vw] max-h-[90vh] p-0 overflow-y-auto'):
                    with ui.row().classes('w-full justify-between items-center px-6 py-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-blue-100'):
                        with ui.column().classes('gap-0'):
                            ui.label('📝 新建发货单').classes('text-lg font-bold text-gray-800')
                            ui.label('支持手工录入与 Excel 一键回填').classes('text-xs text-gray-500')
                        ui.button(icon='close', on_click=dlg_new_shipment.close).props('flat round dense')
                    
                    imported_products: list[dict] = []
                    
                    with ui.card().classes('mx-6 mt-4 p-4 bg-gradient-to-br from-slate-50 to-blue-50 border border-blue-100 shadow-sm rounded-xl'):
                        ui.label('数据录入方式').classes('section-title')
                        ui.label('推荐：先导入 Excel 自动回填，再快速补全字段').classes('text-xs text-gray-400 mb-3')
                        mode_tabs = ui.tabs().classes('mode-switch')
                        with mode_tabs:
                            manual_tab = ui.tab('✍️ 手工录入')
                            excel_tab = ui.tab('📑 Excel 导入')
                        with ui.tab_panels(mode_tabs, value=manual_tab).classes('w-full bg-transparent shadow-none mt-3 fixed-mode-panels'):
                            with ui.tab_panel(manual_tab).classes('px-0 py-2 h-full'):
                                with ui.row().classes('mode-card items-center w-full'):
                                    ui.icon('edit_note', color='blue-6').classes('text-xl')
                                    ui.label('手工模式：适合临时新增，支持快速填单').classes('text-sm text-blue-900 font-medium')
                            with ui.tab_panel(excel_tab).classes('px-0 py-2 h-full'):
                                with ui.row().classes('w-full items-center p-3 bg-blue-50 rounded-lg border border-blue-100 gap-2'):
                                    ui.icon('upload_file', color='blue-5').classes('text-2xl mr-2')
                                    ui.label('从客户订单 Excel 导入并自动回填').classes('text-sm font-bold text-blue-800 flex-1')

                                    async def on_excel_upload(e):
                                        try:
                                            import tempfile, os, asyncio
                                            filename = getattr(e, 'name', getattr(e, 'filename', 'order.xlsx'))
                                            suffix = Path(filename).suffix or '.xlsx'
                                            content_io = getattr(e, 'content', None) or getattr(e, 'file', None)
                                            if content_io is None: return
                                            raw = content_io.read()
                                            if asyncio.iscoroutine(raw): raw = await raw
                                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                                tmp.write(raw)
                                                tmp_path = tmp.name

                                            data = waybill_generator.parse_order_excel(tmp_path)
                                            os.unlink(tmp_path)

                                            customer_input.value = data['receiver_name']
                                            phone_input.value = data['receiver_phone']
                                            address_input.value = data['receiver_address']

                                            prods = data.get('products', [])
                                            if prods:
                                                product_input.value = '、'.join([p['name'] for p in prods[:3]])
                                                qty_input.value = sum(p['qty'] for p in prods)
                                            imported_products.clear()
                                            imported_products.extend(prods)
                                            ui.notify(f'订单导入成功！识别到 {len(prods)} 个商品', type='positive')
                                        except Exception as ex:
                                            ui.notify(f'导入失败：{ex}', type='negative')

                                    ui.upload(on_upload=on_excel_upload, auto_upload=True, label='新增 Excel').props('accept=".xlsx,.xls" color=blue-6 bordered').classes('upload-pill max-w-[360px]')
                                ui.label('支持 .xlsx / .xls，导入后将自动填充收货人、地址、货品和数量。').classes('text-xs text-blue-700 mt-2')
                    
                    with ui.column().classes('px-6 pb-4 gap-3'):
                        with ui.column().classes('section-card w-full gap-1'):
                            ui.label('收货信息').classes('section-title')
                            with ui.row().classes('w-full gap-2'):
                                customer_input = ui.input('收货人*').classes('flex-1 mb-1')
                                phone_input = ui.input('收货电话').classes('flex-1 mb-1')
                            with ui.row().classes('w-full gap-2'):
                                product_input = ui.input('货物品类*').classes('flex-[2] mb-1')
                                qty_input = ui.number('数量(件)*', value=1, min=1, format='%.0f').classes('flex-1 mb-1')
                            address_input = ui.input('收货详细地址*').classes('w-full mb-1')

                        with ui.column().classes('section-card w-full gap-1 bg-slate-50 border-slate-200'):
                            ui.label('运费配置').classes('section-title')
                            with ui.row().classes('w-full gap-2 mb-1'):
                                new_unit_price = ui.number('单价(元/吨)*', value=0, min=0, format='%.2f').classes('flex-1')
                                new_delivery_fee = ui.number('运送费(元)*', value=0, min=0, format='%.2f').classes('flex-1')
                            with ui.row().classes('w-full items-center justify-between gap-2 p-2 rounded-lg bg-white border border-blue-100'):
                                new_freight_display = ui.label('→ 托运单运输费: ¥0.00').classes('text-sm font-bold text-blue-700')
                                ui.label('业务模式将在后续【分配物流】自动判定（整车/零单）').classes('text-xs text-gray-500 text-right')
                    
                    async def submit_shipment():
                        if not customer_input.value or not product_input.value or not address_input.value:
                            ui.notify('请完整填写必填项', type='warning')
                            return
                        # 计算总重量
                        spec_rows = await backend_db.get_all_spec_weights()
                        sw = {r['spec']: r['weight_kg'] for r in spec_rows}
                        prods = imported_products if imported_products else [{'name': product_input.value, 'spec': '', 'qty': int(qty_input.value)}]
                        total_qty, total_weight_t = waybill_generator.calc_total_weight(prods, sw)
                        # 公式: 托运单运输费 = 总重量 * 单价 + 运送费
                        up = float(new_unit_price.value or 0)
                        df = float(new_delivery_fee.value or 0)
                        freight_fee = round(total_weight_t * up + df, 2)
                        
                        new_sid = await backend_db.create_shipment(
                            customer_input.value, 
                            product_input.value,
                            int(qty_input.value), 
                            address_input.value,
                            '待分配',
                            customer_phone=phone_input.value,
                            total_weight=total_weight_t,
                            unit_price=up,
                            delivery_fee=df,
                            freight_fee=freight_fee,
                        )
                        # 持久化商品明细到子表（含 Excel 原始全量数据）
                        if imported_products:
                            await backend_db.save_shipment_products(new_sid, imported_products)
                        ui.notify(f'发货单已生成 | 总重量: {total_weight_t}吨 | 托运单运输费: ¥{freight_fee}', type='positive')
                        customer_input.value = ''
                        phone_input.value = ''
                        product_input.value = ''
                        qty_input.value = 1
                        address_input.value = ''
                        new_unit_price.value = 0
                        new_delivery_fee.value = 0
                        new_freight_display.text = '→ 托运单运输费: ¥0.00'
                        imported_products.clear()
                        dlg_new_shipment.close()
                        list_refreshable.refresh()

                    with ui.row().classes('w-full justify-center items-center gap-3 mt-6 px-6 py-4 bg-white border-t border-gray-100'):
                        ui.button('取消', on_click=dlg_new_shipment.close).props('outline text-gray-600 border-gray-300')
                        ui.button('确认并立即生单', on_click=submit_shipment, color='primary')
                
                ui.button('新建发货单', icon='add', on_click=dlg_new_shipment.open).classes('bg-primary text-white font-bold')

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
                        freight_fee = round(total_weight_t * up + df, 2)
                        
                        provider = current_edit_logistics['value']
                        inferred_mode = current_edit_ship_type['value']
                        if current_edit_logistics_mutable['value']:
                            provider = edit_selector['get_value']()
                            inferred_mode = '整车' if provider == '整车' else ('零单' if provider else current_edit_ship_type['value'])

                        await backend_db.update_shipment_info(
                            curr_sid.text, edit_customer.value, edit_product.value, 
                            int(edit_qty.value), edit_address.value, inferred_mode,
                            edit_pickup.value, edit_payment.value,
                            total_weight=total_weight_t, unit_price=up,
                            delivery_fee=df, freight_fee=freight_fee,
                        )
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

        with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12 gap-4'):
            # ── 顶部动作栏 ──
            with ui.row().classes('w-full justify-between items-center bg-white p-4 rounded-xl border shadow-sm'):
                with ui.row().classes('items-center gap-3'):
                    ui.button('⬅️ 返回台账', on_click=lambda: switch_to_tab('shipments'), color='gray').props('outline')
                    ui.separator().props('vertical').classes('h-8')
                    ui.label(f'📋 订单商品明细').classes('text-xl font-bold text-gray-800')
                    if ship_info:
                        ui.chip(f"{ship_info.get('customer_name', '')}", icon='person', color='blue-2').classes('text-sm')
                        ui.chip(f"{sid}", icon='tag', color='gray-2').classes('text-sm text-gray-500')

                with ui.row().classes('gap-2'):
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

            # ── 下方：动态列宽表 ──
            with ui.card().classes('modern-card w-full p-6'):
                if not detail_rows:
                    with ui.column().classes('w-full items-center py-12'):
                        ui.icon('inbox', size='4rem', color='grey-4')
                        ui.label('该发货单暂无商品明细记录').classes('text-gray-400 text-lg mt-4')
                        ui.label('通过 Excel 导入创建的发货单才会有完整的商品明细行').classes('text-gray-300 text-sm')
                else:
                    # 动态列生成：从返回的字典 key 自动创建表格列定义
                    # 排除内部元数据字段
                    skip_keys = {'_raw', 'raw_data', 'name', 'qty'}
                    all_keys = list(dict.fromkeys(
                        k for row in detail_rows for k in row.keys() if k not in skip_keys
                    ))
                    dynamic_cols = [
                        {'name': k, 'label': k, 'field': k, 'align': 'left' if i == 0 else 'center', 'sortable': True}
                        for i, k in enumerate(all_keys)
                    ]
                    # 清洗行数据：确保所有值都是可序列化的基础类型
                    clean_rows = []
                    for row in detail_rows:
                        clean = {}
                        for k in all_keys:
                            v = row.get(k, '')
                            clean[k] = str(v) if v is not None else ''
                        clean_rows.append(clean)

                    ui.label(f'共 {len(clean_rows)} 条商品记录').classes('text-sm text-gray-400 mb-2')
                    ui.table(
                        columns=dynamic_cols, rows=clean_rows, row_key=all_keys[0]
                    ).classes('w-full').props('dense flat bordered')

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

            driver_prefix_input = ui.input('司机端访问前缀', value=(current_driver_base_url or default_driver_base_url)).props('outlined').classes('w-full mb-3')
            logistics_options_input = ui.input('物流选项（逗号分隔）', value=current_logistics_options or default_logistics_options).props('outlined').classes('w-full mb-3')

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
