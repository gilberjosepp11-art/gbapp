import sqlite3

def init_db():
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    # 1. Tabla de Productos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            precio_venta REAL NOT NULL,
            costo_produccion REAL
        )
    ''')
    
    # 2. Tabla de Clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO clientes (id, cedula, nombre) VALUES (1, "00000000", "Cliente Ocasional")')
    
    # 3. Tabla de Facturas (Añadido metodo_pago)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            tipo_venta TEXT CHECK(tipo_venta IN ('Contado', 'Credito')),
            estado TEXT DEFAULT 'Pagado',
            total REAL NOT NULL,
            metodo_pago TEXT DEFAULT 'Efectivo $',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        )
    ''')
    
    # 4. Tabla de Detalles de Factura
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detalles_factura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factura_id INTEGER,
            producto_id INTEGER,
            cantidad INTEGER,
            precio_unitario REAL,
            FOREIGN KEY (factura_id) REFERENCES facturas (id),
            FOREIGN KEY (producto_id) REFERENCES productos (id)
        )
    ''')
    
    # 5. Tabla de Configuración (Tasa)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            id INTEGER PRIMARY KEY,
            tasa_dolar REAL NOT NULL
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO configuracion (id, tasa_dolar) VALUES (1, 50.00)')
    
    # 6. Tabla de Gastos (Egresos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 7. Tabla de Insumos (Materia Prima)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS insumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            unidad_medida TEXT NOT NULL,
            cantidad REAL NOT NULL,
            costo_unitario REAL DEFAULT 0
        )
    ''')

    # 8. Tabla de Recetas (Escandallos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            insumo_id INTEGER NOT NULL,
            cantidad_usada REAL NOT NULL,
            FOREIGN KEY (producto_id) REFERENCES productos (id),
            FOREIGN KEY (insumo_id) REFERENCES insumos (id)
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("✅ Base de datos actualizada con éxito para Métodos de Pago.")