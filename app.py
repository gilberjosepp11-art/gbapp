from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
import requests
from bs4 import BeautifulSoup
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = 'gilberburger_2026_secreto' 

def get_db_connection():
    conn = sqlite3.connect('negocio.db')
    conn.row_factory = sqlite3.Row
    return conn

def obtener_tasa_bcv_directo():
    try:
        url = "https://www.bcv.org.ve/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'lxml')
            dolar_div = soup.find('div', id='dolar')
            if dolar_div:
                precio_texto = dolar_div.find('strong').text.strip()
                precio = float(precio_texto.replace(',', '.'))
                return precio
    except Exception as e:
        return None
    return None

@app.route('/sincronizar_tasa')
def sincronizar_tasa():
    tasa_nueva = obtener_tasa_bcv_directo()
    if tasa_nueva:
        conn = get_db_connection()
        conn.execute('UPDATE configuracion SET tasa_dolar = ? WHERE id = 1', (tasa_nueva,))
        conn.commit()
        conn.close()
        flash(f"✅ Tasa Oficial BCV actualizada con éxito: Bs. {tasa_nueva}", "success")
    else:
        flash("❌ Error de conexión con el BCV. Por favor, fija la tasa manualmente hoy.", "danger")
    return redirect(request.referrer or url_for('dashboard'))

@app.context_processor
def inject_tasa():
    conn = get_db_connection()
    fila = conn.execute('SELECT tasa_dolar FROM configuracion WHERE id = 1').fetchone()
    conn.close()
    tasa = fila['tasa_dolar'] if fila else 1.0
    return dict(tasa_dolar=tasa)

