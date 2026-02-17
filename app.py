from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime, date, timedelta
import os

app = Flask(__name__)
app.secret_key = 'taxi_userT64AuaHtBe7Y9wI4fgazlIAEmwAXXGCL'
# Para producción, desactiva el modo debug
app.config['DEBUG'] = False

DB_NAME = "taxi_finanzas.db"

# ============================================
# FUNCIONES DE BASE DE DATOS
# ============================================

def crear_tablas():
    """Crea las tablas necesarias"""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    # Tabla de registros (gastos y ganancias)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_personalizado TEXT UNIQUE NOT NULL,
            tipo TEXT NOT NULL,
            fecha_hora TIMESTAMP NOT NULL,
            categoria TEXT NOT NULL,
            cantidad REAL NOT NULL,
            descripcion TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conexion.commit()
    conexion.close()

def generar_id_personalizado(tipo):
    """Genera ID tipo GO-001 o GA-001"""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    prefijo = "GO" if tipo == "gasto" else "GA"
    
    # Buscar el último número
    cursor.execute('''
        SELECT id_personalizado FROM registros 
        WHERE id_personalizado LIKE ? 
        ORDER BY id_personalizado DESC LIMIT 1
    ''', (f'{prefijo}-%',))
    
    resultado = cursor.fetchone()
    conexion.close()
    
    if resultado:
        ultimo_numero = int(resultado[0].split('-')[1])
        nuevo_numero = ultimo_numero + 1
    else:
        nuevo_numero = 1
    
    return f"{prefijo}-{nuevo_numero:03d}"

def obtener_registros(fecha_inicio=None, fecha_fin=None):
    """Obtiene registros con filtro de fechas"""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    query = """
        SELECT 
            id, 
            id_personalizado, 
            tipo, 
            fecha_hora, 
            categoria, 
            cantidad,
            descripcion,
            CASE 
                WHEN tipo = 'ganancia' AND categoria IN ('Uber', 'InDriver', 'Cabify') THEN 
                    CASE 
                        WHEN categoria = 'InDriver' THEN cantidad / (1 - 0.1095)
                        WHEN categoria = 'Uber' THEN cantidad / (1 - 0.2655)
                        ELSE cantidad
                    END
                ELSE cantidad
            END as cantidad_bruta
        FROM registros
    """
    params = []
    
    if fecha_inicio and fecha_fin:
        query += " WHERE DATE(fecha_hora) BETWEEN ? AND ?"
        params = [fecha_inicio, fecha_fin]
    elif fecha_inicio:
        query += " WHERE DATE(fecha_hora) >= ?"
        params = [fecha_inicio]
    elif fecha_fin:
        query += " WHERE DATE(fecha_hora) <= ?"
        params = [fecha_fin]
    
    query += " ORDER BY fecha_hora DESC"
    
    cursor.execute(query, params)
    registros = cursor.fetchall()
    conexion.close()
    
    return registros

def calcular_resumen(fecha_inicio=None, fecha_fin=None):
    """Calcula totales de ganancias, gastos y horas"""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    # Construir la consulta base
    query_base = "SELECT COALESCE(SUM(cantidad), 0) FROM registros WHERE tipo = ?"
    params_ganancias = ['ganancia']
    params_gastos = ['gasto']
    
    # Agregar filtros de fecha si existen
    if fecha_inicio and fecha_fin:
        query_base += " AND DATE(fecha_hora) BETWEEN ? AND ?"
        params_ganancias.extend([fecha_inicio, fecha_fin])
        params_gastos.extend([fecha_inicio, fecha_fin])
    elif fecha_inicio:
        query_base += " AND DATE(fecha_hora) >= ?"
        params_ganancias.append(fecha_inicio)
        params_gastos.append(fecha_inicio)
    elif fecha_fin:
        query_base += " AND DATE(fecha_hora) <= ?"
        params_ganancias.append(fecha_fin)
        params_gastos.append(fecha_fin)
    
    # Total ganancias
    cursor.execute(query_base, params_ganancias)
    total_ganancias = cursor.fetchone()[0]
    
    # Total gastos
    cursor.execute(query_base, params_gastos)
    total_gastos = cursor.fetchone()[0]
    
    # Calcular horas trabajadas (solo con ganancias)
    query_horas = "SELECT fecha_hora FROM registros WHERE tipo = 'ganancia'"
    params_horas = []
    
    if fecha_inicio and fecha_fin:
        query_horas += " AND DATE(fecha_hora) BETWEEN ? AND ?"
        params_horas = [fecha_inicio, fecha_fin]
    elif fecha_inicio:
        query_horas += " AND DATE(fecha_hora) >= ?"
        params_horas = [fecha_inicio]
    elif fecha_fin:
        query_horas += " AND DATE(fecha_hora) <= ?"
        params_horas = [fecha_fin]
    
    query_horas += " ORDER BY fecha_hora ASC"
    
    cursor.execute(query_horas, params_horas)
    registros_horas = cursor.fetchall()
    
    horas_totales = 0
    if len(registros_horas) >= 2:
        try:
            primera_hora = datetime.strptime(registros_horas[0][0], '%Y-%m-%d %H:%M:%S')
            ultima_hora = datetime.strptime(registros_horas[-1][0], '%Y-%m-%d %H:%M:%S')
            diferencia = ultima_hora - primera_hora
            horas_totales = round(diferencia.total_seconds() / 3600, 1)
        except:
            horas_totales = 0
    
    conexion.close()
    
    return {
        'ganancias': total_ganancias,
        'gastos': total_gastos,
        'neto': total_ganancias - total_gastos,
        'horas': horas_totales
    }

