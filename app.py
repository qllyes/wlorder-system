import base64
import io
import socket
import datetime
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
        # 使用真实的外部连接探测自身IP，而不是解析hostname以免带入虚拟网卡IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

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
    """注入现代 SaaS 风格 CSS"""
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
        /* 侧边栏活动项样式 */
        .sidebar-item-active {
            background-color: #2563EB !important;
            color: white !important;
        }
        </style>
    ''')

# ════════════════════════════════════════════════
#  SPA 页面组件：发货调度工作台
# ════════════════════════════════════════════════

async def shipments_content():
    @ui.refreshable
    async def main_shipments_refreshable():
        with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12 gap-6'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('发货单调度与管理').classes('text-2xl font-bold tracking-tight text-gray-800')
                
                # ── 融合后的新建发货单入口 ──
                dlg_new_shipment = ui.dialog()
                with dlg_new_shipment, ui.card().classes('min-w-[540px] p-6'):
                    with ui.row().classes('w-full justify-between items-center mb-4'):
                        ui.label('📝 新建发货单').classes('text-lg font-bold')
                        ui.button(icon='close', on_click=dlg_new_shipment.close).props('flat round dense')
                    
                    # Excel 导入区
                    imported_products: list[dict] = []
                    with ui.row().classes('w-full items-center mb-3 p-3 bg-blue-50 rounded-lg border border-blue-100'):
                        ui.icon('upload_file', color='blue-5').classes('text-2xl mr-2')
                        ui.label('从客户订单Excel导入').classes('text-sm font-bold text-blue-800 flex-1')
                        
                        async def on_excel_upload(e):
                            """解析上传的订单 Excel，自动填充表单字段"""
                            try:
                                import tempfile, os, asyncio
                                # 兼容不同 NiceGUI 版本的上传事件属性名
                                filename = getattr(e, 'name', getattr(e, 'filename', 'order.xlsx'))
                                suffix = Path(filename).suffix or '.xlsx'
                                content_io = getattr(e, 'content', None) or getattr(e, 'file', None)
                                if content_io is None:
                                    ui.notify('无法读取上传文件', type='negative')
                                    return
                                # 兼容同步 BytesIO 和异步 UploadFile 两种情层
                                raw = content_io.read()
                                if asyncio.iscoroutine(raw):
                                    raw = await raw
                                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                    tmp.write(raw)
                                    tmp_path = tmp.name
                                
                                data = waybill_generator.parse_order_excel(tmp_path)
                                os.unlink(tmp_path)
                                
                                # 填充收货人信息
                                customer_input.value = data['receiver_name']
                                address_input.value = data['receiver_address']
                                
                                # 填充商品信息（取前3个商品名称合并显示）
                                prods = data.get('products', [])
                                if prods:
                                    product_input.value = '、'.join([p['name'] for p in prods[:3]])
                                    qty_input.value = sum(p['qty'] for p in prods)
                                
                                # 保存到外层变量供生成托运单使用
                                imported_products.clear()
                                imported_products.extend(prods)
                                
                                ui.notify(f'订单导入成功！识别到 {len(prods)} 个商品，请检查信息', type='positive')
                            except Exception as ex:
                                ui.notify(f'导入失败：{ex}', type='negative')
                        
                        ui.upload(on_upload=on_excel_upload, auto_upload=True, label='选择 Excel').props('accept=".xlsx,.xls" dense flat color=blue-5')
                    
                    customer_input = ui.input('客户名称*').classes('w-full mb-2')
                    product_input = ui.input('货物品类*').classes('w-full mb-2')
                    qty_input = ui.number('数量(件)*', value=1, min=1, format='%.0f').classes('w-full mb-2')
                    address_input = ui.input('收货详细地址*').classes('w-full mb-2')
                    
                    ui.separator().classes('my-4')
                    ui.label('发货模式选择*').classes('text-xs font-bold text-gray-400 mb-1')
                    mode_choice = ui.radio(['整车', '零单'], value='整车').props('inline')
                    
                    async def submit_shipment():
                        if not customer_input.value or not product_input.value or not address_input.value:
                            ui.notify('请完整填写必填项（带*）', type='warning')
                            return
                        
                        await backend_db.create_shipment(
                            customer_input.value, 
                            product_input.value,
                            int(qty_input.value), 
                            address_input.value,
                            mode_choice.value
                        )
                        ui.notify(f'发货单创建成功，已开启【{mode_choice.value}】派发流程', type='positive')
                        
                        # 清空并关闭
                        customer_input.value = ''
                        product_input.value = ''
                        qty_input.value = 1
                        address_input.value = ''
                        dlg_new_shipment.close()
                        list_refreshable.refresh()

                    with ui.row().classes('w-full justify-end gap-2 mt-4'):
                        ui.button('取消', on_click=dlg_new_shipment.close).props('outline text-gray-600 border-gray-300')
                        ui.button('确认并立即生单', on_click=submit_shipment, color='primary')
                
                ui.button('新建发货单', icon='add', on_click=dlg_new_shipment.open).classes('bg-primary text-white font-bold')

            # 废除原有的派发面板，该功能已被顶部新建功能取代
            
            # ── 调度总台账 ──
            with ui.card().classes('modern-card w-full p-6'):
                with ui.row().classes('w-full justify-between items-center mb-4'):
                    ui.label('📦 调度总台账 (整车/零单)').classes('text-lg font-bold')
                    with ui.row().classes('items-center gap-2'):
                        ui.label('司机端访问前缀:').classes('text-sm text-gray-500')
                        base_url_input = ui.input(value=f"http://{get_local_ip()}:8501").props('dense outlined').classes('w-64')
                        ui.icon('info', color='grey-5').tooltip('如扫码打不开，请检查手机是否与电脑在同一WiFi，或手动将前缀改为电脑正确的局域网IP')
                        
                        async def do_batch():
                            selected = [row['shipment_id'] for row in table.selected if row['ship_type'] == '零单' and not row.get('batch_id')]
                            if not selected:
                                ui.notify('请勾选尚未合单的【零单】进行合单', type='warning')
                                return
                            bid = await backend_db.batch_lingdan(selected)
                            ui.notify(f'成功生成合单批次: {bid}', type='positive')
                            list_refreshable.refresh()
                        
                        ui.button('🔗 零单合单', on_click=do_batch, color='secondary', icon='link').props('outline dense')
                        ui.button(icon='refresh', on_click=lambda: list_refreshable.refresh()).props('flat round color=primary tooltip="刷新"')
                
                curr_sid = ui.label().classes('hidden')
                
                # ── 弹窗：编辑发货单 ──
                dlg_edit = ui.dialog()
                with dlg_edit, ui.card().classes('min-w-[480px] p-6'):
                    with ui.row().classes('w-full justify-between items-center mb-4'):
                        ui.label('✏️ 修改发货单').classes('text-lg font-bold text-blue-800')
                        ui.button(icon='close', on_click=dlg_edit.close).props('flat round dense')
                    
                    edit_customer = ui.input('客户名称*').classes('w-full mb-2')
                    edit_product = ui.input('货物品类*').classes('w-full mb-2')
                    edit_qty = ui.number('数量(件)*', min=1, format='%.0f').classes('w-full mb-2')
                    edit_address = ui.input('收货详细地址*').classes('w-full mb-2')
                    
                    ui.separator().classes('my-4')
                    ui.label('修改发货模式').classes('text-xs font-bold text-gray-400 mb-1')
                    edit_mode = ui.radio(['整车', '零单'], value='整车').props('inline')
                    ui.label('提示：若更改发货模式，系统将会自动清空绑定的司机并退回至【未订车】状态').classes('text-[10px] text-orange-500 mb-4')
                    
                    async def save_edit():
                        if not edit_customer.value or not edit_product.value or not edit_address.value:
                            ui.notify('请完整填写必填项', type='warning')
                            return
                        await backend_db.update_shipment_info(
                            curr_sid.text, edit_customer.value, edit_product.value, 
                            int(edit_qty.value), edit_address.value, edit_mode.value
                        )
                        ui.notify('发货单已修改', type='positive')
                        dlg_edit.close()
                        list_refreshable.refresh()
                        
                    with ui.row().classes('w-full justify-end gap-2 mt-4'):
                        ui.button('取消', on_click=dlg_edit.close).props('outline text-gray-600 border-gray-300')
                        ui.button('保存修改', on_click=save_edit, color='primary')
                
                # ── 弹窗：补录零单快递信息 ──
                dlg_lingdan = ui.dialog()
                with dlg_lingdan, ui.card().classes('min-w-[400px] p-6'):
                    ui.label('补录第三方物流信息').classes('font-bold text-lg mb-4')
                    comp_in = ui.input('第三方物流公司*').classes('w-full mb-2')
                    trk_in = ui.input('运单号*').classes('w-full mb-4')
                    async def save_lingdan():
                        if not comp_in.value or not trk_in.value:
                            ui.notify('请完整填写', type='warning')
                            return
                        await backend_db.update_lingdan_info(curr_sid.text, comp_in.value, trk_in.value)
                        ui.notify('零单发货完成', type='positive')
                        dlg_lingdan.close()
                        list_refreshable.refresh()
                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('取消', on_click=dlg_lingdan.close).props('flat')
                        ui.button('保存并发货', on_click=save_lingdan, color='primary')
                        
                # ── 弹窗：司机二维码 ──
                dlg_qr = ui.dialog()
                with dlg_qr, ui.card().classes('p-6 items-center'):
                    ui.label('司机发车扫码').classes('font-bold text-lg mb-4 text-primary')
                    qr_img = ui.image().classes('w-60 h-60 bg-white p-2 rounded shadow')
                    ui.button('关闭', on_click=dlg_qr.close).classes('mt-4 w-full').props('outline')

                # ── 弹窗：作废确认 ──
                dlg_cancel = ui.dialog()
                with dlg_cancel, ui.card().classes('p-6 items-center'):
                    ui.label('⚠️ 确定要作废这笔发货单吗？').classes('text-lg font-bold text-red-600 mb-2')
                    ui.label('作废后将无法修改和恢复此单数据。').classes('text-sm text-gray-500 mb-6')
                    
                    async def confirm_cancel():
                        await backend_db.cancel_shipment(curr_sid.text)
                        ui.notify('此单据已作废，数据已归档', type='warning')
                        dlg_cancel.close()
                        list_refreshable.refresh()
                        
                    with ui.row().classes('w-full justify-center gap-4'):
                        ui.button('暂不作废', on_click=dlg_cancel.close).props('outline text-gray-600')
                        ui.button('确认作废', on_click=confirm_cancel, color='red')

                # ── 弹窗：撤销发货(回驳)确认 ──
                dlg_rollback = ui.dialog()
                with dlg_rollback, ui.card().classes('p-6 items-center'):
                    ui.label('🔄 确定要撤销这笔发货单吗？').classes('text-lg font-bold text-orange-600 mb-2')
                    ui.label('此操作将会清空所有已绑定的司机、车辆及第三方物流信息，并将其打回至【未订车】池。').classes('text-sm text-gray-500 mb-6 text-center')
                    
                    async def confirm_rollback():
                        await backend_db.rollback_to_unbooked(curr_sid.text)
                        ui.notify('单据已撤销发货并打回未订车状态，所有物流关联已清空', type='info')
                        dlg_rollback.close()
                        list_refreshable.refresh()
                        
                    with ui.row().classes('w-full justify-center gap-4'):
                        ui.button('暂不撤销', on_click=dlg_rollback.close).props('outline text-gray-600')
                        ui.button('确认撤销回【未订车】', on_click=confirm_rollback, color='orange')

                # ── 弹窗：生成托运单 ──
                wb_sid_label = ui.label().classes('hidden')     # 当前发货单ID
                wb_receiver  = ui.label().classes('hidden')     # 收货人
                wb_address   = ui.label().classes('hidden')     # 收货地址
                wb_weight_label  = ui.label('─')                # 总重量预算结果展示
                wb_freight_label = ui.label('─')                # 运费预算结果展示
                wb_ship_type  = None
                wb_freight    = None
                wb_delivery_fee = None
                wb_pickup     = None
                wb_payment    = None

                dlg_waybill = ui.dialog()
                with dlg_waybill, ui.card().classes('min-w-[520px] p-6'):
                    with ui.row().classes('w-full justify-between items-center mb-4'):
                        ui.label('📔 生成托运单').classes('text-lg font-bold text-gray-800')
                        ui.button(icon='close', on_click=dlg_waybill.close).props('flat round dense')
                    
                    # 运输类型
                    ui.label('运输类型').classes('text-xs font-bold text-gray-400 mb-1')
                    wb_ship_type = ui.select(['零单', '整车', '专车'], value='零单').classes('w-full mb-2')
                    
                    with ui.row().classes('w-full gap-2 mb-2'):
                        wb_freight    = ui.number('手动输入运费(元)', value=0, min=0).classes('flex-1')
                        wb_delivery_fee = ui.number('送货费(元)', value=0, min=0).classes('flex-1')
                    
                    with ui.row().classes('w-full gap-2 mb-4'):
                        wb_pickup  = ui.select(['送货上门', '自提'], value='送货上门', label='取货方式').classes('flex-1')
                        wb_payment = ui.select(['现付', '提付'], value='现付', label='付款方式').classes('flex-1')
                    
                    # 预算结果展示
                    with ui.card().classes('w-full bg-gray-50 p-3 mb-4'):
                        with ui.row().classes('w-full justify-between'):
                            ui.label('总重量：').classes('text-sm text-gray-600')
                            wb_weight_label = ui.label('—').classes('text-sm font-bold text-blue-700')
                        with ui.row().classes('w-full justify-between'):
                            ui.label('运费计算：').classes('text-sm text-gray-600')
                            wb_freight_label = ui.label('—').classes('text-sm font-bold text-green-700')
                    
                    async def preview_waybill():
                        """(按预算)根据当前单据信息计算重量和运费"""
                        try:
                            spec_rows = await backend_db.get_all_spec_weights()
                            sw = {r['spec']: r['weight_kg'] for r in spec_rows}
                            ship = await backend_db.get_shipment_by_id(curr_sid.text)
                            if not ship:
                                return
                            products = [{'name': ship.get('product_name',''), 'spec': '', 'qty': ship.get('quantity', 0)}]
                            total_qty, total_weight_t = waybill_generator.calc_total_weight(products, sw)
                            wb_weight_label.set_text(f'{total_weight_t} 吨')
                            
                            if wb_ship_type.value in ('零单', '拼车'):
                                calc = freight_calc.calc_freight(total_weight_t, wb_ship_type.value, 0, wb_delivery_fee.value)
                                wb_freight_label.set_text(f'{calc} 元 (需先输入内表单价)' if calc == 0 else f'{calc} 元')
                            else:
                                wb_freight_label.set_text(f'请手动输入运费')
                        except Exception as ex:
                            ui.notify(f'预算失败: {ex}', type='warning')
                    
                    async def download_waybill():
                        """(下载)以托运单模板生成填充后的 Excel"""
                        try:
                            spec_rows = await backend_db.get_all_spec_weights()
                            sw = {r['spec']: r['weight_kg'] for r in spec_rows}
                            ship = await backend_db.get_shipment_by_id(curr_sid.text)
                            if not ship:
                                ui.notify('未找到发货单信息', type='negative')
                                return
                            
                            products = [{'name': ship.get('product_name',''), 'spec': '', 'qty': ship.get('quantity', 0)}]
                            order_data = {
                                'order_no': ship.get('shipment_id', ''),
                                'receiver_name':    ship.get('customer_name', ''),
                                'receiver_phone':   '',
                                'receiver_address': ship.get('delivery_address', ''),
                                'products': products,
                            }
                            freight_val = float(wb_freight.value or 0)
                            excel_bytes = waybill_generator.generate_waybill_excel(
                                order_data, freight=freight_val,
                                pickup_method=wb_pickup.value,
                                payment_method=wb_payment.value,
                                spec_weights=sw,
                            )
                            filename = f"托运单_{ship.get('shipment_id','')}_{datetime.date.today()}.xlsx"
                            ui.download(excel_bytes, filename)
                            ui.notify('托运单已生成，即将下载', type='positive')
                        except Exception as ex:
                            ui.notify(f'托运单生成失败：{ex}', type='negative')
                    
                    with ui.row().classes('w-full justify-between gap-2 mt-2'):
                        ui.button('预算重量与运费', on_click=preview_waybill, color='blue').props('outline dense')
                        ui.space()
                        ui.button('取消', on_click=dlg_waybill.close).props('flat')
                        ui.button('生成并下载 Excel', on_click=download_waybill, color='green').props('dense')

                # ── 筛选栏组件 ──
                with ui.row().classes('w-full items-end gap-4 p-4 mb-4 bg-gray-50 rounded-lg border border-gray-100 shadow-sm'):
                    filter_status = ui.select(['全部', '未订车', '已订车', '已发货', '已作废'], value='全部', label='状态').classes('w-32')
                    filter_customer = ui.input('客户名称').classes('w-48')
                    filter_start = ui.input('开始时间(格式YYYY-MM-DD)').classes('w-48')
                    filter_end = ui.input('结束时间(格式YYYY-MM-DD)').classes('w-48')
                    
                    def do_search():
                        list_refreshable.refresh()
                        
                    def do_reset():
                        filter_status.value = '全部'
                        filter_customer.value = ''
                        filter_start.value = ''
                        filter_end.value = ''
                        list_refreshable.refresh()
                        
                    async def export_csv():
                        import csv, io
                        rows = await backend_db.fetch_all_shipments(
                            filter_status.value, filter_customer.value,
                            filter_start.value, filter_end.value
                        )
                        output = io.StringIO()
                        writer = csv.DictWriter(output, fieldnames=["shipment_id", "ship_type", "status", "customer_name", "product_name", "quantity", "delivery_address", "created_at"])
                        
                        # 写入中文表头映射方便理解
                        writer.writerow({
                            "shipment_id": "发货号", "ship_type": "模式", "status": "状态",
                            "customer_name": "客户名称", "product_name": "货物品类", "quantity": "数量",
                            "delivery_address": "收货地址", "created_at": "创建时间"
                        })
                        for row in rows:
                            # 过滤仅导出我们关心的字段，屏蔽源数据ID或token等脏数据
                            clean_row = {k: row.get(k, '') for k in writer.fieldnames}
                            writer.writerow(clean_row)
                            
                        csv_data = output.getvalue().encode('utf-8-sig') # 避免 Excel 打开乱码
                        ui.download(csv_data, f"骄阳物流总台账导出_{datetime.date.today().isoformat()}.csv")

                    ui.button('查询', on_click=do_search, color='primary', icon='search').props('dense')
                    ui.button('重置', on_click=do_reset, color='grey', icon='refresh').props('dense outline')
                    
                    ui.space()
                    ui.button('导出 Excel (CSV)', on_click=export_csv, color='green', icon='file_download').props('dense outline')

                table = None
                
                @ui.refreshable
                async def list_refreshable():
                    shipments = await backend_db.fetch_all_shipments(
                        filter_status.value, filter_customer.value,
                        filter_start.value, filter_end.value
                    )
                    cols = [
                        {'name': 'shipment_id', 'label': '发货号', 'field': 'shipment_id', 'align': 'left'},
                        {'name': 'order_id', 'label': '源订单号', 'field': 'order_id', 'align': 'left'},
                        {'name': 'ship_type', 'label': '类型', 'field': 'ship_type', 'align': 'center'},
                        {'name': 'status', 'label': '状态', 'field': 'status', 'align': 'center'},
                        {'name': 'customer', 'label': '客户', 'field': 'customer_name', 'align': 'left'},
                        {'name': 'batch', 'label': '合单批次', 'field': 'batch_id', 'align': 'left'},
                        {'name': 'actions', 'label': '操作', 'align': 'center'}
                    ]
                    with ui.table(columns=cols, rows=shipments, row_key='shipment_id', selection='multiple').classes('w-full') as global_table:
                        nonlocal table
                        table = global_table
                        
                        table.add_slot('body-cell-ship_type', '''
                            <q-td :props="props">
                                <q-badge :color="props.row.ship_type === \'整车\' ? \'purple\' : \'teal\'">{{ props.row.ship_type }}</q-badge>
                            </q-td>
                        ''')
                        table.add_slot('body-cell-status', '''
                            <q-td :props="props">
                                <q-chip 
                                    :color="props.row.status === \'已作废\' ? \'grey\' : (props.row.status === \'已发货\' ? \'green\' : (props.row.status === \'未订车\' ? \'red\' : \'orange\'))" 
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
                                        dense flat color="blue-7" icon="edit" @click="$parent.$emit('edit_shipment', props.row)" tooltip="修改" class="mr-1"/>
                                    <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'未订车\'" 
                                        dense outline color="primary" label="改为已订车" @click="$parent.$emit('mark_booked', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'已订车\'" 
                                        dense color="orange" icon="qr_code" label="发车码" @click="$parent.$emit('show_qr', props.row)" class="mr-1" />
                                    <q-btn v-if="props.row.ship_type === \'零单\' && props.row.status === \'未订车\'" 
                                        dense color="orange" label="补录快递单" @click="$parent.$emit('fill_lingdan', props.row)" class="mr-1" />
                                    <q-btn dense flat color="grey-7" icon="print" @click="$parent.$emit('print', props.row)" tooltip="打印发货单"/>
                                    <q-btn v-if="props.row.status === \'未订车\' || props.row.status === \'已订车\'" 
                                        dense flat color="red-5" icon="delete" @click="$parent.$emit('cancel_shipment', props.row)" tooltip="作废" class="ml-2"/>
                                    <q-btn v-if="props.row.status === \'已发货\'" 
                                        dense flat color="orange-9" icon="replay" @click="$parent.$emit('rollback_shipment', props.row)" tooltip="撤销并发回待分配" class="ml-2"/>
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
                            edit_mode.value = row['ship_type']
                            dlg_edit.open()
                            
                        def handle_cancel_shipment(e):
                            curr_sid.set_text(e.args['shipment_id'])
                            dlg_cancel.open()
                            
                        def handle_rollback_shipment(e):
                            curr_sid.set_text(e.args['shipment_id'])
                            dlg_rollback.open()
                        
                        async def handle_mark_booked(e):
                            await backend_db.update_zhengche_to_yidingche(e.args['shipment_id'])
                            ui.notify('操作成功，已变更为已订车', type='info')
                            list_refreshable.refresh()
                        
                        async def handle_show_qr(e):
                            sid = e.args.get('shipment_id', '')
                            tk = e.args.get('driver_token', '')
                            if not tk:
                                ui.notify('该发货单缺少发车 Token', type='negative')
                                return
                            try:
                                url = f"{base_url_input.value.strip('/')}/driver_confirm?id={sid}&token={tk}"
                                b64 = generate_qr_base64(url)
                                qr_img.set_source(b64) 
                            except Exception as ex:
                                ui.notify(f'二维码生成失败：{ex}', type='negative')
                            dlg_qr.open()
                            
                        def handle_fill_lingdan(e):
                            curr_sid.set_text(e.args['shipment_id'])
                            comp_in.value, trk_in.value = '', ''
                            dlg_lingdan.open()
                            
                        def handle_print(e):
                            """打印按钮 → 弹出生成托运单弹窗"""
                            row = e.args
                            curr_sid.set_text(row.get('shipment_id', ''))
                            # 预填收货人信息
                            wb_receiver.set_text(row.get('customer_name', ''))
                            wb_address.set_text(row.get('delivery_address', ''))
                            wb_freight.value = 0
                            wb_delivery_fee.value = 0
                            wb_ship_type.value = '零单'
                            wb_pickup.value = '送货上门'
                            wb_payment.value = '现付'
                            wb_weight_label.set_text('─')
                            wb_freight_label.set_text('─')
                            dlg_waybill.open()
                        
                        table.on('edit_shipment', handle_edit_shipment)
                        table.on('cancel_shipment', handle_cancel_shipment)
                        table.on('rollback_shipment', handle_rollback_shipment)
                        table.on('mark_booked', handle_mark_booked)
                        table.on('show_qr', handle_show_qr)
                        table.on('fill_lingdan', handle_fill_lingdan)
                        table.on('print', handle_print)

                await list_refreshable()
    
    await main_shipments_refreshable()

