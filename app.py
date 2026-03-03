import base64
import io
import socket
import datetime
from pathlib import Path
from typing import Optional

import qrcode
from nicegui import app, ui

import backend_db
from init_db import init_db

# 启动时自动初始化数据库
init_db()

# ════════════════════════════════════════════════
#  全局工具集与样式注入
# ════════════════════════════════════════════════

def get_local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
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
#  SPA 页面组件：订单管理
# ════════════════════════════════════════════════

async def orders_content():
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 gap-6 mb-12'):
        # ── 页面顶部行 ──
        with ui.row().classes('w-full justify-between items-center'):
            ui.label('订单管理').classes('text-2xl font-bold tracking-tight text-gray-800')
            
            # 弹窗内的新建订单表单
            dlg_new_order = ui.dialog()
            with dlg_new_order, ui.card().classes('min-w-[480px] p-6'):
                with ui.row().classes('w-full justify-between items-center mb-4'):
                    ui.label('📝 新建客户订单').classes('text-lg font-bold')
                    ui.button(icon='close', on_click=dlg_new_order.close).props('flat round dense')
                
                customer_input = ui.input('客户名称*').classes('w-full mb-2')
                product_input = ui.input('货物品类*').classes('w-full mb-2')
                qty_input = ui.number('数量(件)*', value=1, min=1, format='%.0f').classes('w-full mb-2')
                address_input = ui.input('收货详细地址*').classes('w-full mb-2')
                
                # 新增：生单时选择分流模式
                ui.separator().classes('my-4')
                ui.label('发货模式选择*').classes('text-xs font-bold text-gray-400 mb-1')
                mode_choice = ui.radio(['整车', '零单'], value='整车').props('inline')
                ui.label('提示：生单后将自动在“发货调度”中生成待处理记录').classes('text-[10px] text-blue-500 mb-6')
                
                async def submit_order():
                    if not customer_input.value or not product_input.value or not address_input.value:
                        ui.notify('请完整填写必填项（带*）', type='warning')
                        return
                    
                    # 1. 创建订单
                    o_id = f"ORDER-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                    await backend_db.create_order(
                        o_id, customer_input.value, product_input.value,
                        int(qty_input.value), address_input.value
                    )
                    
                    # 2. 核心补丁：联动创建发货单（自动分流派发）
                    await backend_db.create_shipment(o_id, mode_choice.value)
                    
                    ui.notify(f'订单创建成功，已同步开启【{mode_choice.value}】派发流程', type='positive')
                    
                    # 清空并关闭
                    customer_input.value = ''
                    product_input.value = ''
                    qty_input.value = 1
                    address_input.value = ''
                    dlg_new_order.close()
                    order_list_refreshable.refresh()

                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('取消', on_click=dlg_new_order.close).props('outline text-gray-600 border-gray-300')
                    ui.button('确认并立即生单', on_click=submit_order, color='primary')
            
            ui.button('新建订单', icon='add', on_click=dlg_new_order.open).classes('bg-primary text-white font-bold')
            
        # ── 筛选工具栏 ──
        with ui.card().classes('modern-card w-full p-4 border-l-4 border-l-blue-400'):
            with ui.row().classes('w-full items-end gap-4'):
                filter_status = ui.select(
                    {'全部': '全部', '待发货': '待发货', '已派发': '已派发'}, 
                    value='全部', 
                    label='订单状态'
                ).classes('w-40')
                filter_start_date = ui.input('开始日期(YYYY-MM-DD)').props('type=date').classes('w-48')
                filter_end_date = ui.input('结束日期(YYYY-MM-DD)').props('type=date').classes('w-48')
                filter_keyword = ui.input('货物名称(关键词)').classes('flex-grow')
                
                def apply_filters():
                    order_list_refreshable.refresh()
                    
                def reset_filters():
                    filter_status.value = '全部'
                    filter_start_date.value = ''
                    filter_end_date.value = ''
                    filter_keyword.value = ''
                    order_list_refreshable.refresh()

                ui.button('搜索', on_click=apply_filters, color='primary')
                ui.button('重置', on_click=reset_filters, color='grey').props('outline')

        # ── 历史订单列表 ──
        with ui.card().classes('modern-card w-full p-6'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('📋 订单列表').classes('text-lg font-bold')
                ui.button(icon='refresh', on_click=lambda: order_list_refreshable.refresh()).props('flat round color=primary tooltip="刷新"')
            
            @ui.refreshable
            async def order_list_refreshable():
                orders = await backend_db.fetch_all_orders()
                filtered_orders = []
                for order in orders:
                    if filter_status.value != '全部' and order['status'] != filter_status.value:
                        continue
                    if filter_keyword.value and filter_keyword.value.lower() not in order['product_name'].lower():
                        continue
                    order_date = order['created_at'][:10]
                    if filter_start_date.value and order_date < filter_start_date.value:
                        continue
                    if filter_end_date.value and order_date > filter_end_date.value:
                        continue
                    filtered_orders.append(order)

                filtered_orders.sort(key=lambda x: x['created_at'], reverse=True)
                filtered_orders.sort(key=lambda x: x['status'] != '待发货')

                if not filtered_orders:
                    with ui.column().classes('w-full items-center py-12'):
                        ui.icon('inbox', size='4xl', color='grey-4').classes('mb-4')
                        ui.label('暂无符合条件的订单数据').classes('text-gray-400')
                    return
                
                cols = [
                    {'name': 'order_id', 'label': '订单号', 'field': 'order_id', 'align': 'left'},
                    {'name': 'customer_name', 'label': '客户名', 'field': 'customer_name', 'align': 'left'},
                    {'name': 'product_name', 'label': '物品', 'field': 'product_name', 'align': 'left'},
                    {'name': 'quantity', 'label': '数量', 'field': 'quantity', 'align': 'right'},
                    {'name': 'status', 'label': '状态', 'field': 'status', 'align': 'center'},
                    {'name': 'created_at', 'label': '创建时间', 'field': 'created_at', 'align': 'left'},
                    {'name': 'actions', 'label': '操作', 'align': 'center'},
                ]
                with ui.table(columns=cols, rows=filtered_orders, row_key='order_id').classes('w-full') as table:
                    table.add_slot('body-cell-status', '''
                        <q-td :props="props">
                            <q-chip :color="props.row.status === \'待发货\' ? \'orange\' : \'green\'" text-color="white" dense size="sm">
                                {{ props.row.status }}
                            </q-chip>
                        </q-td>
                    ''')
                    table.add_slot('body-cell-actions', '''
                        <q-td :props="props">
                            <q-btn v-if="props.row.status === \'待发货\'" 
                                outline dense color="primary" label="补录派发" @click="$parent.$emit('dispatch', props.row)" />
                            <q-btn v-else flat dense color="grey" label="已派入调度" @click="$parent.$emit('goto_shipment', props.row)" />
                        </q-td>
                    ''')
                    table.on('dispatch', lambda e: switch_to_shipments(e.args["order_id"]))
                    table.on('goto_shipment', lambda e: switch_to_shipments(None))
            await order_list_refreshable()

# ════════════════════════════════════════════════
#  SPA 页面组件：发货调度
# ════════════════════════════════════════════════

async def shipments_content(selected_order_id: Optional[str] = None):
    @ui.refreshable
    async def main_shipments_refreshable(oid: Optional[str] = selected_order_id):
        with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12 gap-6'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('发货单调度与管理').classes('text-2xl font-bold tracking-tight text-gray-800')

            # ── 派发面板 ──
            if oid:
                order = await backend_db.get_order_by_id(oid)
                if order:
                    with ui.card().classes('modern-card w-full p-6 border-l-4 border-l-blue-500 bg-blue-50/20'):
                        ui.label(f'正在为临时派发单 [{oid}] 分配发货模式').classes('text-blue-800 font-bold mb-2')
                        ui.label(f"客户: {order['customer_name']} | 物品: {order['product_name']} | 数量: {order['quantity']}").classes('text-gray-600')
                        
                        with ui.row().classes('items-center gap-6 mt-4'):
                            ship_type = ui.radio(['整车', '零单'], value='整车').props('inline')
                            async def do_dispatch():
                                await backend_db.create_shipment(oid, ship_type.value)
                                ui.notify(f'已生成【{ship_type.value}】发货单', type='positive')
                                main_shipments_refreshable.refresh(None) 
                                list_refreshable.refresh()
                            ui.button('🚀 确认分流', on_click=do_dispatch, color='primary')
            
            # ── 调度总台账 ──
            with ui.card().classes('modern-card w-full p-6'):
                with ui.row().classes('w-full justify-between items-center mb-4'):
                    ui.label('📦 调度总台账 (整车/零单)').classes('text-lg font-bold')
                    with ui.row().classes('items-center gap-2'):
                        ui.label('司机端访问前缀:').classes('text-sm text-gray-500')
                        base_url_input = ui.input(value=f"http://{get_local_ip()}:8501").props('dense outlined').classes('w-64')
                        
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
                        
                dlg_qr = ui.dialog()
                with dlg_qr, ui.card().classes('p-6 items-center'):
                    ui.label('司机发车扫码').classes('font-bold text-lg mb-4 text-primary')
                    qr_img = ui.image().classes('w-60 h-60 bg-white p-2 rounded shadow')
                    ui.button('关闭', on_click=dlg_qr.close).classes('mt-4 w-full').props('outline')

                table = None
                
                @ui.refreshable
                async def list_refreshable():
                    shipments = await backend_db.fetch_all_shipments()
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
                                    :color="props.row.status === \'已发货\' ? \'green\' : (props.row.status === \'未订车\' ? \'red\' : \'orange\')" 
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
                                <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'未订车\'" 
                                    dense outline color="primary" label="改为已订车" @click="$parent.$emit('mark_booked', props.row)" class="mr-1" />
                                <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'已订车\'" 
                                    dense color="orange" icon="qr_code" label="发车码" @click="$parent.$emit('show_qr', props.row)" class="mr-1" />
                                <q-btn v-if="props.row.ship_type === \'零单\' && props.row.status === \'待填写\'" 
                                    dense color="orange" label="补录快递单" @click="$parent.$emit('fill_lingdan', props.row)" class="mr-1" />
                                <q-btn dense flat color="grey-7" icon="print" @click="$parent.$emit('print', props.row)" tooltip="打印发货单"/>
                            </q-td>
                        ''')
                        
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
                            import urllib.parse
                            sid = e.args.get('shipment_id', '')
                            base = urllib.parse.quote(base_url_input.value.strip('/'), safe='')
                            ui.open(f"/print?id={sid}&base={base}", new_tab=True)
                        
                        table.on('mark_booked', handle_mark_booked)
                        table.on('show_qr', handle_show_qr)
                        table.on('fill_lingdan', handle_fill_lingdan)
                        table.on('print', handle_print)

                await list_refreshable()
    
    await main_shipments_refreshable()
    return main_shipments_refreshable

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
    active_tab = 'orders'
    shipments_ref = None 

    def switch_to_tab(tab_name: str, order_id: Optional[str] = None):
        nonlocal active_tab
        active_tab = tab_name
        panels.value = tab_name
        for k, btn in sidebar_btns.items():
            if k == tab_name:
                btn.classes('sidebar-item-active', remove='text-gray-400 hover:bg-gray-700 hover:text-white')
            else:
                btn.classes('text-gray-400 hover:bg-gray-700 hover:text-white', remove='sidebar-item-active')
        if tab_name == 'shipments' and shipments_ref:
            shipments_ref.refresh(order_id)

    # 声明全局函数供 Table 事件调用
    global switch_to_shipments
    switch_to_shipments = lambda oid: switch_to_tab('shipments', oid)

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
                ('orders',    '📝', '订单管理'),
                ('shipments', '📦', '发货调度'),
                ('dashboard', '📊', '数据看板'),
                ('finance',   '💰', '费用核算'),
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
    with ui.tab_panels(value='orders').classes('w-full bg-transparent h-full') as panels:
        with ui.tab_panel('orders').classes('p-0'):
            await orders_content()
        with ui.tab_panel('shipments').classes('p-0'):
            shipments_ref = await shipments_content()
        with ui.tab_panel('dashboard').classes('p-0'):
            await dashboard_content()
        with ui.tab_panel('finance').classes('p-0'):
            await finance_content()
    
    switch_to_tab('orders')

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
