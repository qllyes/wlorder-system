import base64
import io
import socket
import datetime
from pathlib import Path

import qrcode
from nicegui import app, ui

import backend_db
from init_db import init_db

# 启动时自动初始化数据库（若不存在则建表，幂等）
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
    """根据字符串生成二维码头像的 Base64 编码"""
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"

def inject_modern_css():
    """注入现代 SaaS 风格 CSS：类似 Vercel/Linear 的专业感设计。"""
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
        .header-nav {
            background: #FFFFFF;
            border-bottom: 1px solid var(--border-color);
        }
        .nav-link {
            color: #4B5563;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            transition: all 0.2s;
            font-weight: 500;
        }
        .nav-link:hover {
            background-color: #F3F4F6;
            color: var(--primary-blue);
        }
        /* 表格斑马纹与操作吸顶 */
        .q-table tbody tr:nth-child(even) {
            background-color: #FAFAFA;
        }
        .q-table tbody tr:hover {
            background-color: #F3F4F6 !important;
        }
        </style>
    ''')

def create_header(title: str):
    """PC 端统一 Header"""
    inject_modern_css()
    with ui.header().classes('header-nav items-center justify-between px-8 py-3 w-full'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('local_shipping', size='md', color='primary')
            ui.label(title).classes('text-xl font-bold tracking-tight text-gray-800')
        with ui.row().classes('gap-2'):
            ui.link('📝 订单管理', '/').classes('nav-link')
            ui.link('📦 发货调度', '/shipments').classes('nav-link')
            ui.link('📊 数据看板', '/dashboard').classes('nav-link')
            ui.link('💰 费用核算', '/finance').classes('nav-link')

# ════════════════════════════════════════════════
#  1. 订单管理页 (/)
# ════════════════════════════════════════════════

@ui.page('/')
async def index_page():
    ui.page_title('订单管理 - 极速物流系统')
    create_header('极速物流调度管理台')
    
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 gap-6 mb-12'):
        # ── 录入订单卡片 ──
        with ui.card().classes('modern-card w-full p-6'):
            ui.label('✨ 录入新客户订单').classes('text-lg font-bold mb-4')
            with ui.row().classes('w-full gap-4 items-end'):
                customer_input = ui.input('客户名称*').classes('flex-grow')
                product_input = ui.input('货物品类*').classes('flex-grow')
                qty_input = ui.number('数量(件)*', value=1, min=1, format='%.0f').classes('w-32')
                address_input = ui.input('收货详细地址*').classes('flex-grow-2 w-1/3')
                
                async def submit_order():
                    if not customer_input.value or not product_input.value or not address_input.value:
                        ui.notify('请完整填写必填项（带*）', type='warning')
                        return
                    o_id = f"ORDER-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                    await backend_db.create_order(
                        o_id, customer_input.value, product_input.value,
                        int(qty_input.value), address_input.value
                    )
                    ui.notify('订单创建成功', type='positive')
                    # 清空表单
                    customer_input.value = ''
                    product_input.value = ''
                    qty_input.value = 1
                    address_input.value = ''
                    order_list_refreshable.refresh()
                    
                ui.button('保存并录入', on_click=submit_order, icon='save').classes('h-12 bg-primary text-white px-8')
        
        # ── 历史订单列表 ──
        with ui.card().classes('modern-card w-full p-6'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('📋 历史订单列表').classes('text-lg font-bold')
                ui.button(icon='refresh', on_click=lambda: order_list_refreshable.refresh()).props('flat round color=primary tooltip="刷新"')
            
            @ui.refreshable
            async def order_list_refreshable():
                orders = await backend_db.fetch_all_orders()
                if not orders:
                    with ui.column().classes('w-full items-center py-12'):
                        ui.icon('inbox', size='4xl', color='grey-4').classes('mb-4')
                        ui.label('暂无订单数据，请在上方录入').classes('text-gray-400')
                    return
                
                cols = [
                    {'name': 'order_id', 'label': '订单号', 'field': 'order_id', 'align': 'left'},
                    {'name': 'customer_name', 'label': '客户名', 'field': 'customer_name', 'align': 'left'},
                    {'name': 'product_name', 'label': '物品', 'field': 'product_name', 'align': 'left'},
                    {'name': 'quantity', 'label': '数量', 'field': 'quantity', 'align': 'right'},
                    {'name': 'status', 'label': '状态', 'field': 'status', 'align': 'center'},
                    {'name': 'created_at', 'label': '创建时间', 'field': 'created_at', 'align': 'left'},
                    {'name': 'actions', 'label': '调度操作', 'align': 'center'},
                ]
                with ui.table(columns=cols, rows=orders, row_key='order_id').classes('w-full') as table:
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
                                outline dense color="primary" label="分配派发" @click="$parent.$emit('dispatch', props.row)" />
                            <q-btn v-else flat dense color="grey" label="已派发" disable />
                        </q-td>
                    ''')
                    table.on('dispatch', lambda e: ui.navigate.to(f'/shipments?order_id={e.args["order_id"]}'))
            await order_list_refreshable()


