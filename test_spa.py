from nicegui import ui

@ui.page('/')
def index():
    ui.add_head_html('<style>body { margin: 0; }</style>')
    
    # Global state for active tab
    active_tab = 'orders'

    # The container that controls what's shown
    panels = ui.tab_panels().classes('w-full h-full')
    
    def change_tab(new_tab):
        panels.value = new_tab

    with ui.left_drawer().classes('bg-gray-900 text-white w-60 min-h-screen'):
        ui.button('Orders', on_click=lambda: change_tab('orders'))
        ui.button('Shipments', on_click=lambda: change_tab('shipments'))

    with panels:
        with ui.tab_panel('orders'):
            ui.label('Orders Page').classes('text-2xl')
            ui.button('Dispatch order 123', on_click=lambda: change_tab('shipments'))
        
        with ui.tab_panel('shipments'):
            ui.label('Shipments Page').classes('text-2xl')


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8503)