# ════════════════════════════════════════════════
#  SPA 页面组件：数据看板 & 费用核算 (维持原样)
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
            kpi_card('今日新增订单', stats['today_orders'], 'border-l-blue-500', 'add_shopping_cart')
            kpi_card('当前积压未发数', stats['pending_count'], 'border-l-orange-500', 'hourglass_empty')
            kpi_card('今日已发货/发车', stats['shipped_today'], 'border-l-green-500', 'local_shipping')
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
                ui.html(f'<div><div class="text-sm text-gray-500">累计收入</div><div class="text-2xl font-bold text-blue-600">¥ {summary.get("total_fee", 0):.2f}</div></div>')
                ui.html(f'<div><div class="text-sm text-gray-500">累计支出</div><div class="text-2xl font-bold text-red-500">¥ {summary.get("total_cost", 0):.2f}</div></div>')
                ui.html(f'<div><div class="text-sm text-gray-500">累计净利</div><div class="text-3xl font-black text-green-600">¥ {summary.get("total_profit", 0):.2f}</div></div>')
        with ui.card().classes('modern-card w-full p-6'):
            curr_sid = ui.label().classes('hidden')
            dlg_fee = ui.dialog()
            with dlg_fee, ui.card().classes('p-6 min-w-[350px]'):
                ui.label('核算运单费用').classes('font-bold text-lg mb-4')
                out_fee = ui.number('费用收入', format='%.2f').classes('w-full mb-2')
                in_cost = ui.number('成本支出', format='%.2f').classes('w-full mb-4')
                async def save_fee():
                    await backend_db.update_shipment_fee(curr_sid.text, float(out_fee.value or 0), float(in_cost.value or 0))
                    ui.notify('登记核算成功')
                    dlg_fee.close()
                    fin_table.refresh()
                ui.button('保存账单', on_click=save_fee, color='green').classes('w-full')
            @ui.refreshable
            async def fin_table():
                rows = await backend_db.fetch_shipped_shipments()
                cols = [{'name': 'shipment_id', 'label': '发货号', 'field': 'shipment_id'},{'name': 'profit', 'label': '利润', 'field': 'profit'},{'name': 'actions', 'label': '操作', 'align': 'center'}]
                with ui.table(columns=cols, rows=rows, row_key='shipment_id').classes('w-full') as ft:
                    ft.add_slot('body-cell-actions', '<q-td :props="props"><q-btn outline dense color="secondary" label="登记" @click="$parent.$emit(\'edit_fee\', props.row)" /></q-td>')
                    ft.on('edit_fee', lambda e: (curr_sid.set_text(e.args['shipment_id']), dlg_fee.open()))
            await fin_table()