# ════════════════════════════════════════════════
#  2. 发货调度页 (/shipments)
# ════════════════════════════════════════════════

@ui.page('/shipments')
async def shipments_page(order_id: str = ''):
    ui.page_title('发货调度 - 极速物流系统')
    create_header('发货单调度与管理')
    
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12 gap-6'):
        # ── 派发卡片（带参数时） ──
        if order_id:
            order = await backend_db.get_order_by_id(order_id)
            if order:
                with ui.card().classes('modern-card w-full p-6 border-l-4 border-l-blue-500 bg-blue-50/20'):
                    ui.label(f'正在为订单 [{order_id}] 派发发货单').classes('text-blue-800 font-bold mb-2')
                    ui.label(f"客户: {order['customer_name']} | 物品: {order['product_name']} | 数量: {order['quantity']}").classes('text-gray-600')
                    
                    with ui.row().classes('items-center gap-6 mt-4'):
                        ship_type = ui.radio(['整车', '零单'], value='整车').props('inline')
                        async def do_dispatch():
                            await backend_db.create_shipment(order_id, ship_type.value)
                            ui.notify(f'已生成【{ship_type.value}】发货单', type='positive')
                            ui.navigate.to('/shipments')
                        ui.button('🚀 确认生成', on_click=do_dispatch, color='primary')
        
        # ── 调度总台账 ──
        with ui.card().classes('modern-card w-full p-6'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('📦 调度总台账 (整车/零单)').classes('text-lg font-bold')
                with ui.row().classes('items-center gap-2'):
                    ui.label('司机端访问前缀:').classes('text-sm text-gray-500')
                    base_url_input = ui.input(value=f"http://{get_local_ip()}:8501").props('dense outlined').classes('w-64')
                    
                    # 合单按钮
                    async def do_batch():
                        # 从表格中获取选中的行
                        selected = [row['shipment_id'] for row in table.selected if row['ship_type'] == '零单' and not row.get('batch_id')]
                        if not selected:
                            ui.notify('请勾选尚未合单的【零单】进行合单', type='warning')
                            return
                        bid = await backend_db.batch_lingdan(selected)
                        ui.notify(f'成功生成合单批次: {bid}', type='positive')
                        list_refreshable.refresh()
                    
                    ui.button('🔗 零单合单', on_click=do_batch, color='secondary', icon='link').props('outline dense')
                    ui.button(icon='refresh', on_click=lambda: list_refreshable.refresh()).props('flat round color=primary tooltip="刷新"')
            
            # --- 隐藏的变量和弹窗 ---
            curr_sid = ui.label().classes('hidden') # 充当状态变量传递 ID
            
            # 1. 补录零单弹窗
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
                    
            # 2. QR码弹窗
            dlg_qr = ui.dialog()
            with dlg_qr, ui.card().classes('p-6 items-center'):
                ui.label('司机发车扫码').classes('font-bold text-lg mb-4 text-primary')
                qr_img = ui.html()
                ui.button('关闭', on_click=dlg_qr.close).classes('mt-4 w-full').props('outline')

            # --- 表格 ---
            # 初始化 table 变量，以便 nonlocal 能找到
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
                                :color="props.row.status === \'已发货\' ? \'green\' : (props.row.status === \'未订车\' ? \'red\' : (props.row.status === \'已订车\' ? \'blue\' : \'orange\'))" 
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
                            <!-- 未订车 → 变更为已订车 -->
                            <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'未订车\'" 
                                dense outline color="primary" label="改为已订车" @click="$parent.$emit('mark_booked', props.row)" class="mr-1" />
                            
                            <!-- 已订车 → 呼出二维码 -->
                            <q-btn v-if="props.row.ship_type === \'整车\' && props.row.status === \'已订车\'" 
                                dense color="blue" icon="qr_code" label="发车码" @click="$parent.$emit('show_qr', props.row)" class="mr-1" />
                            
                            <!-- 待填写 → 补录 -->
                            <q-btn v-if="props.row.ship_type === \'零单\' && props.row.status === \'待填写\'" 
                                dense color="orange" label="补录快递单" @click="$parent.$emit('fill_lingdan', props.row)" class="mr-1" />
                                
                            <!-- 打印按钮 (全状态支持) -->
                            <q-btn dense flat color="grey-7" icon="print" @click="$parent.$emit('print', props.row)" tooltip="打印发货单"/>
                        </q-td>
                    ''')
                    
                    async def handle_mark_booked(e):
                        await backend_db.update_zhengche_to_yidingche(e.args['shipment_id'])
                        ui.notify('操作成功，已变更为已订车', type='info')
                        list_refreshable.refresh()
                    
                    def handle_show_qr(e):
                        sid, tk = e.args['shipment_id'], e.args['driver_token']
                        url = f"{base_url_input.value.strip('/')}/driver_confirm?id={sid}&token={tk}"
                        qr_img.content = f'<div class="p-2 bg-white rounded shadow"><img src="{generate_qr_base64(url)}" width="240" height="240" /></div>'
                        dlg_qr.open()
                        
                    def handle_fill_lingdan(e):
                        curr_sid.set_text(e.args['shipment_id'])
                        comp_in.value, trk_in.value = '', ''
                        dlg_lingdan.open()
                        
                    def handle_print(e):
                        # 打开新标签页打印
                        ui.open(f"/print?id={e.args['shipment_id']}", new_tab=True)
                    
                    table.on('mark_booked', handle_mark_booked)
                    table.on('show_qr', handle_show_qr)
                    table.on('fill_lingdan', handle_fill_lingdan)
                    table.on('print', handle_print)

            await list_refreshable()


# ════════════════════════════════════════════════
#  3. 司机确认页 (/driver_confirm) (Mobile First)
# ════════════════════════════════════════════════

@ui.page('/driver_confirm')
async def driver_confirm_page(id: str = '', token: str = ''):
    """手机端即扫即用页面，无 Header。"""
    ui.page_title('司机发车确认')
    # 注入基础移动端优化 css
    ui.add_head_html('<style>body { background-color: #F8FAFC; }</style>')
    
    with ui.column().classes('w-full max-w-lg mx-auto p-4 items-center min-h-screen'):
        ui.label('🚛 极速物流发车单').classes('text-2xl font-black text-blue-900 mt-6 mb-8')
        
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
            ui.label('🧑‍✈️ 填报车辆资质').classes('font-bold text-lg mb-4')
            d_name = ui.input('真实姓名').props('outlined dense').classes('w-full mb-3')
            d_id = ui.input('身份证号').props('outlined dense').classes('w-full mb-3')
            d_phone = ui.input('手机号').props('outlined dense type=tel').classes('w-full mb-3')
            ui.separator().classes('mb-3')
            t_plate = ui.input('车牌号 (例:湘A88888)').props('outlined dense').classes('w-full mb-3')
            t_type = ui.select(['4.2米轻卡','6.8米中卡','9.6米重卡','13.5米挂车','17.5米平板','其他'], 
                               label='车型').props('outlined dense').classes('w-full mb-6')
            
            async def submit_info():
                if not all([d_name.value, d_id.value, d_phone.value, t_plate.value, t_type.value]):
                    ui.notify('请完整填写所有信息', type='negative')
                    return
                await backend_db.confirm_zhengche_driver(
                    id, d_name.value, d_id.value, d_phone.value, t_plate.value, t_type.value
                )
                ui.notify('确认发车成功！', type='positive')
                ui.navigate.to(f'/driver_confirm?id={id}&token={token}')
                
            ui.button('确认装货完毕，立即发车', on_click=submit_info).classes('w-full h-14 bg-blue-600 text-white font-bold text-lg rounded-lg shadow-lg')


# ════════════════════════════════════════════════
#  4. 打印预览页 (/print) - 纯 HTML 渲染
# ════════════════════════════════════════════════

@ui.page('/print')
async def print_page(id: str = ''):
    ship = await backend_db.get_shipment_by_id(id)
    if not ship:
        ui.label("发货单不存在")
        return
        
    # 构建纯净的打印样式，隐藏保密字段
    ui.add_head_html('''
        <style>
            body { background: white; color: black; font-family: sans-serif; padding: 2rem; }
            .print-table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
            .print-table th, .print-table td { border: 1px solid #000; padding: 10px; text-align: left; }
            .print-header { text-align: center; margin-bottom: 2rem; }
            @media print {
                .no-print { display: none !important; }
            }
        </style>
    ''')
    
    with ui.column().classes('w-full max-w-4xl mx-auto'):
        ui.button('🖨️ 点击开始打印', on_click=lambda: ui.run_javascript('window.print()')).classes('no-print mb-4')
        with ui.column().classes('w-full border p-8'):
            ui.label('出 库 发 货 单').classes('print-header text-3xl font-bold w-full')
            
            with ui.row().classes('w-full justify-between mb-4'):
                ui.label(f"发货单号：{ship['shipment_id']}")
                ui.label(f"开单时间：{ship['created_at']}")
                
            html_table = f'''
            <table class="print-table">
                <tr><th>关联订单</th><td>{ship['order_id']}</td><th>发货类型</th><td>{ship['ship_type']}</td></tr>
                <tr><th>收货客户</th><td colspan="3">{ship['customer_name']}</td></tr>
                <tr><th>送货地址</th><td colspan="3">{ship['delivery_address']}</td></tr>
                <tr><th>货物名称</th><td>{ship['product_name']}</td><th>数量</th><td>{ship['quantity']} 件</td></tr>
            '''
            if ship['ship_type'] == '整车':
                html_table += f'''
                    <tr><th colspan="4" style="text-align:center;background:#eee;">承运司机信息</th></tr>
                    <tr><th>司机姓名</th><td>{ship.get('driver_name','')}</td><th>联系电话</th><td>{ship.get('driver_phone','')}</td></tr>
                    <tr><th>车牌号码</th><td>{ship.get('truck_plate','')}</td><th>车型</th><td>{ship.get('truck_type','')}</td></tr>
                '''
            else:
                html_table += f'''
                    <tr><th colspan="4" style="text-align:center;background:#eee;">外包物流信息</th></tr>
                    <tr><th>物流公司</th><td>{ship.get('third_party_company','')}</td><th>运单号</th><td>{ship.get('third_party_tracking','')}</td></tr>
                '''
            html_table += '</table>'
            ui.html(html_table).classes('w-full')
            
            ui.label('注：此单据作为出门发车凭证。').classes('mt-8 text-sm text-gray-600')
            ui.row().classes('w-full justify-between mt-12').append(ui.html('<span>经办人签字：____________</span><span>司机/承运商签字：____________</span>'))


# ════════════════════════════════════════════════
#  5. 数据看板 (/dashboard)
# ════════════════════════════════════════════════

@ui.page('/dashboard')
async def dashboard_page():
    ui.page_title('数据看板 - 极速物流系统')
    create_header('数据资产与作业总看板')
    
    stats = await backend_db.get_dashboard_stats()
    
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12'):
        # ── 核心 KPI 卡片区 ──
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
        
        # ── 下半区布局 ──
        with ui.row().classes('w-full gap-6'):
            # 左侧：状态分布
            with ui.card().classes('modern-card p-6 w-1/3'):
                ui.label('当前大盘状态分布').classes('text-lg font-bold mb-4')
                for item in stats['status_dist']:
                    with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-100'):
                        ui.label(item['status']).classes('text-gray-600')
                        ui.label(str(item['cnt'])).classes('font-bold text-lg')
            
            # 右侧：今日作业明细
            with ui.card().classes('modern-card p-6 flex-grow'):
                ui.label('今日发货单作业流水').classes('text-lg font-bold mb-4')
                cols = [
                    {'name': 'shipment_id', 'label': '发货号', 'field': 'shipment_id'},
                    {'name': 'ship_type', 'label': '类型', 'field': 'ship_type'},
                    {'name': 'status', 'label': '状态', 'field': 'status'},
                    {'name': 'customer', 'label': '客户', 'field': 'customer_name'},
                    {'name': 'time', 'label': '变动时间', 'field': 'created_at'},
                ]
                ui.table(columns=cols, rows=stats['today_shipments']).classes('w-full').props('dense flat')


# ════════════════════════════════════════════════
#  6. 费用核算 (/finance)
# ════════════════════════════════════════════════

@ui.page('/finance')
async def finance_page():
    ui.page_title('费用核算 - 极速物流系统')
    create_header('财务核算与利差对账单')
    
    with ui.column().classes('w-full max-w-7xl mx-auto mt-6 px-4 mb-12'):
        # ── 财务总计 ──
        summary = await backend_db.get_finance_summary()
        with ui.card().classes('modern-card w-full p-6 mb-6 bg-gray-50'):
            ui.label('历史累计核心财务数据（仅针对已发货完结单）').classes('font-bold text-gray-600 mb-4')
            with ui.row().classes('w-full gap-12'):
                ui.html(f'<div><div class="text-sm text-gray-500">累计对外物流费 (收入)</div><div class="text-2xl font-bold text-blue-600">¥ {summary.get("total_fee", 0):.2f}</div></div>')
                ui.html(f'<div><div class="text-sm text-gray-500">累计实际成本 (支出)</div><div class="text-2xl font-bold text-red-500">¥ {summary.get("total_cost", 0):.2f}</div></div>')
                ui.html(f'<div><div class="text-sm text-gray-500">累计轧差净利 (利润)</div><div class="text-3xl font-black text-green-600">¥ {summary.get("total_profit", 0):.2f}</div></div>')

        # ── 核算列表 ──
        with ui.card().classes('modern-card w-full p-6'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('📝 费用登记录入').classes('text-lg font-bold')
                ui.button(icon='refresh', on_click=lambda: fin_table.refresh()).props('flat round color=primary tooltip="刷新"')
            
            # 弹窗
            curr_sid = ui.label().classes('hidden')
            dlg_fee = ui.dialog()
            with dlg_fee, ui.card().classes('p-6 min-w-[350px]'):
                ui.label('核算运单费用').classes('font-bold text-lg mb-4')
                ui.label('注意：实际成本对外部完全保密').classes('text-xs text-red-500 mb-4 bg-red-50 p-2')
                out_fee = ui.number('向客户收取的物流费 (¥)', format='%.2f').classes('w-full mb-2')
                in_cost = ui.number('实际发车内部成本 (¥)', format='%.2f').classes('w-full mb-4')
                async def save_fee():
                    f_val = float(out_fee.value or 0)
                    c_val = float(in_cost.value or 0)
                    await backend_db.update_shipment_fee(curr_sid.text, f_val, c_val)
                    ui.notify(f'登记核算成功，计入利润 ¥{f_val-c_val:.2f}', type='positive')
                    dlg_fee.close()
                    fin_table.refresh()
                    # 这里也可以刷新 summary，为求简便此处通过用户手动刷页面来更新顶部 summary
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('取消', on_click=dlg_fee.close).props('flat')
                    ui.button('保存账单', on_click=save_fee, color='green')
            
            @ui.refreshable
            async def fin_table():
                rows = await backend_db.fetch_shipped_shipments()
                cols = [
                    {'name': 'shipment_id', 'label': '发货号', 'field': 'shipment_id', 'align': 'left'},
                    {'name': 'ship_type', 'label': '承运', 'field': 'ship_type', 'align': 'center'},
                    {'name': 'batch', 'label': '合单批次', 'field': 'batch_id', 'align': 'left'},
                    {'name': 'logistics_fee', 'label': '对外物流费(¥)', 'field': 'logistics_fee', 'align': 'right'},
                    {'name': 'actual_cost', 'label': '实际成本(¥)', 'field': 'actual_cost', 'align': 'right'},
                    {'name': 'profit', 'label': '利润(¥)', 'field': 'profit', 'align': 'right'},
                    {'name': 'shipped_at', 'label': '发车时间', 'field': 'shipped_at', 'align': 'left'},
                    {'name': 'actions', 'label': '费用操作', 'align': 'center'},
                ]
                with ui.table(columns=cols, rows=rows, row_key='shipment_id').classes('w-full') as ft:
                    ft.add_slot('body-cell-logistics_fee', '<q-td :props="props" class="text-blue-600 font-bold">{{ props.row.logistics_fee }}</q-td>')
                    ft.add_slot('body-cell-actual_cost', '<q-td :props="props" class="text-red-500 font-bold">{{ props.row.actual_cost }}</q-td>')
                    ft.add_slot('body-cell-profit', '<q-td :props="props" class="text-green-600 font-black text-lg">{{ props.row.profit }}</q-td>')
                    ft.add_slot('body-cell-actions', '''
                        <q-td :props="props">
                            <q-btn outline dense color="secondary" label="登记账单" @click="$parent.$emit('edit_fee', props.row)" />
                        </q-td>
                    ''')
                    def handle_edit_fee(e):
                        curr_sid.set_text(e.args['shipment_id'])
                        out_fee.value = e.args['logistics_fee']
                        in_cost.value = e.args['actual_cost']
                        dlg_fee.open()
                    ft.on('edit_fee', handle_edit_fee)
            
            await fin_table()

# 启动服务器
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='极速物流调度系统', port=8501, host='0.0.0.0', language='zh-CN', favicon='🚚')