# ============================================
# RUTAS DE LA APLICACIÓN
# ============================================

@app.route('/')
def index():
    """Página principal"""
    crear_tablas()
    
    # Obtener filtros de fecha
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    # Si no hay fechas, usar hoy
    if not fecha_inicio and not fecha_fin:
        hoy = date.today().strftime('%Y-%m-%d')
        fecha_inicio = hoy
        fecha_fin = hoy
    
    registros = obtener_registros(fecha_inicio, fecha_fin)
    resumen = calcular_resumen(fecha_inicio, fecha_fin)
    
    return render_template('index.html', 
                         registros=registros,
                         resumen=resumen,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         datetime=datetime)

@app.route('/registro/nuevo', methods=['POST'])
def nuevo_registro():
    """Crea un nuevo registro (gasto o ganancia)"""
    try:
        tipo = request.form['tipo']
        fecha_hora = request.form['fecha_hora']
        categoria = request.form['categoria']
        cantidad_bruta = float(request.form['cantidad'])
        descripcion = request.form.get('descripcion', '')
        
        # Validar
        if not fecha_hora:
            fecha_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Calcular cantidad final según comisiones
        cantidad_final = cantidad_bruta
        
        if tipo == 'ganancia':
            if categoria == 'InDriver':
                # Descontar 10.95%
                cantidad_final = cantidad_bruta * (1 - 0.1095)
                descripcion = f"{descripcion} | Bruto: S/{cantidad_bruta:.2f} (Comisión 10.95%)".strip()
            elif categoria == 'Uber':
                # Descontar 26.55%
                cantidad_final = cantidad_bruta * (1 - 0.2655)
                descripcion = f"{descripcion} | Bruto: S/{cantidad_bruta:.2f} (Comisión 26.55%)".strip()
            elif categoria == 'Cabify':
                # Sin comisión
                descripcion = f"{descripcion} | Bruto: S/{cantidad_bruta:.2f} (Sin comisión)".strip()
        
        # Generar ID personalizado
        id_personalizado = generar_id_personalizado(tipo)
        
        conexion = sqlite3.connect(DB_NAME)
        cursor = conexion.cursor()
        
        cursor.execute('''
            INSERT INTO registros 
            (id_personalizado, tipo, fecha_hora, categoria, cantidad, descripcion)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (id_personalizado, tipo, fecha_hora, categoria, cantidad_final, descripcion))
        
        conexion.commit()
        conexion.close()
        
        flash(f'✅ Registro {id_personalizado} creado con éxito', 'success')
        
    except Exception as e:
        flash(f'❌ Error al crear registro: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/registro/editar/<int:id>', methods=['GET', 'POST'])
def editar_registro(id):
    """Edita un registro existente"""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    if request.method == 'POST':
        # Actualizar registro
        fecha_hora = request.form['fecha_hora']
        categoria = request.form['categoria']
        cantidad = float(request.form['cantidad'])
        descripcion = request.form.get('descripcion', '')
        
        cursor.execute('''
            UPDATE registros 
            SET fecha_hora = ?, categoria = ?, cantidad = ?, descripcion = ?
            WHERE id = ?
        ''', (fecha_hora, categoria, cantidad, descripcion, id))
        
        conexion.commit()
        conexion.close()
        
        flash('✅ Registro actualizado', 'success')
        return redirect(url_for('index'))
    
    # Obtener datos del registro
    cursor.execute("SELECT * FROM registros WHERE id = ?", (id,))
    registro = cursor.fetchone()
    conexion.close()
    
    if not registro:
        flash('❌ Registro no encontrado', 'error')
        return redirect(url_for('index'))
    
    return render_template('editar.html', registro=registro)

@app.route('/registro/eliminar/<int:id>')
def eliminar_registro(id):
    """Elimina un registro"""
    try:
        conexion = sqlite3.connect(DB_NAME)
        cursor = conexion.cursor()
        
        cursor.execute("DELETE FROM registros WHERE id = ?", (id,))
        conexion.commit()
        conexion.close()
        
        flash('🗑️ Registro eliminado', 'success')
        
    except Exception as e:
        flash(f'❌ Error al eliminar: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/api/resumen')
def api_resumen():
    """API para obtener resumen en JSON"""
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    resumen = calcular_resumen(fecha_inicio, fecha_fin)
    return jsonify(resumen)

# ============================================
# PUNTO DE ENTRADA
# ============================================
if __name__ == '__main__':
    crear_tablas()
    app.run(debug=True, host='0.0.0.0', port=5000)