@app.route('/actualizar_tasa', methods=['POST'])
def actualizar_tasa():
    nueva_tasa = float(request.form['tasa_dolar'])
    conn = get_db_connection()
    conn.execute('UPDATE configuracion SET tasa_dolar = ? WHERE id = 1', (nueva_tasa,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/')
def inicio():
    return redirect(url_for('dashboard'))

# --- MÓDULO DE DASHBOARD ---
@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    hoy = conn.execute("SELECT COALESCE(SUM(total), 0) as total FROM facturas WHERE DATE(fecha) = DATE('now', 'localtime')").fetchone()['total']
    mes = conn.execute("SELECT COALESCE(SUM(total), 0) as total FROM facturas WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now', 'localtime')").fetchone()['total']
    gastos_hoy = conn.execute("SELECT COALESCE(SUM(monto), 0) as total FROM gastos WHERE DATE(fecha) = DATE('now', 'localtime')").fetchone()['total']
    gastos_mes = conn.execute("SELECT COALESCE(SUM(monto), 0) as total FROM gastos WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now', 'localtime')").fetchone()['total']
    
    ganancia_hoy = hoy - gastos_hoy
    ganancia_mes = mes - gastos_mes
    por_cobrar = conn.execute("SELECT COALESCE(SUM(total), 0) as deuda FROM facturas WHERE estado = 'Pendiente'").fetchone()['deuda']
    top_productos = conn.execute('''
        SELECT p.nombre, SUM(d.cantidad) as cantidad_vendida
        FROM detalles_factura d JOIN productos p ON d.producto_id = p.id
        GROUP BY p.id ORDER BY cantidad_vendida DESC LIMIT 5
    ''').fetchall()
    conn.close()
    return render_template('dashboard.html', hoy=hoy, mes=mes, gastos_hoy=gastos_hoy, gastos_mes=gastos_mes, 
                           ganancia_hoy=ganancia_hoy, ganancia_mes=ganancia_mes, por_cobrar=por_cobrar, top_productos=top_productos)

# --- RESPALDO DB ---
@app.route('/exportar_db')
def exportar_db():
    try:
        return send_file('negocio.db', as_attachment=True, download_name='gbapp_respaldo.db')
    except Exception as e:
        flash(f"❌ Error al exportar la base de datos: {e}", "danger")
        return redirect(url_for('dashboard'))

@app.route('/importar_db', methods=['POST'])
def importar_db():
    if 'archivo_db' not in request.files:
        flash("❌ No se seleccionó ningún archivo.", "danger")
        return redirect(url_for('dashboard'))
    archivo = request.files['archivo_db']
    if archivo.filename == '':
        flash("❌ El archivo no es válido.", "danger")
        return redirect(url_for('dashboard'))
    if archivo:
        try:
            archivo.save('negocio.db')
            flash("✅ ¡Base de datos restaurada con éxito en este equipo!", "success")
        except Exception as e:
            flash(f"❌ Error al importar la base de datos: {e}", "danger")
    return redirect(url_for('dashboard'))


# --- MÓDULO DE INVENTARIO Y COMPRAS MÚLTIPLES ---
@app.route('/insumos')
def insumos():
    conn = get_db_connection()
    lista_insumos = conn.execute("SELECT * FROM insumos ORDER BY nombre").fetchall()
    conn.close()
    carrito_compra = session.get('carrito_compra', [])
    total_carrito_compra = sum(item['subtotal'] for item in carrito_compra)
    return render_template('insumos.html', insumos=lista_insumos, carrito_compra=carrito_compra, total_carrito_compra=total_carrito_compra)

@app.route('/agregar_insumo', methods=['POST'])
def agregar_insumo():
    conn = get_db_connection()
    conn.execute('INSERT INTO insumos (nombre, unidad_medida, cantidad) VALUES (?, ?, ?)', 
                 (request.form['nombre'], request.form['unidad'], float(request.form['cantidad'])))
    conn.commit()
    conn.close()
    return redirect(url_for('insumos'))

@app.route('/agregar_carrito_compra', methods=['POST'])
def agregar_carrito_compra():
    insumo_id = int(request.form['insumo_id'])
    cantidad = float(request.form['cantidad_comprada'])
    costo_unitario = float(request.form['costo_unitario'])
    subtotal = cantidad * costo_unitario
    
    conn = get_db_connection()
    ins = conn.execute('SELECT nombre, unidad_medida FROM insumos WHERE id = ?', (insumo_id,)).fetchone()
    conn.close()
    
    if 'carrito_compra' not in session: session['carrito_compra'] = []
    session['carrito_compra'].append({
        'insumo_id': insumo_id, 'nombre': ins['nombre'], 'unidad': ins['unidad_medida'],
        'cantidad': cantidad, 'costo_unitario': costo_unitario, 'subtotal': subtotal
    })
    session.modified = True
    return redirect(url_for('insumos'))

@app.route('/eliminar_carrito_compra/<int:index>')
def eliminar_carrito_compra(index):
    carrito = session.get('carrito_compra', [])
    if 0 <= index < len(carrito):
        carrito.pop(index)
        session.modified = True
    return redirect(url_for('insumos'))

@app.route('/procesar_compra_multiple', methods=['POST'])
def procesar_compra_multiple():
    carrito = session.get('carrito_compra', [])
    if not carrito: return redirect(url_for('insumos'))
        
    proveedor = request.form.get('proveedor', 'Proveedor General')
    gasto_total = sum(item['subtotal'] for item in carrito)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    resumen_items = []
    for item in carrito:
        cursor.execute('UPDATE insumos SET cantidad = cantidad + ?, costo_unitario = ? WHERE id = ?', 
                       (item['cantidad'], item['costo_unitario'], item['insumo_id']))
        resumen_items.append(f"{item['cantidad']} {item['unidad']} {item['nombre']}")
        
    detalle_texto = f"Compra a {proveedor}: " + ", ".join(resumen_items)
    cursor.execute('INSERT INTO gastos (descripcion, monto) VALUES (?, ?)', (detalle_texto, gasto_total))
    conn.commit()
    conn.close()
    
    session.pop('carrito_compra', None)
    flash(f"✅ ¡Compra múltiple registrada con éxito! Total gastado: ${gasto_total:.2f}", "success")
    return redirect(url_for('insumos'))

@app.route('/eliminar_insumo/<int:id>')
def eliminar_insumo(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM insumos WHERE id = ?', (id,))
    conn.execute('DELETE FROM recetas WHERE insumo_id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('insumos'))


# --- MÓDULO DE PRODUCTOS (CATÁLOGO Y EDICIÓN) ---
@app.route('/productos')
def productos():
    conn = get_db_connection()
    query = '''
        SELECT p.id, p.nombre, p.precio_venta, 
               COALESCE(SUM(r.cantidad_usada * i.costo_unitario), 0) AS costo_real
        FROM productos p
        LEFT JOIN recetas r ON p.id = r.producto_id
        LEFT JOIN insumos i ON r.insumo_id = i.id
        GROUP BY p.id
    '''
    productos_db = conn.execute(query).fetchall()
    conn.close()
    
    productos_calculados = []
    for p in productos_db:
        item = dict(p)
        costo = item['costo_real']
        precio = item['precio_venta']
        ganancia = precio - costo
        margen = (ganancia / precio * 100) if precio > 0 else 0
        item['ganancia'] = ganancia
        item['margen'] = margen
        productos_calculados.append(item)
    return render_template('productos.html', productos=productos_calculados)

@app.route('/agregar_producto', methods=['POST'])
def agregar_producto():
    conn = get_db_connection()
    conn.execute('INSERT INTO productos (nombre, precio_venta) VALUES (?, ?)', (request.form['nombre'], float(request.form['precio'])))
    conn.commit()
    conn.close()
    return redirect(url_for('productos'))

@app.route('/eliminar_producto/<int:id>')
def eliminar_producto(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM productos WHERE id = ?', (id,))
    conn.execute('DELETE FROM recetas WHERE producto_id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('productos'))

@app.route('/editar_producto/<int:id>', methods=('GET', 'POST'))
def editar_producto(id):
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute('UPDATE productos SET nombre = ?, precio_venta = ? WHERE id = ?', 
                     (request.form['nombre'], float(request.form['precio']), id))
        conn.commit()
        conn.close()
        flash("✅ Producto actualizado con éxito.", "success")
        return redirect(url_for('productos'))
    producto = conn.execute('SELECT * FROM productos WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('editar_producto.html', producto=producto)


# --- MÓDULO DE CLIENTES Y EDICIÓN ---
@app.route('/clientes')
def clientes():
    conn = get_db_connection()
    lista_clientes = conn.execute('SELECT * FROM clientes ORDER BY nombre').fetchall()
    conn.close()
    return render_template('clientes.html', clientes=lista_clientes)

@app.route('/agregar_cliente', methods=['POST'])
def agregar_cliente():
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO clientes (cedula, nombre) VALUES (?, ?)', (request.form['cedula'], request.form['nombre']))
        conn.commit()
        flash("✅ Cliente registrado con éxito.", "success")
    except: 
        flash("❌ Error: La cédula ya está registrada.", "danger")
    conn.close()
    return redirect(url_for('clientes'))

@app.route('/editar_cliente/<int:id>', methods=('GET', 'POST'))
def editar_cliente(id):
    conn = get_db_connection()
    if request.method == 'POST':
        try:
            conn.execute('UPDATE clientes SET cedula = ?, nombre = ? WHERE id = ?', 
                         (request.form['cedula'], request.form['nombre'], id))
            conn.commit()
            conn.close()
            flash("✅ Cliente actualizado con éxito.", "success")
            return redirect(url_for('clientes'))
        except Exception as e:
            flash("❌ Error: Posible cédula duplicada.", "danger")
    cliente = conn.execute('SELECT * FROM clientes WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('editar_cliente.html', cliente=cliente)


# --- MÓDULO DE RECETAS ---
@app.route('/receta/<int:producto_id>')
def gestionar_receta(producto_id):
    conn = get_db_connection()
    producto = conn.execute('SELECT * FROM productos WHERE id = ?', (producto_id,)).fetchone()
    receta = conn.execute('''
        SELECT r.id, i.nombre, i.unidad_medida, r.cantidad_usada 
        FROM recetas r JOIN insumos i ON r.insumo_id = i.id 
        WHERE r.producto_id = ?
    ''', (producto_id,)).fetchall()
    insumos_disponibles = conn.execute('SELECT * FROM insumos ORDER BY nombre').fetchall()
    conn.close()
    return render_template('receta.html', producto=producto, receta=receta, insumos=insumos_disponibles)

@app.route('/agregar_a_receta', methods=['POST'])
def agregar_a_receta():
    conn = get_db_connection()
    conn.execute('INSERT INTO recetas (producto_id, insumo_id, cantidad_usada) VALUES (?, ?, ?)', 
                 (int(request.form['producto_id']), int(request.form['insumo_id']), float(request.form['cantidad_usada'])))
    conn.commit()
    conn.close()
    return redirect(url_for('gestionar_receta', producto_id=int(request.form['producto_id'])))

@app.route('/eliminar_de_receta/<int:receta_id>/<int:producto_id>')
def eliminar_de_receta(receta_id, producto_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM recetas WHERE id = ?', (receta_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('gestionar_receta', producto_id=producto_id))


# --- GASTOS ---
@app.route('/gastos')
def gastos():
    conn = get_db_connection()
    lista_gastos = conn.execute("SELECT * FROM gastos ORDER BY fecha DESC").fetchall()
    conn.close()
    return render_template('gastos.html', gastos=lista_gastos)

@app.route('/agregar_gasto', methods=['POST'])
def agregar_gasto():
    conn = get_db_connection()
    conn.execute('INSERT INTO gastos (descripcion, monto) VALUES (?, ?)', (request.form['descripcion'], float(request.form['monto'])))
    conn.commit()
    conn.close()
    return redirect(url_for('gastos'))

@app.route('/eliminar_gasto/<int:id>')
def eliminar_gasto(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM gastos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('gastos'))


# --- PUNTO DE VENTA Y VENTAS ---
@app.route('/ventas')
def registrar_venta():
    conn = get_db_connection()
    productos = conn.execute('SELECT * FROM productos').fetchall()
    clientes = conn.execute('SELECT * FROM clientes ORDER BY nombre').fetchall()
    conn.close()
    carrito = session.get('carrito', [])
    total_carrito = sum(item['subtotal'] for item in carrito)
    return render_template('registrar_venta.html', productos=productos, clientes=clientes, carrito=carrito, total_carrito=total_carrito)

@app.route('/agregar_carrito', methods=['POST'])
def agregar_carrito():
    producto_id = int(request.form['producto_id'])
    cantidad = int(request.form['cantidad'])
    conn = get_db_connection()
    producto = conn.execute('SELECT * FROM productos WHERE id = ?', (producto_id,)).fetchone()
    conn.close()
    
    if 'carrito' not in session: session['carrito'] = []
    carrito = session['carrito']
    
    encontrado = False
    for item in carrito:
        if item['producto_id'] == producto_id:
            item['cantidad'] += cantidad
            item['subtotal'] = item['cantidad'] * item['precio']
            encontrado = True; break
            
    if not encontrado:
        carrito.append({'producto_id': producto['id'], 'nombre': producto['nombre'], 'precio': producto['precio_venta'], 'cantidad': cantidad, 'subtotal': producto['precio_venta'] * cantidad})
        
    session.modified = True
    return redirect(url_for('registrar_venta'))

@app.route('/eliminar_carrito/<int:index>')
def eliminar_carrito(index):
    carrito = session.get('carrito', [])
    if 0 <= index < len(carrito):
        carrito.pop(index)
        session.modified = True
    return redirect(url_for('registrar_venta'))

@app.route('/procesar_venta', methods=['POST'])
def procesar_venta():
    carrito = session.get('carrito', [])
    if not carrito: return redirect(url_for('registrar_venta'))
        
    tipo_venta = request.form['tipo_venta']
    cliente_id = int(request.form['cliente_id'])
    metodo_pago = request.form['metodo_pago'] if tipo_venta == 'Contado' else 'Crédito'
    estado = 'Pendiente' if tipo_venta == 'Credito' else 'Pagado'
    total = sum(item['subtotal'] for item in carrito)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO facturas (cliente_id, tipo_venta, estado, total, metodo_pago) VALUES (?, ?, ?, ?, ?)', 
                   (cliente_id, tipo_venta, estado, total, metodo_pago))
    factura_id = cursor.lastrowid
    
    for item in carrito:
        cursor.execute('INSERT INTO detalles_factura (factura_id, producto_id, cantidad, precio_unitario) VALUES (?, ?, ?, ?)', 
                       (factura_id, item['producto_id'], item['cantidad'], item['precio']))
        
        receta = cursor.execute('SELECT insumo_id, cantidad_usada FROM recetas WHERE producto_id = ?', (item['producto_id'],)).fetchall()
        for r in receta:
            cantidad_a_descontar = r['cantidad_usada'] * item['cantidad']
            cursor.execute('UPDATE insumos SET cantidad = cantidad - ? WHERE id = ?', (cantidad_a_descontar, r['insumo_id']))
            
    conn.commit()
    conn.close()
    session.pop('carrito', None)
    return redirect(url_for('historial_ventas'))

@app.route('/historial_ventas')
def historial_ventas():
    conn = get_db_connection()
    fecha_filtro = request.args.get('fecha', '')
    estado_filtro = request.args.get('estado', 'Todos')
    cliente_filtro = request.args.get('cliente_id', '')
    query = '''
        SELECT f.id, f.fecha, c.nombre as cliente_nombre, c.cedula as cliente_cedula, f.tipo_venta, f.estado, f.total, f.metodo_pago,
               GROUP_CONCAT(d.cantidad || 'x ' || COALESCE(p.nombre, '(Eliminado)'), ', ') as detalles
        FROM facturas f JOIN clientes c ON f.cliente_id = c.id JOIN detalles_factura d ON f.id = d.factura_id LEFT JOIN productos p ON d.producto_id = p.id
        WHERE 1=1
    '''
    params = []
    if fecha_filtro: query += ' AND DATE(f.fecha) = ?'; params.append(fecha_filtro)
    if estado_filtro != 'Todos': query += ' AND f.estado = ?'; params.append(estado_filtro)
    if cliente_filtro: query += ' AND f.cliente_id = ?'; params.append(cliente_filtro)
    query += ' GROUP BY f.id ORDER BY f.fecha DESC'
    
    facturas = conn.execute(query, params).fetchall()
    clientes = conn.execute('SELECT * FROM clientes ORDER BY nombre').fetchall()
    conn.close()
    return render_template('historial_ventas.html', facturas=facturas, clientes=clientes, fecha_filtro=fecha_filtro, estado_filtro=estado_filtro, cliente_filtro=cliente_filtro)

@app.route('/saldar_deuda/<int:id_factura>', methods=['POST'])
def saldar_deuda(id_factura):
    metodo_pago = request.form['metodo_pago']
    conn = get_db_connection()
    conn.execute('UPDATE facturas SET estado = "Pagado", metodo_pago = ? WHERE id = ?', (metodo_pago, id_factura))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('historial_ventas'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)