# ════════════════════════════════════════════════
#  SPA 主入口 (/)
# ════════════════════════════════════════════════

@ui.page('/')
async def main_page():
    inject_modern_css()
    
    # 状态：用于侧边栏切换与刷新
    active_tab = 'shipments'

    def switch_to_tab(tab_name: str):
        nonlocal active_tab
        active_tab = tab_name
        panels.value = tab_name
        for k, btn in sidebar_btns.items():
            if k == tab_name:
                btn.classes('sidebar-item-active', remove='text-gray-400 hover:bg-gray-700 hover:text-white')
            else:
                btn.classes('text-gray-400 hover:bg-gray-700 hover:text-white', remove='sidebar-item-active')

    # 1. 顶部栏 (放置 Toggle 按钮)
    with ui.header().classes('bg-white text-gray-800 border-b border-gray-200 px-4 flex items-center justify-between'):
        with ui.row().classes('items-center gap-2'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat round color=primary')
            ui.label('骄阳物流调度后台').classes('font-bold text-lg hidden md:block')
        
        with ui.row().classes('items-center gap-4 text-sm'):
            ui.label(f"📅 {datetime.date.today()}").classes('text-gray-400')
            ui.icon('account_circle', size='sm').classes('text-gray-400')

    # 2. 侧边栏 (可折叠)
    with ui.left_drawer(fixed=True).classes('bg-gray-900 text-white w-30 min-h-screen flex flex-col p-0') as left_drawer:
        with ui.row().classes('items-center gap-3 p-6 border-b border-gray-700 w-full'):
            ui.icon('local_shipping', size='lg', color='blue-400')
            ui.label('骄阳物流').classes('text-lg font-bold text-white')

        with ui.column().classes('flex-grow p-3 gap-1 w-full'):
            sidebar_btns = {}
            MENU = [
                ('shipments', '📦', '发货调度'),
                ('dashboard', '📊', '数据看板'),
                ('finance',   '💰', '费用核算'),
                ('settings',  '⚙️', '系统设置'),
            ]
            for key, icon, label in MENU:
                with ui.row().classes('w-full items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-colors text-gray-400 hover:bg-gray-700 hover:text-white') as btn:
                    sidebar_btns[key] = btn
                    ui.label(icon).classes('text-lg')
                    ui.label(label).classes('font-medium')
                    btn.on('click', lambda k=key: switch_to_tab(k))
        
        with ui.row().classes('p-4 border-t border-gray-700 w-full'):
            ui.button('收起菜单', icon='chevron_left', on_click=left_drawer.toggle).props('flat dense size=sm').classes('text-gray-500 w-full')

    # 3. 内容面板
    with ui.tab_panels(value='shipments').classes('w-full bg-transparent h-full') as panels:
        with ui.tab_panel('shipments').classes('p-0'):
            await shipments_content()
        with ui.tab_panel('dashboard').classes('p-0'):
            await dashboard_content()
        with ui.tab_panel('finance').classes('p-0'):
            await finance_content()
        with ui.tab_panel('settings').classes('p-0'):
            await settings_content()
    
    switch_to_tab('shipments')


# ════════════════════════════════════════════════
#  SPA 页面组件：系统设置（规格单重管理）
# ════════════════════════════════════════════════

async def settings_content():
    with ui.column().classes('w-full max-w-4xl mx-auto mt-6 px-4 mb-12 gap-6'):
        ui.label('⚙️ 系统设置 — 规格单重管理').classes('text-2xl font-bold tracking-tight text-gray-800')
        
        with ui.card().classes('modern-card w-full p-6'):
            ui.label('📦 规格单重配置').classes('text-lg font-bold mb-4')
            ui.label('用于生成托运单时计算总重量。单位：kg/件。').classes('text-sm text-gray-500 mb-4')
            
            @ui.refreshable
            async def spec_table_refreshable():
                rows = await backend_db.get_all_spec_weights()
                cols = [
                    {'name': 'spec',      'label': '规格名称', 'field': 'spec',      'align': 'left'},
                    {'name': 'weight_kg', 'label': '单重(kg)', 'field': 'weight_kg', 'align': 'center'},
                    {'name': 'actions',   'label': '操作',                            'align': 'center'},
                ]
                with ui.table(columns=cols, rows=rows, row_key='spec').classes('w-full') as spec_tbl:
                    spec_tbl.add_slot('body-cell-actions', '''
                        <q-td :props="props">
                            <q-btn dense flat color="red-5" icon="delete" 
                                @click="$parent.$emit('del_spec', props.row)"/>
                        </q-td>
                    ''')
                    async def on_del(e):
                        await backend_db.delete_spec_weight(e.args['spec'])
                        ui.notify(f'已删除规格：{e.args["spec"]}', type='warning')
                        spec_table_refreshable.refresh()
                    spec_tbl.on('del_spec', on_del)
            
            await spec_table_refreshable()
            
            ui.separator().classes('my-4')
            ui.label('新增规格').classes('text-sm font-bold text-gray-600 mb-2')
            
            with ui.row().classes('w-full items-end gap-2'):
                new_spec = ui.input('规格名称（如 750ml*12）').classes('flex-1')
                new_weight = ui.number('单重（kg）', value=0.0, min=0).classes('w-36')
                
                async def add_spec():
                    if not new_spec.value:
                        ui.notify('请输入规格名称', type='warning')
                        return
                    await backend_db.save_spec_weight(new_spec.value, float(new_weight.value))
                    ui.notify(f'已保存规格 {new_spec.value} = {new_weight.value}kg', type='positive')
                    new_spec.value = ''
                    new_weight.value = 0.0
                    spec_table_refreshable.refresh()
                
                ui.button('➕ 新增', on_click=add_spec, color='primary').props('dense')

# 司机页 & 打印页 (由于是独立入口，保持不变)
@ui.page('/driver_confirm')
async def driver_confirm_page(id: str = '', token: str = ''):
    ship = await backend_db.get_shipment_by_id(id)
    if not ship or ship['driver_token'] != token:
        ui.label('鉴权失败').classes('text-red-500 m-12')
        return
    ui.label('司机确认发车面板').classes('text-2xl m-12')

@ui.page('/print')
async def print_page(id: str = '', base: str = ''):
    ui.label(f'打印发货单: {id}').classes('m-12')

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='骄阳物流调度系统', port=8501, host='0.0.0.0', language='zh-CN', favicon='🚚')
